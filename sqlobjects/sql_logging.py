"""SQL logging utilities for sqlobjects.

Provides ObjectLogger (a logging.Logger subclass that auto-rewrites caller
fields to user-code location) and get_caller_frame() for custom scenarios.

Frame-skip strategy:
- Skips frames from site-packages (covers pip-installed sqlobjects/sqlalchemy)
- Skips frames whose module name starts with "sqlobjects." or "sqlalchemy."
  (covers editable installs via `pip install -e .`)
- Skips frames from extra_skip_packages specified by the caller
"""

from __future__ import annotations

import inspect
import logging
import os
from collections.abc import Iterator, Mapping
from time import perf_counter
from types import FrameType
from typing import Any

from greenlet import getcurrent
from sqlalchemy import event
from sqlalchemy.engine import Engine


__all__ = ["get_caller_frame", "ObjectLogger"]

# Exact module names that are always considered internal
_INTERNAL_MODULES = {"sqlobjects", "sqlalchemy", "logging"}

# Module name prefixes that are always considered internal
_INTERNAL_PREFIXES = ("sqlobjects.", "sqlalchemy.")

# Absolute path of this file, used to skip itself reliably
_THIS_FILE = os.path.abspath(__file__)


def _should_skip_frame(
    filepath: str,
    module: str,
    extra_skip_prefixes: tuple[str, ...],
) -> bool:
    """Return True if this frame should be skipped (library/internal frame).

    Args:
        filepath: frame_info.filename
        module: frame.f_globals.get("__name__", "")
        extra_skip_prefixes: tuple of module name prefixes to skip in addition
            to the built-in sqlobjects/sqlalchemy prefixes.
    """
    if "site-packages" in filepath:
        return True
    if filepath.startswith("<"):
        return True
    if module in _INTERNAL_MODULES or module.startswith(_INTERNAL_PREFIXES):
        return True
    if filepath == _THIS_FILE or os.path.abspath(filepath) == _THIS_FILE:
        return True
    if extra_skip_prefixes and module.startswith(extra_skip_prefixes):
        return True
    return False


def _caller_frames() -> Iterator[FrameType]:
    """Walk Python frames, including parents suspended by SQLAlchemy's greenlet."""
    current = getcurrent()
    frame = inspect.currentframe()
    try:
        while True:
            while frame is not None:
                yield frame
                frame = frame.f_back
            current = current.parent
            if current is None:
                break
            frame = current.gr_frame
    finally:
        del frame


def _find_user_frame(
    extra_skip_packages: list[str] | None = None,
) -> inspect.FrameInfo | None:
    """Return the first user-code FrameInfo, skipping library frames.

    Applies the same skip rules as get_caller_frame() but returns the raw
    FrameInfo instead of a formatted string. Returns None if no frame found.
    """
    extra_skip_prefixes: tuple[str, ...] = tuple(extra_skip_packages) if extra_skip_packages else ()
    for frame in _caller_frames():
        module = frame.f_globals.get("__name__", "")
        if not _should_skip_frame(frame.f_code.co_filename, module, extra_skip_prefixes):
            return inspect.FrameInfo(frame, *inspect.getframeinfo(frame, context=0))
    return None


def get_caller_frame(
    extra_skip_packages: list[str] | None = None,
    max_frames: int = 1,
) -> str | list[str]:
    """Inspect the call stack and return the first user-code frame(s).

    Skips frames from:
    - site-packages (pip install)
    - sqlobjects.* and sqlalchemy.* modules (editable install)
    - extra_skip_packages prefixes provided by the caller

    Args:
        extra_skip_packages: Additional module name prefixes to skip
            (e.g. ["myapp.middleware"]). Matched against frame's __name__.
        max_frames: How many user-code frames to return.
            1 returns a str; >1 returns a list[str].

    Returns:
        Frame string "path/to/file.py:lineno in funcname", or a list of such
        strings when max_frames > 1.
    """
    extra_skip_prefixes: tuple[str, ...] = tuple(extra_skip_packages) if extra_skip_packages else ()
    frames: list[str] = []

    for frame in _caller_frames():
        module = frame.f_globals.get("__name__", "")
        if _should_skip_frame(frame.f_code.co_filename, module, extra_skip_prefixes):
            continue
        rel_path = _relative_path(frame.f_code.co_filename)
        frames.append(f"{rel_path}:{frame.f_lineno} in {frame.f_code.co_name}")
        if len(frames) >= max_frames:
            break

    if not frames:
        return "<unknown>" if max_frames == 1 else ["<unknown>"]
    return frames[0] if max_frames == 1 else frames


def _relative_path(filepath: str) -> str:
    """Return path relative to cwd, or absolute if outside cwd."""
    try:
        return os.path.relpath(filepath)
    except ValueError:
        return filepath


class ObjectLogger(logging.Logger):
    """logging.Logger subclass that rewrites LogRecord caller fields to user-code location.

    Overrides makeRecord() to replace the standard caller fields
    (filename, funcName, lineno, pathname) with the first user-code frame
    found by _find_user_frame(). This means any handler attached to this logger
    — including loguru InterceptHandlers — will display the real call site
    without any additional Filter configuration.

    Args:
        name: Logger name (passed to logging.Logger).
        level: Initial log level (default NOTSET).
        extra_skip_packages: Additional module name prefixes to skip when
            searching for the user-code frame (e.g. ["myapp.middleware"]).
    """

    def __init__(
        self,
        name: str,
        level: int = logging.NOTSET,
        extra_skip_packages: list[str] | None = None,
    ) -> None:
        super().__init__(name, level)
        self.extra_skip_packages = extra_skip_packages

    def makeRecord(  # noqa: N802
        self,
        name: str,
        level: int,
        fn: str,
        lno: int,
        msg: object,
        args: Any,
        exc_info: Any,
        func: str | None = None,
        extra: Mapping[str, object] | None = None,
        sinfo: str | None = None,
    ) -> logging.LogRecord:
        record = super().makeRecord(name, level, fn, lno, msg, args, exc_info, func, extra, sinfo)
        frame_info = _find_user_frame(self.extra_skip_packages)
        if frame_info:
            record.pathname = os.path.abspath(frame_info.filename)
            record.filename = os.path.basename(frame_info.filename)
            record.module = os.path.splitext(record.filename)[0]
            record.funcName = frame_info.function
            record.lineno = frame_info.lineno
        return record


def _install_object_logger(name: str) -> ObjectLogger:
    """Create an ObjectLogger and register it in the logging system.

    Directly writes into logging.root.manager.loggerDict so that
    logging.getLogger(name) returns this ObjectLogger instance.
    Migrates handlers, level, and propagate from any pre-existing Logger
    (but not from PlaceHolder sentinels, which are logging internals).

    Thread-safe: acquires the logging module lock during the operation.

    Known limitation: code that obtained a reference via getLogger(name)
    *before* this function runs will still hold the old Logger instance.
    """
    with logging._lock:  # type: ignore[attr-defined]  # noqa: SLF001
        existing = logging.root.manager.loggerDict.get(name)
        logger = ObjectLogger(name)
        logger.parent = logging.root
        logger.propagate = True
        if isinstance(existing, logging.Logger):
            for handler in existing.handlers:
                logger.addHandler(handler)
            if existing.level != logging.NOTSET:
                logger.setLevel(existing.level)
            logger.propagate = existing.propagate
        logging.root.manager.loggerDict[name] = logger
    return logger


# Module-level instance shared by all database engines and usable by callers.
_sql_logger: ObjectLogger = _install_object_logger("sqlobjects.sql")


def _install_query_logging(engine: Engine, db_name: str) -> None:
    """Observe physical cursor executions without recompilation or row fetching."""
    timing_key = "_sqlobjects_query_timing"

    def start(context, statement, parameters, executemany):
        if context is not None and _sql_logger.isEnabledFor(logging.DEBUG):
            setattr(
                context,
                timing_key,
                (perf_counter(), statement, None if engine.hide_parameters else parameters, executemany),
            )

    def do_execute(cursor, statement, parameters, context):
        start(context, statement, parameters, False)

    def do_executemany(cursor, statement, parameters, context):
        start(context, statement, parameters, True)

    def do_execute_no_params(cursor, statement, context):
        start(context, statement, None, False)

    def emit(context, cursor=None, error=None):
        if context is None:
            return
        timing = context.__dict__.pop(timing_key, None)
        if timing is None or not _sql_logger.isEnabledFor(logging.DEBUG):
            return
        started, statement, parameters, executemany = timing
        duration_ms = (perf_counter() - started) * 1000
        try:
            _sql_logger.debug(
                statement,
                extra={
                    "sql": statement,
                    "params": None if engine.hide_parameters else parameters,
                    "duration_ms": duration_ms,
                    "db_name": db_name,
                    "dialect": engine.dialect.name,
                    "executemany": executemany,
                    "rowcount": cursor.rowcount if cursor is not None and error is None else None,
                    "success": error is None,
                    "error_type": type(error).__name__ if error is not None else None,
                },
            )
        except Exception:
            # Diagnostics must not roll back a successful write or replace a DB error.
            pass

    def after_execute(conn, cursor, statement, parameters, context, executemany):
        emit(context, cursor)

    def handle_error(exception_context):
        emit(
            exception_context.execution_context,
            error=exception_context.original_exception,
        )

    # Dialect events receive each batch's actual SQL/params. For insertmanyvalues,
    # after_cursor_execute receives the original unbatched statement/params.
    event.listen(engine, "do_execute", do_execute)
    event.listen(engine, "do_executemany", do_executemany)
    event.listen(engine, "do_execute_no_params", do_execute_no_params)
    event.listen(engine, "after_cursor_execute", after_execute)
    event.listen(engine, "handle_error", handle_error)

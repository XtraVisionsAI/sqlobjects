"""SQL logging utilities for sqlobjects.

Provides get_caller_frame() to surface user-code caller information in SQL log
records, compatible with standard logging and loguru.

Filter strategy:
- Skips frames from site-packages (covers pip-installed sqlobjects/sqlalchemy)
- Skips frames whose module name starts with "sqlobjects." or "sqlalchemy."
  (covers editable installs via `pip install -e .`)
- Skips frames from extra_skip_packages specified by the caller
"""

from __future__ import annotations

import inspect
import logging
import os


__all__ = ["get_caller_frame", "SQLCallerFilter"]

# Exact module names that are always considered internal
_INTERNAL_MODULES = {"sqlobjects", "sqlalchemy"}

# Module name prefixes that are always considered internal
_INTERNAL_PREFIXES = ("sqlobjects.", "sqlalchemy.")

# Absolute path of this file, used to skip itself reliably
_THIS_FILE = os.path.abspath(__file__)


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
    skip_prefixes = _INTERNAL_PREFIXES
    if extra_skip_packages:
        skip_prefixes = skip_prefixes + tuple(extra_skip_packages)

    frames: list[str] = []

    for frame_info in inspect.stack():
        filepath = frame_info.filename
        module = frame_info.frame.f_globals.get("__name__", "")

        # Skip site-packages frames (pip-installed third-party libs)
        if "site-packages" in filepath:
            continue

        # Skip sqlobjects/sqlalchemy frames (editable install)
        if module in _INTERNAL_MODULES or module.startswith(skip_prefixes):
            continue

        # Skip this helper file itself
        if os.path.abspath(filepath) == _THIS_FILE:
            continue

        rel_path = _relative_path(filepath)
        frames.append(f"{rel_path}:{frame_info.lineno} in {frame_info.function}")

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


class SQLCallerFilter(logging.Filter):
    """logging.Filter that rewrites LogRecord caller fields to user-code location.

    Inspects the call stack at filter time, skips library frames (site-packages
    and sqlobjects.*/sqlalchemy.* modules for editable installs), and overwrites
    record.filename / record.funcName / record.lineno / record.pathname so that
    any handler (including loguru interception) displays the real user-code
    call site.

    Also exposes record.caller (str or list[str]) for use in custom Formatters.

    Args:
        max_frames: Number of user-code frames to capture (default 1).
            When 1, record.caller is a str and record location fields point
            to that single frame.
            When > 1, record.caller is a list[str] and record location fields
            are set from the first (most recent) frame.
        extra_skip_packages: Additional module name prefixes to skip
            (matched against frame's __name__).
    """

    def __init__(
        self,
        max_frames: int = 1,
        extra_skip_packages: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.max_frames = max_frames
        self.extra_skip_packages: list[str] | None = list(extra_skip_packages) if extra_skip_packages else None

    def filter(self, record: logging.LogRecord) -> bool:
        caller = get_caller_frame(
            extra_skip_packages=self.extra_skip_packages,
            max_frames=self.max_frames,
        )
        record.caller = caller

        # Overwrite standard location fields from the first user frame
        first = caller if isinstance(caller, str) else caller[0]
        self._overwrite_record_location(record, first)

        return True

    @staticmethod
    def _overwrite_record_location(record: logging.LogRecord, frame_str: str) -> None:
        """Parse 'path/to/file.py:lineno in funcname' and overwrite record fields.

        Frame string format: "relative/path/to/file.py:42 in func_name"
        Uses rsplit to handle edge cases where function name could have spaces.
        """
        try:
            # Split off the function name part (rightmost " in ")
            path_part, func_part = frame_str.rsplit(" in ", 1)
            # Split off the line number (rightmost ":")
            filepath, lineno_str = path_part.rsplit(":", 1)
            record.pathname = os.path.abspath(filepath)
            record.filename = os.path.basename(filepath)
            record.module = os.path.splitext(record.filename)[0]
            record.funcName = func_part.strip()
            record.lineno = int(lineno_str)
        except (ValueError, AttributeError):
            pass  # Keep original fields if parsing fails

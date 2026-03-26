"""SQL logging utilities for sqlobjects.

Provides SQLCallerFilter and get_caller_frame() to surface user-code caller
information in SQL log records, compatible with standard logging and loguru.

Filter strategy:
- Skips frames from site-packages (covers pip-installed sqlobjects/sqlalchemy)
- Skips frames whose module name starts with "sqlobjects." or "sqlalchemy."
  (covers editable installs via `pip install -e .`)
- Skips frames from extra_skip_packages specified by the caller
"""

from __future__ import annotations

import inspect
import os


# Module name prefixes that are always considered internal
_INTERNAL_PREFIXES = ("sqlobjects.", "sqlalchemy.", "sqlobjects", "sqlalchemy")


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
        if module.startswith(skip_prefixes):
            continue

        # Skip this helper file itself
        if os.path.basename(filepath) == "sql_logging.py":
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

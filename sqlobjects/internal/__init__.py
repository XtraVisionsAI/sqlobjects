"""Internal utilities for SQLObjects

This package contains internal utilities shared between Model and Bulk
operations. These utilities are not part of the public API and should
not be used directly by end users.

The utilities provide:
- Low-level SQL execution (SQLOperations)
- Result processing (ResultProcessor)
"""

from .operations import SQLOperations
from .results import ResultProcessor


__all__ = ["SQLOperations", "ResultProcessor"]

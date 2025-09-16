"""SQLObjects - High-performance async ORM for Python.

A modern, type-safe ORM built on SQLAlchemy Core with Django-style API,
designed for high performance and developer productivity.
"""

from .model import ObjectModel
from .objects import (
    BulkResult,
    ConflictResolution,
    ErrorHandling,
    FailedRecord,
    ObjectsManager,
    TransactionMode,
)
from .queryset import Q, QuerySet


__version__ = "0.3.0"

__all__ = [
    # Core classes
    "ObjectModel",
    "ObjectsManager",
    "QuerySet",
    "Q",
    # Bulk operations
    "BulkResult",
    "FailedRecord",
    # Transaction control
    "TransactionMode",
    "ErrorHandling",
    "ConflictResolution",
]

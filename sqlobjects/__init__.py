"""SQLObjects - High-performance async ORM for Python.

A modern, type-safe ORM built on SQLAlchemy Core with Django-style API,
designed for high performance and developer productivity.
"""

from .cascade import CascadeOption, CascadePresets, CascadeType, OnDelete, OnDeleteType
from .fields.relations import relationship
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
from .sql_logging import ObjectLogger, get_caller_frame


__version__ = "2.0.1"

__all__ = [
    # Core classes
    "ObjectModel",
    "ObjectsManager",
    "QuerySet",
    "Q",
    # Field definitions
    "relationship",
    # Cascade operations
    "OnDelete",
    "CascadeOption",
    "CascadePresets",
    "OnDeleteType",
    "CascadeType",
    # Bulk operations
    "BulkResult",
    "FailedRecord",
    # Transaction control
    "TransactionMode",
    "ErrorHandling",
    "ConflictResolution",
    # SQL logging
    "ObjectLogger",
    "get_caller_frame",
]

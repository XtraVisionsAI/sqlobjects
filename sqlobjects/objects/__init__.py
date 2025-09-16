"""SQLObjects Objects Manager - Public Interface"""

from .bulk import BulkResult, ConflictResolution, ErrorHandling, FailedRecord, TransactionMode
from .core import ObjectsDescriptor, ObjectsManager


__all__ = [
    "ObjectsDescriptor",
    "ObjectsManager",
    "BulkResult",
    "FailedRecord",
    "TransactionMode",
    "ErrorHandling",
    "ConflictResolution",
]

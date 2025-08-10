"""SQLObjects - Django-style async ORM library built on SQLAlchemy

A modern, type-safe ORM that combines the best of Django's ORM with SQLAlchemy's power,
featuring chainable queries, Q objects, relationship loading, and comprehensive validation.
"""

from .base import ObjectModel
from .queries import Q


__version__ = "0.1.0"

__all__ = [
    # Base model
    "ObjectModel",
    # Core query system
    "Q",
]

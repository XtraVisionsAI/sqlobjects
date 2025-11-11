"""Backward compatibility module for relationship proxy classes.

All proxy classes have been moved to fields/proxies.py with new names:
- RelatedQuerySet → RelatedQuerySet (unchanged)
- NoLoadProxy → NoLoadRelation
- RaiseProxy → RaiseLoadRelation

This module provides backward compatibility aliases.
Import from sqlobjects.fields.proxies instead.
"""

from ..proxies import NoLoadRelation as NoLoadProxy
from ..proxies import RaiseLoadRelation as RaiseProxy
from ..proxies import RelatedQuerySet


__all__ = ["RelatedQuerySet", "NoLoadProxy", "RaiseProxy"]

"""Special relationship proxy classes for advanced lazy loading strategies.

This module contains proxy classes for special relationship loading behaviors:
- RelatedQuerySet: Dynamic query set for lazy='dynamic'
- NoLoadProxy: Empty proxy for lazy='noload'
- RaiseProxy: Exception-raising proxy for lazy='raise'

Note: Standard relationship proxies (RelatedObjectProxy, OneToManyCollection,
M2MRelatedCollection) are now in fields/strategies.py as the unified public API.
"""

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from ...model import ObjectModel
    from .descriptors import RelationshipDescriptor


class RelatedQuerySet:
    """Related query set - inherits full QuerySet functionality (lazy='dynamic')."""

    def __init__(self, instance: "ObjectModel", descriptor: "RelationshipDescriptor"):
        """Initialize related query set.

        Args:
            instance: Parent model instance
            descriptor: Relationship descriptor
        """
        self.parent_instance = instance
        self.relationship_desc = descriptor
        self._queryset: Any = None
        self._initialized = False

    def _get_queryset(self) -> Any:
        """Lazy initialize QuerySet.

        Returns:
            Initialized QuerySet instance
        """
        if not self._initialized:
            # QuerySet will be implemented in Layer 5
            # For now, return a placeholder
            self._queryset = None
            self._initialized = True

        return self._queryset

    def __getattr__(self, name: str) -> Any:
        """Proxy all QuerySet methods.

        Args:
            name: Method name to proxy

        Returns:
            Proxied method or attribute
        """
        qs = self._get_queryset()
        if qs is None:
            raise NotImplementedError("QuerySet not yet implemented")

        attr = getattr(qs, name)
        return attr


class NoLoadProxy:
    """No-load proxy (lazy='noload')."""

    def __init__(self, instance: "ObjectModel", descriptor: "RelationshipDescriptor"):
        """Initialize no-load proxy.

        Args:
            instance: Parent model instance
            descriptor: Relationship descriptor
        """
        self.instance = instance
        self.descriptor = descriptor
        self.property = descriptor.property

    def __await__(self) -> Any:
        """Async access returns empty result."""
        return self._empty_result().__await__()

    async def _empty_result(self) -> list[Any] | None:
        """Return empty result.

        Returns:
            Empty list for collections, None for single objects
        """
        return [] if self.property.uselist else None

    def __iter__(self) -> Any:
        """Iterator returns empty."""
        return iter([])

    def __len__(self) -> int:
        """Length is 0."""
        return 0

    def __bool__(self) -> bool:
        """Boolean value is False."""
        return False


class RaiseProxy:
    """Raise exception proxy (lazy='raise')."""

    def __init__(self, instance: "ObjectModel", descriptor: "RelationshipDescriptor"):
        """Initialize raise proxy.

        Args:
            instance: Parent model instance
            descriptor: Relationship descriptor
        """
        self.instance = instance
        self.descriptor = descriptor
        self.property = descriptor.property

    def __await__(self) -> Any:
        """Async access raises exception."""
        raise AttributeError(
            f"Relationship '{self.property.name}' is configured with lazy='raise'. "
            f"Use explicit loading with select_related() or prefetch_related()."
        )

    def __iter__(self) -> Any:
        """Iterator access raises exception."""
        raise AttributeError(
            f"Relationship '{self.property.name}' is configured with lazy='raise'. "
            f"Use explicit loading with select_related() or prefetch_related()."
        )

    def __len__(self) -> int:
        """Length access raises exception."""
        raise AttributeError(
            f"Relationship '{self.property.name}' is configured with lazy='raise'. "
            f"Use explicit loading with select_related() or prefetch_related()."
        )

    def __bool__(self) -> bool:
        """Boolean access raises exception."""
        raise AttributeError(
            f"Relationship '{self.property.name}' is configured with lazy='raise'. "
            f"Use explicit loading with select_related() or prefetch_related()."
        )

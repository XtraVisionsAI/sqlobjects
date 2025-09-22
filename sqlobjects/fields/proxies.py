from typing import TYPE_CHECKING, Any

from ..exceptions import DeferredFieldError


if TYPE_CHECKING:
    from ..mixins import DeferredLoadingMixin


class DeferredFieldProxy:
    """Optimized proxy for deferred fields with caching."""

    def __init__(self, instance: "DeferredLoadingMixin", field_name: str) -> None:
        self.instance = instance
        self.field_name = field_name
        self._cached_value = None
        self._is_loaded = False

    async def fetch(self) -> Any:
        """Fetch field value, auto-loading if not loaded."""
        if not self._is_loaded:
            await self.instance.load_deferred_field(self.field_name)
            self._cached_value = getattr(self.instance, self.field_name, None)
            self._is_loaded = True
        return self._cached_value

    def is_loaded(self) -> bool:
        return self.instance.is_field_loaded(self.field_name)

    def is_deferred(self) -> bool:
        return self.instance.is_field_deferred(self.field_name)

    def __iter__(self):
        raise DeferredFieldError(
            f"Cannot iterate over deferred field '{self.field_name}' on {self.instance.__class__.__name__}"
        )

    def __len__(self):
        raise DeferredFieldError(
            f"Cannot get length of deferred field '{self.field_name}' on {self.instance.__class__.__name__}"
        )

    def __bool__(self):
        raise DeferredFieldError(
            f"Cannot check boolean value of deferred field '{self.field_name}' on {self.instance.__class__.__name__}"
        )

    def __getitem__(self, key):
        raise DeferredFieldError(
            f"Cannot access items of deferred field '{self.field_name}' on {self.instance.__class__.__name__}"
        )

    def __contains__(self, item):
        raise DeferredFieldError(
            f"Cannot check containment in deferred field '{self.field_name}' on {self.instance.__class__.__name__}"
        )

    def __add__(self, other):
        raise DeferredFieldError(
            f"Cannot perform arithmetic on deferred field '{self.field_name}' on {self.instance.__class__.__name__}"
        )

    def __str__(self):
        return f"<DeferredField: {self.field_name}>"

    def __repr__(self):
        return f"DeferredFieldProxy(field_name='{self.field_name}')"


class RelationFieldProxy:
    """Optimized proxy for relationship fields with caching."""

    def __init__(self, instance: Any, field_name: str) -> None:
        self.instance = instance
        self.field_name = field_name
        self._cached_objects = None
        self._is_loaded = False

    async def fetch(self) -> Any:
        """Fetch relationship objects."""
        if not self._is_loaded:
            relationships = getattr(self.instance.__class__, "_relationships", {})
            if self.field_name not in relationships:
                return None

            descriptor = relationships[self.field_name]
            actual_proxy = descriptor.__get__(self.instance, self.instance.__class__)

            if hasattr(actual_proxy, "all"):
                self._cached_objects = await actual_proxy.all()
            elif hasattr(actual_proxy, "get"):
                self._cached_objects = await actual_proxy.get()
            else:
                self._cached_objects = actual_proxy

            self._is_loaded = True
        return self._cached_objects

    def is_loaded(self) -> bool:
        cache_attr = f"_{self.field_name}_cache"
        return hasattr(self.instance, cache_attr)

    def is_deferred(self) -> bool:
        return not self.is_loaded()

    def _get_cached_objects(self) -> Any:
        cache_attr = f"_{self.field_name}_cache"
        return getattr(self.instance, cache_attr, None)

    def __iter__(self):
        raise DeferredFieldError(
            f"Cannot iterate over unloaded relationship '{self.field_name}' on {self.instance.__class__.__name__}"
        )

    def __len__(self):
        raise DeferredFieldError(
            f"Cannot get length of unloaded relationship '{self.field_name}' on {self.instance.__class__.__name__}"
        )

    def __bool__(self):
        raise DeferredFieldError(
            f"Cannot check boolean value of unloaded relationship '{self.field_name}' "
            f"on {self.instance.__class__.__name__}"
        )

    def __getitem__(self, key):
        raise DeferredFieldError(
            f"Cannot access items of unloaded relationship '{self.field_name}' on {self.instance.__class__.__name__}"
        )

    def __contains__(self, item):
        raise DeferredFieldError(
            f"Cannot check containment in unloaded relationship '{self.field_name}' "
            f"on {self.instance.__class__.__name__}"
        )

    def __add__(self, other):
        raise DeferredFieldError(
            f"Cannot perform arithmetic on unloaded relationship '{self.field_name}' "
            f"on {self.instance.__class__.__name__}"
        )

    def __str__(self):
        return f"<RelationField: {self.field_name}>"

    def __repr__(self):
        return f"RelationFieldProxy(field_name='{self.field_name}')"

from typing import TYPE_CHECKING, Generic, TypeVar, overload

from ...cascade import OnDelete


if TYPE_CHECKING:
    from ...model import ObjectModel
    from ..proxies import BaseRelated


T = TypeVar("T")


class RelationshipType:
    """Relationship type enumeration."""

    MANY_TO_ONE = "many_to_one"
    ONE_TO_MANY = "one_to_many"
    ONE_TO_ONE = "one_to_one"
    MANY_TO_MANY = "many_to_many"


class RelationshipProperty:
    """Relationship property configuration and metadata."""

    def __init__(
        self,
        argument: str | type["ObjectModel"],
        foreign_keys: str | list[str] | None = None,
        back_populates: str | None = None,
        backref: str | None = None,
        lazy: str = "select",
        uselist: bool | None = None,
        secondary: str | None = None,
        primaryjoin: str | None = None,
        secondaryjoin: str | None = None,
        order_by: str | list[str] | None = None,
        cascade: str | bool = False,
        on_delete: OnDelete = OnDelete.NO_ACTION,
        passive_deletes: bool = False,
        **kwargs,
    ):
        """Initialize relationship property with cascade and deletion behavior.

        Args:
            argument: Target model class or string name
            foreign_keys: Foreign key field name(s)
            back_populates: Name of reverse relationship attribute
            backref: Name for automatic reverse relationship
            lazy: Loading strategy ('select', 'dynamic', 'noload', 'raise')
            uselist: Whether relationship returns a list
            secondary: M2M table name
            primaryjoin: Custom primary join condition
            secondaryjoin: Custom secondary join condition for M2M
            order_by: Default ordering for collections
            cascade: Cascade behavior (bool for simple on/off, str for SQLAlchemy cascade options)
            on_delete: Behavior when related object is deleted
            passive_deletes: Whether to use passive deletes
            **kwargs: Additional relationship options
        """
        self.argument = argument
        self.foreign_keys = foreign_keys
        self.back_populates = back_populates
        self.backref = backref
        self.lazy = lazy
        self.uselist = uselist
        self.secondary = secondary
        self.m2m_definition = None  # M2M table definition
        self.primaryjoin = primaryjoin
        self.secondaryjoin = secondaryjoin
        self.order_by = order_by
        self.cascade = cascade
        self.on_delete = on_delete
        self.passive_deletes = passive_deletes
        self.name: str | None = None
        self.resolved_model: type[ObjectModel] | None = None
        self.relationship_type: str | None = None
        self.is_many_to_many: bool = False  # M2M relationship flag

        # Store additional relationship configuration parameters
        self.extra_kwargs = kwargs


class RelationshipDescriptor(Generic[T]):
    """Unified relationship field descriptor with proper type hints."""

    def __init__(self, property_: RelationshipProperty):
        """Initialize relationship descriptor.

        Args:
            property_: Relationship property configuration
        """
        self.property = property_
        self.name: str | None = None
        self._is_relationship = True  # Mark as relationship for Column compatibility

    def __set_name__(self, owner: type, name: str) -> None:
        """Set descriptor name and register with model.

        Args:
            owner: Model class that owns this descriptor
            name: Field name
        """
        self.name = name
        self.property.name = name

        # Register relationship with model
        if not hasattr(owner, "_relationships"):
            owner._relationships = {}
        owner._relationships[name] = self

    @overload
    def __get__(self, instance: None, owner: type) -> "RelationshipDescriptor[T]": ...

    @overload
    def __get__(self, instance: "ObjectModel", owner: type) -> "BaseRelated[T]": ...

    def __get__(self, instance: "ObjectModel | None", owner: type) -> "RelationshipDescriptor[T] | BaseRelated[T]":
        """Get relationship value.

        Args:
            instance: Model instance or None for class access
            owner: Model class

        Returns:
            Appropriate relationship proxy based on lazy strategy
        """
        if instance is None:
            return self

        # Ensure relationships are resolved
        registry = getattr(instance.__class__, "__registry__", None)
        if registry:
            registry.resolve_all_relationships()

        # Check if already preloaded
        if self.name:
            cache_attr = f"_{self.name}_cache"
            if hasattr(instance, cache_attr):
                return getattr(instance, cache_attr)

        # Return different objects based on lazy strategy
        from ..proxies import (
            ManyToManyRelation,
            NoLoadRelation,
            OneToManyRelation,
            RaiseLoadRelation,
            RelatedObject,
            RelatedQuerySet,
        )

        if self.property.lazy == "dynamic":
            return RelatedQuerySet(instance, self)
        elif self.property.lazy == "noload":
            return NoLoadRelation(instance, self)
        elif self.property.lazy == "raise":
            return RaiseLoadRelation(instance, self)
        elif self.property.is_many_to_many:
            return ManyToManyRelation(instance, self)
        elif self.property.uselist:
            return OneToManyRelation(instance, self)
        else:
            return RelatedObject(instance, self)

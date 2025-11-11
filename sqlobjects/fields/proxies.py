"""Public proxy interfaces for field and relationship access.

This module provides all proxy classes for deferred fields and relationships:
- DeferredObject: Proxy for deferred field loading
- RelatedObject[T]: Single related object proxy
- RelatedCollection[T]: Base class for collection proxies
- OneToManyRelation[T]: One-to-many relationship proxy
- ManyToManyRelation[T]: Many-to-many relationship proxy
- RelatedQuerySet[T]: Dynamic query set proxy (lazy='dynamic')
- NoLoadRelation[T]: No-load proxy (lazy='noload')
- RaiseLoadRelation[T]: Raise-on-access proxy (lazy='raise')
"""

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from sqlalchemy import join, select

from ..exceptions import DeferredFieldError


if TYPE_CHECKING:
    from ..mixins import DeferredLoadingMixin
    from ..model import ObjectModel
    from .relations.descriptors import RelationshipDescriptor


T = TypeVar("T")


class DeferredObject:
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
        return f"<DeferredObject: {self.field_name}>"

    def __repr__(self):
        return f"DeferredObject(field_name='{self.field_name}')"


class BaseRelated(Generic[T]):
    """Base class for all relationship proxies."""

    def __init__(self, instance: "ObjectModel", descriptor: "RelationshipDescriptor"):
        self.instance = instance
        self.descriptor = descriptor
        self.property = descriptor.property
        self._cached_value = None
        self._loaded = False

    async def fetch(self) -> T:
        """Fetch related object(s)."""
        if not self._loaded:
            await self._load()
        return self._cached_value  # type: ignore

    def _invalidate_cache(self) -> None:
        """Invalidate cached value."""
        self._loaded = False
        self._cached_value = None

    async def _load(self):
        """Load related data from database - implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _load method")

    def _set_empty_result(self):
        """Set empty result - implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _set_empty_result method")


class RelatedObject(BaseRelated[T]):
    """Proxy for single related object (many-to-one, one-to-one)."""

    async def _load(self):
        """Load related object from database."""
        if self.property.foreign_keys and self.property.resolved_model:
            fk_field = self.property.foreign_keys
            if isinstance(fk_field, list):
                fk_field = fk_field[0]

            fk_value = getattr(self.instance, fk_field)
            if fk_value is not None:
                related_table = self.property.resolved_model.get_table()
                pk_col = list(related_table.primary_key.columns)[0]

                query = select(related_table).where(pk_col == fk_value)
                session = self.instance.get_session()
                result = await session.execute(query)
                row = result.first()

                if row:
                    self._cached_value = self.property.resolved_model.from_dict(dict(row._mapping), validate=False)

        self._loaded = True

    def _set_empty_result(self):
        """Set empty result for single object."""
        self._cached_value = None
        self._loaded = True

    def __str__(self):
        return f"<RelatedObject: {self.property.name}>"

    def __repr__(self):
        return f"RelatedObject(field='{self.property.name}')"


class RelatedCollection(BaseRelated[T], Generic[T]):
    """Base class for collection relationship proxies."""

    async def count(self) -> int:
        """Get count of related objects."""
        objects = await self.fetch()
        return len(objects)  # type: ignore

    async def clear(self, session=None):
        """Remove all objects from the relationship."""
        objects = await self.fetch()
        if objects:
            await self.remove(*objects, session=session)  # type: ignore

    async def add(self, *objs: T, session=None) -> None:
        """Add objects to the relationship - implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement add method")

    async def remove(self, *objs: T, session=None) -> None:
        """Remove objects from the relationship - implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement remove method")

    def _set_empty_result(self):
        """Set empty result for collection."""
        self._cached_value = []
        self._loaded = True


class OneToManyRelation(RelatedCollection[T]):
    """Proxy for one-to-many relationship collections."""

    async def _load(self):
        """Load one-to-many relationship."""
        if not self.property.resolved_model:
            self._set_empty_result()
            return

        instance_pk = self.instance.id
        related_table = self.property.resolved_model.get_table()

        fk_name = self._get_fk_field()
        fk_col = related_table.c[fk_name]
        query = select(related_table).where(fk_col == instance_pk)
        session = self.instance.get_session()
        result = await session.execute(query)

        self._cached_value = [
            self.property.resolved_model.from_dict(dict(row._mapping), validate=False) for row in result
        ]
        self._loaded = True

    async def add(self, *objs: T, session=None) -> None:
        """Add objects to the relationship."""
        session = session or self.instance.get_session()
        fk_field = self._get_fk_field()

        for obj in objs:
            setattr(obj, fk_field, self.instance.id)
            await obj.using(session).save()  # type: ignore

        self._invalidate_cache()

    async def remove(self, *objs: T, session=None) -> None:
        """Remove objects from the relationship."""
        session = session or self.instance.get_session()
        fk_field = self._get_fk_field()

        for obj in objs:
            setattr(obj, fk_field, None)
            await obj.using(session).save()  # type: ignore

        self._invalidate_cache()

    def _get_fk_field(self):
        """Get foreign key field name."""
        fk_name = self.property.foreign_keys
        if isinstance(fk_name, list):
            fk_name = fk_name[0]
        elif fk_name is None:
            fk_name = (
                f"{self.property.back_populates}_id"
                if self.property.back_populates
                else f"{self.instance.__class__.__name__.lower()}_id"
            )
        return fk_name

    def __str__(self):
        return f"<OneToManyRelation: {self.property.name}>"

    def __repr__(self):
        return f"OneToManyRelation(field='{self.property.name}')"


class ManyToManyRelation(RelatedCollection[T]):
    """Proxy for many-to-many relationship collections."""

    async def _load(self):
        """Load M2M related object list from database."""
        m2m_def = self.property.m2m_definition
        if not m2m_def:
            self._set_empty_result()
            return

        registry = getattr(self.instance.__class__, "__registry__", None)
        if not registry:
            self._set_empty_result()
            return

        m2m_table = registry.get_m2m_table(m2m_def.table_name)
        if not m2m_table or not m2m_def.left_ref_field:
            self._set_empty_result()
            return

        instance_id = getattr(self.instance, m2m_def.left_ref_field)
        if instance_id is None:
            self._set_empty_result()
            return

        if not self.property.resolved_model:
            self._set_empty_result()
            return

        related_table = self.property.resolved_model.get_table()

        if not (m2m_def.right_field and m2m_def.right_ref_field and m2m_def.left_field):
            self._set_empty_result()
            return

        joined_tables = join(
            m2m_table,
            related_table,
            getattr(m2m_table.c, m2m_def.right_field) == getattr(related_table.c, m2m_def.right_ref_field),
        )

        query = (
            select(related_table)
            .select_from(joined_tables)
            .where(getattr(m2m_table.c, m2m_def.left_field) == instance_id)
        )

        session = self.instance.get_session()
        result = await session.execute(query)

        self._cached_value = [
            self.property.resolved_model.from_dict(dict(row._mapping), validate=False) for row in result
        ]
        self._loaded = True

    async def add(self, *objs: T, session=None) -> None:
        """Add objects to M2M relationship."""
        session = session or self.instance.get_session()
        m2m_def = self.property.m2m_definition
        if not m2m_def:
            return

        registry = getattr(self.instance.__class__, "__registry__", None)
        if not registry:
            return
        m2m_table = registry.get_m2m_table(m2m_def.table_name)
        instance_id = getattr(self.instance, m2m_def.left_ref_field)

        for obj in objs:
            related_id = getattr(obj, m2m_def.right_ref_field)
            stmt = m2m_table.insert().values({m2m_def.left_field: instance_id, m2m_def.right_field: related_id})
            await session.execute(stmt)

        await session.commit()
        self._invalidate_cache()

    async def remove(self, *objs: T, session=None) -> None:
        """Remove objects from M2M relationship."""
        session = session or self.instance.get_session()
        m2m_def = self.property.m2m_definition
        if not m2m_def:
            return

        registry = getattr(self.instance.__class__, "__registry__", None)
        if not registry:
            return
        m2m_table = registry.get_m2m_table(m2m_def.table_name)
        instance_id = getattr(self.instance, m2m_def.left_ref_field)

        for obj in objs:
            related_id = getattr(obj, m2m_def.right_ref_field)
            stmt = m2m_table.delete().where(
                (getattr(m2m_table.c, m2m_def.left_field) == instance_id)
                & (getattr(m2m_table.c, m2m_def.right_field) == related_id)
            )
            await session.execute(stmt)

        await session.commit()
        self._invalidate_cache()

    async def set(self, objs: list[T], session=None) -> None:
        """Set M2M relationship to exact list of objects."""
        await self.clear(session=session)
        if objs:
            await self.add(*objs, session=session)

    def __str__(self):
        return f"<ManyToManyRelation: {self.property.name}>"

    def __repr__(self):
        return f"ManyToManyRelation(field='{self.property.name}')"


class RelatedQuerySet(BaseRelated[T]):
    """Dynamic query set proxy for lazy='dynamic' relationships."""

    def __init__(self, instance: "ObjectModel", descriptor: "RelationshipDescriptor"):
        super().__init__(instance, descriptor)
        self.parent_instance = instance
        self.relationship_desc = descriptor
        self._queryset: Any = None
        self._initialized = False

    def _get_queryset(self) -> Any:
        """Lazy initialize QuerySet."""
        if not self._initialized:
            # QuerySet will be implemented in Layer 5
            self._queryset = None
            self._initialized = True
        return self._queryset

    async def _load(self):
        """Load implementation - returns QuerySet."""
        self._cached_value = self._get_queryset()
        self._loaded = True

    def _set_empty_result(self):
        """Set empty QuerySet result."""
        self._cached_value = None
        self._loaded = True

    def __getattr__(self, name: str) -> Any:
        """Proxy all QuerySet methods."""
        qs = self._get_queryset()
        if qs is None:
            raise NotImplementedError("QuerySet not yet implemented")
        return getattr(qs, name)

    def __str__(self):
        return f"<RelatedQuerySet: {self.property.name}>"

    def __repr__(self):
        return f"RelatedQuerySet(field='{self.property.name}')"


class NoLoadRelation(BaseRelated[T]):
    """No-load proxy for lazy='noload' relationships."""

    async def _load(self):
        """Load implementation - returns empty result."""
        self._cached_value = [] if self.property.uselist else None
        self._loaded = True

    def _set_empty_result(self):
        """Set empty result."""
        self._cached_value = [] if self.property.uselist else None
        self._loaded = True

    def __iter__(self) -> Any:
        """Iterator returns empty."""
        return iter([])

    def __len__(self) -> int:
        """Length is 0."""
        return 0

    def __bool__(self) -> bool:
        """Boolean value is False."""
        return False

    def __str__(self):
        return f"<NoLoadRelation: {self.property.name}>"

    def __repr__(self):
        return f"NoLoadRelation(field='{self.property.name}')"


class RaiseLoadRelation(BaseRelated[T]):
    """Raise exception proxy for lazy='raise' relationships."""

    async def _load(self):
        """Load implementation - raises exception."""
        raise AttributeError(
            f"Relationship '{self.property.name}' is configured with lazy='raise'. "
            f"Use explicit loading with select_related() or prefetch_related()."
        )

    def _set_empty_result(self):
        """Set empty result - raises exception."""
        raise AttributeError(
            f"Relationship '{self.property.name}' is configured with lazy='raise'. "
            f"Use explicit loading with select_related() or prefetch_related()."
        )

    async def fetch(self):
        """Fetch raises exception for raise proxy."""
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

    def __str__(self):
        return f"<RaiseLoadRelation: {self.property.name}>"

    def __repr__(self):
        return f"RaiseLoadRelation(field='{self.property.name}')"

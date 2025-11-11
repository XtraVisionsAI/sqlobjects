"""Public proxy interfaces for field and relationship access."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import join, select

from ..exceptions import DeferredFieldError


if TYPE_CHECKING:
    from ..mixins import DeferredLoadingMixin
    from ..model import ObjectModel
    from .relations.descriptors import RelationshipDescriptor


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


class RelatedObjectProxy:
    """Proxy for single related object (many-to-one, one-to-one)."""

    def __init__(self, instance: "ObjectModel", descriptor: "RelationshipDescriptor"):
        self.instance = instance
        self.descriptor = descriptor
        self.property = descriptor.property
        self._cached_object = None
        self._loaded = False

    async def fetch(self):
        """Fetch the related object, auto-loading if not loaded."""
        if not self._loaded:
            await self._load()
        return self._cached_object

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
                    self._cached_object = self.property.resolved_model.from_dict(dict(row._mapping), validate=False)

        self._loaded = True

    def __str__(self):
        return f"<RelatedObject: {self.property.name}>"

    def __repr__(self):
        return f"RelatedObjectProxy(field='{self.property.name}')"


class BaseRelatedCollection:
    """Base class for related object collections."""

    def __init__(self, instance: "ObjectModel", descriptor: "RelationshipDescriptor"):
        self.instance = instance
        self.descriptor = descriptor
        self.property = descriptor.property
        self._cached_objects = None
        self._loaded = False

    async def fetch(self):
        """Fetch all related objects."""
        if not self._loaded:
            await self._load()
        return self._cached_objects or []

    async def _load(self):
        """Load related object list from database - implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _load method")

    def _set_empty_result(self):
        """Common method to set empty result."""
        self._cached_objects = []
        self._loaded = True


class OneToManyProxy(BaseRelatedCollection):
    """Proxy for one-to-many relationship collections."""

    async def _load(self):
        """Load one-to-many relationship."""
        if not self.property.resolved_model:
            self._set_empty_result()
            return

        instance_pk = self.instance.id
        related_table = self.property.resolved_model.get_table()

        fk_name = self.property.foreign_keys
        if isinstance(fk_name, list):
            fk_name = fk_name[0]
        elif fk_name is None:
            fk_name = (
                f"{self.property.back_populates}_id"
                if self.property.back_populates
                else f"{self.instance.__class__.__name__.lower()}_id"
            )

        fk_col = related_table.c[fk_name]
        query = select(related_table).where(fk_col == instance_pk)
        session = self.instance.get_session()
        result = await session.execute(query)

        self._cached_objects = [
            self.property.resolved_model.from_dict(dict(row._mapping), validate=False) for row in result
        ]
        self._loaded = True

    def __str__(self):
        return f"<OneToMany: {self.property.name}>"

    def __repr__(self):
        return f"OneToManyProxy(field='{self.property.name}')"


class ManyToManyProxy(BaseRelatedCollection):
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

        self._cached_objects = [
            self.property.resolved_model.from_dict(dict(row._mapping), validate=False) for row in result
        ]
        self._loaded = True

    def __str__(self):
        return f"<ManyToMany: {self.property.name}>"

    def __repr__(self):
        return f"ManyToManyProxy(field='{self.property.name}')"

from typing import TYPE_CHECKING, Any

from sqlalchemy import select


if TYPE_CHECKING:
    from ...model import ObjectModel
    from .descriptors import RelationshipDescriptor


class RelatedObjectProxy:
    """Proxy for single related object."""

    def __init__(self, instance: "ObjectModel", descriptor: "RelationshipDescriptor"):
        """Initialize related object proxy.

        Args:
            instance: Parent model instance
            descriptor: Relationship descriptor
        """
        self.instance = instance
        self.descriptor = descriptor
        self.property = descriptor.property
        self._cached_object = None
        self._loaded = False

    async def get(self):
        """Get the related object.

        Returns:
            Related object instance or None
        """
        if not self._loaded:
            await self._load()
        return self._cached_object

    def __await__(self):
        """Support await syntax."""
        return self.get().__await__()

    async def _load(self):
        """Load related object from database."""
        if self.property.foreign_keys and self.property.resolved_model:
            # Get foreign key field name
            fk_field = self.property.foreign_keys
            if isinstance(fk_field, list):
                fk_field = fk_field[0]

            fk_value = getattr(self.instance, fk_field)
            if fk_value is not None:
                related_table = self.property.resolved_model.get_table()
                pk_col = list(related_table.primary_key.columns)[0]

                query = select(related_table).where(pk_col == fk_value)  # noqa
                session = self.instance.get_session()
                result = await session.execute(query)
                row = result.first()

                if row:
                    self._cached_object = self.property.resolved_model.from_dict(dict(row._mapping), validate=False)

        self._loaded = True


class BaseRelatedCollection:
    """Base class for related object collections."""

    def __init__(self, instance: "ObjectModel", descriptor: "RelationshipDescriptor"):
        """Initialize related collection.

        Args:
            instance: Parent model instance
            descriptor: Relationship descriptor
        """
        self.instance = instance
        self.descriptor = descriptor
        self.property = descriptor.property
        self._cached_objects = None
        self._loaded = False

    async def all(self):
        """Get all related objects.

        Returns:
            List of related object instances
        """
        if not self._loaded:
            await self._load()
        return self._cached_objects or []

    def __await__(self):
        """Support await syntax."""
        return self.all().__await__()

    async def _load(self):
        """Load related object list from database - implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement _load method")

    def _set_empty_result(self):
        """Common method to set empty result."""
        self._cached_objects = []
        self._loaded = True


class OneToManyCollection(BaseRelatedCollection):
    """One-to-many related object collection."""

    async def _load(self):
        """Load one-to-many relationship."""
        if not self.property.resolved_model:
            self._set_empty_result()
            return

        instance_pk = self.instance.id
        related_table = self.property.resolved_model.get_table()

        # Infer foreign key field name
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

        query = select(related_table).where(fk_col == instance_pk)  # noqa
        session = self.instance.get_session()
        result = await session.execute(query)

        self._cached_objects = [
            self.property.resolved_model.from_dict(dict(row._mapping), validate=False) for row in result
        ]
        self._loaded = True


class M2MCollectionMixin:
    """Mixin class for M2M collection functionality."""

    # Type hints for mixin attributes
    instance: "ObjectModel"
    property: Any

    def _load_m2m_data(self) -> tuple[Any | None, Any | None, Any | None, Any | None]:
        """Load M2M basic data.

        Returns:
            Tuple of (m2m_def, registry, m2m_table, instance_id)
        """
        m2m_def = self.property.m2m_definition
        if not m2m_def:
            return None, None, None, None

        registry = getattr(self.instance.__class__, "__registry__", None)
        if not registry:
            return None, None, None, None

        m2m_table = registry.get_m2m_table(m2m_def.table_name)
        if not m2m_table:
            return None, None, None, None

        if not m2m_def.left_ref_field:
            return None, None, None, None

        instance_id = getattr(self.instance, m2m_def.left_ref_field)
        if instance_id is None:
            return None, None, None, None

        return m2m_def, registry, m2m_table, instance_id

    def _build_m2m_query(self, m2m_def: Any, m2m_table: Any, instance_id: Any) -> Any:
        """Build M2M query.

        Args:
            m2m_def: M2M table definition
            m2m_table: M2M table instance
            instance_id: Current instance ID

        Returns:
            SQLAlchemy query or None
        """
        if not self.property.resolved_model:
            return None

        related_table = self.property.resolved_model.get_table()

        from sqlalchemy import join

        if not (m2m_def.right_field and m2m_def.right_ref_field and m2m_def.left_field):
            return None

        joined_tables = join(
            m2m_table,
            related_table,
            getattr(m2m_table.c, m2m_def.right_field) == getattr(related_table.c, m2m_def.right_ref_field),  # noqa
        )

        return (
            select(related_table)
            .select_from(joined_tables)
            .where(getattr(m2m_table.c, m2m_def.left_field) == instance_id)  # noqa
        )


class M2MRelatedCollection(BaseRelatedCollection, M2MCollectionMixin):
    """Many-to-many related object collection."""

    async def _load(self) -> None:
        """Load M2M related object list from database."""
        m2m_def, registry, m2m_table, instance_id = self._load_m2m_data()
        if not m2m_def or not registry or not m2m_table or instance_id is None:
            self._set_empty_result()
            return

        query = self._build_m2m_query(m2m_def, m2m_table, instance_id)
        if not query:
            self._set_empty_result()
            return

        session = self.instance.get_session()
        result = await session.execute(query)

        if self.property.resolved_model:
            self._cached_objects = [
                self.property.resolved_model.from_dict(dict(row._mapping), validate=False) for row in result
            ]
        else:
            self._cached_objects = []
        self._loaded = True

    async def add(self, *objects: "ObjectModel") -> None:
        """Add M2M relationships.

        Args:
            *objects: Objects to add to the relationship
        """
        m2m_def, registry, m2m_table, instance_id = self._load_m2m_data()
        if not m2m_def or not registry or not m2m_table or instance_id is None:
            return

        from sqlalchemy import insert

        session = self.instance.get_session()

        if not (m2m_def.right_ref_field and m2m_def.left_field and m2m_def.right_field):
            return

        for obj in objects:
            related_id = getattr(obj, m2m_def.right_ref_field)
            if related_id is not None:
                stmt = insert(m2m_table).values({m2m_def.left_field: instance_id, m2m_def.right_field: related_id})
                await session.execute(stmt)

        # Clear cache
        self._loaded = False
        self._cached_objects = None

    async def remove(self, *objects: "ObjectModel") -> None:
        """Remove M2M relationships.

        Args:
            *objects: Objects to remove from the relationship
        """
        m2m_def, registry, m2m_table, instance_id = self._load_m2m_data()
        if not m2m_def or not registry or not m2m_table or instance_id is None:
            return

        from sqlalchemy import and_, delete

        session = self.instance.get_session()

        if not (m2m_def.right_ref_field and m2m_def.left_field and m2m_def.right_field):
            return

        for obj in objects:
            related_id = getattr(obj, m2m_def.right_ref_field)
            if related_id is not None:
                stmt = delete(m2m_table).where(
                    and_(
                        getattr(m2m_table.c, m2m_def.left_field) == instance_id,
                        getattr(m2m_table.c, m2m_def.right_field) == related_id,
                    )
                )
                await session.execute(stmt)

        # Clear cache
        self._loaded = False
        self._cached_objects = None


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

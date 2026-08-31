import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Union, cast

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy import MetaData as SqlAlchemyMetaData

from .fields import ColumnAttribute
from .fields.relations import M2MTable, RelationshipDescriptor, RelationshipResolver
from .fields.utils import get_column_from_field, is_field_definition
from .utils.naming import to_snake_case
from .utils.pattern import pluralize


if TYPE_CHECKING:
    from .model import ObjectModel

__all__ = [
    "ModelProcessor",
    "ModelRegistry",
    "ModelConfig",
    "index",
    "constraint",
    "unique",
    "foreignkey",
]

_FIELD_NAME_PATTERN = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")
_TEMP_INDEX_PREFIX = "__temp__idx_"


@dataclass
class _RawModelConfig:
    """Raw model configuration with optional fields for parsing phase."""

    table_name: str | None = None
    verbose_name: str | None = None
    verbose_name_plural: str | None = None
    ordering: list[str] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    constraints: list[CheckConstraint | UniqueConstraint | ForeignKeyConstraint] = field(default_factory=list)
    description: str | None = None
    db_options: dict[str, dict[str, Any]] = field(default_factory=dict)
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelConfig:
    """Complete model configuration with all required fields filled."""

    table_name: str
    verbose_name: str
    verbose_name_plural: str
    ordering: list[str] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    constraints: list[CheckConstraint | UniqueConstraint | ForeignKeyConstraint] = field(default_factory=list)
    description: str | None = None
    db_options: dict[str, dict[str, Any]] = field(default_factory=dict)
    custom: dict[str, Any] = field(default_factory=dict)
    field_validators: dict[str, list[Any]] = field(default_factory=dict)
    field_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)


class ModelRegistry(SqlAlchemyMetaData):
    """Unified registry for models, tables, and relationships.

    This class extends SQLAlchemy's MetaData to provide comprehensive
    management of model classes, their database tables, relationships,
    and many-to-many association tables.

    Features:
    - Model class registration and lookup
    - Relationship resolution and management
    - M2M table creation and management
    - Table-to-model mapping
    """

    def __init__(self, bind=None, schema=None, quote_schema=None, naming_convention=None, info=None):
        """Initialize ModelRegistry with SQLAlchemy MetaData configuration.

        Args:
            bind: Database engine or connection
            schema: Default schema name
            quote_schema: Whether to quote schema names
            naming_convention: Naming convention for constraints
            info: Additional metadata information
        """
        super().__init__(schema=schema, quote_schema=quote_schema, naming_convention=naming_convention, info=info)
        if bind is not None:
            self.bind = bind

        # Model management
        self._models: dict[str, type[ObjectModel]] = {}
        self._table_to_model: dict[str, type[ObjectModel]] = {}

        # Relationship management
        self._relationships: dict[str, dict[str, RelationshipDescriptor]] = {}
        self._resolved: bool = False

        # M2M table management
        self._m2m_tables: dict[str, M2MTable] = {}
        self._pending_m2m: list[M2MTable] = []

    # Model registration
    def register_model(self, model_class: type["ObjectModel"]) -> None:
        """Register model class with table and relationships.

        Args:
            model_class: Model class to register
        """
        self._models[model_class.__name__] = model_class

        if hasattr(model_class, "__table__"):
            table = getattr(model_class, "__table__")  # noqa: B009
            if table is not None:
                self._table_to_model[table.name] = model_class

        # Register relationships
        if hasattr(model_class, "_relationships"):
            relationships = getattr(model_class, "_relationships")  # noqa: B009
            if relationships is not None:
                self._relationships[model_class.__name__] = relationships
                self._resolved = False  # Mark for re-resolution

    def get_model(self, name: str) -> type["ObjectModel"] | None:
        """Get model class by name.

        Args:
            name: Model class name

        Returns:
            Model class or None if not found
        """
        return self._models.get(name)

    def get_model_by_table(self, table_name: str) -> type["ObjectModel"] | None:
        """Get model class by table name.

        Args:
            table_name: Database table name

        Returns:
            Model class or None if not found
        """
        return self._table_to_model.get(table_name)

    def list_models(self) -> list[type["ObjectModel"]]:
        """Get all registered models.

        Returns:
            List of all registered model classes
        """
        return list(self._models.values())

    # Relationship resolution
    def resolve_all_relationships(self) -> None:
        """Resolve all model relationships.

        This method resolves string-based relationship references to actual
        model classes and determines relationship types.
        """
        if self._resolved:
            return

        for _, relationships in self._relationships.items():
            for _, descriptor in relationships.items():
                self._resolve_relationship(descriptor)

        self._resolved = True

    def _resolve_relationship(self, descriptor: "RelationshipDescriptor") -> None:
        """Resolve single relationship.

        Args:
            descriptor: Relationship descriptor to resolve
        """
        if isinstance(descriptor.property.argument, str):
            related_model = self._models.get(descriptor.property.argument)
            if related_model:
                descriptor.property.resolved_model = related_model

                # Enhanced relationship type resolution with model context
                self._resolve_relationship_type_with_context(descriptor)

                descriptor.property.relationship_type = RelationshipResolver.resolve_relationship_type(
                    descriptor.property
                )

    def _resolve_relationship_type_with_context(self, descriptor: "RelationshipDescriptor") -> None:
        """Resolve relationship type with model context.

        Args:
            descriptor: Relationship descriptor to resolve
        """
        property_ = descriptor.property

        if property_.uselist is not None:
            return

        # Find current model
        current_model_name = None
        for model_name, relationships in self._relationships.items():
            if descriptor in relationships.values():
                current_model_name = model_name
                break

        if current_model_name and property_.resolved_model:
            current_model = self._models.get(current_model_name)
            if current_model and hasattr(current_model, "__table__"):
                table = current_model.__table__
                target_table_name = property_.resolved_model.__table__.name

                # Check for foreign key to target model
                for col in table.columns:  # noqa
                    for fk in col.foreign_keys:
                        if fk.column.table.name == target_table_name:
                            property_.uselist = False
                            if not property_.foreign_keys:
                                property_.foreign_keys = [col.name]
                            return

                # No FK found, assume one-to-many
                property_.uselist = True

    # M2M table management
    def register_m2m_table(self, m2m_def: "M2MTable") -> None:
        """Register M2M table for delayed creation.

        Args:
            m2m_def: M2M table definition to register
        """
        self._pending_m2m.append(m2m_def)

    def process_pending_m2m(self) -> None:
        """Process all pending M2M table registrations.

        Creates actual database tables for all pending M2M definitions
        where both related models are available.
        """
        for m2m_def in self._pending_m2m:
            self._create_m2m_table(m2m_def)
        self._pending_m2m.clear()

    def _create_m2m_table(self, m2m_def: "M2MTable") -> None:
        """Create M2M table from definition.

        Args:
            m2m_def: M2M table definition to create
        """
        left_model = self.get_model(m2m_def.left_model)
        right_model = self.get_model(m2m_def.right_model)

        if not left_model or not right_model:
            return  # Keep in pending

        left_table = getattr(left_model, "__table__", None)
        right_table = getattr(right_model, "__table__", None)

        if left_table is None or right_table is None:
            return  # Keep in pending

        m2m_def.create_table(self, left_table, right_table)
        self._m2m_tables[m2m_def.table_name] = m2m_def

    def get_m2m_table(self, table_name: str) -> Any | None:
        """Get M2M table by name.

        Args:
            table_name: Name of the M2M table

        Returns:
            SQLAlchemy Table object or None if not found
        """
        return self.tables.get(table_name)

    def get_m2m_definition(self, table_name: str) -> Union["M2MTable", None]:
        """Get M2M table definition by name.

        Args:
            table_name: Name of the M2M table

        Returns:
            M2MTable definition or None if not found
        """
        return self._m2m_tables.get(table_name)


class ModelProcessor(type):
    """Metaclass that processes SQLObjects model definitions with type inference and table construction.

    This metaclass handles the complete model processing pipeline:
    - Type inference from annotations
    - Configuration parsing and validation
    - Table construction with indexes and constraints
    - Dataclass functionality generation
    - Model registration and relationship setup
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        """Create new model class with complete processing pipeline.

        Args:
            name: Class name
            bases: Base classes
            namespace: Class namespace
            **kwargs: Additional keyword arguments

        Returns:
            Processed model class
        """
        # Get or create ModelRegistry based on inheritance pattern
        registry = None

        # Check if this directly inherits from ObjectModel
        direct_objectmodel_bases = [base for base in bases if base.__name__ == "ObjectModel"]

        if direct_objectmodel_bases:
            # Direct ObjectModel inheritance - use ObjectModel's shared registry
            objectmodel_base = direct_objectmodel_bases[0]
            if not hasattr(objectmodel_base, "__registry__"):
                objectmodel_base.__registry__ = ModelRegistry()
            registry = objectmodel_base.__registry__
        else:
            # Inherit from user-defined BaseModel - use BaseModel's registry
            for base in bases:
                if hasattr(base, "__registry__"):
                    registry = base.__registry__
                    break
            if registry is None:
                registry = ModelRegistry()
        # Create class
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Set shared registry
        cls.__registry__ = registry  # type: ignore[reportAttributeAccessIssue]

        # If not abstract class, build table
        if not cls.__dict__.get("__abstract__", False):
            # Parse configuration
            config = _parse_model_config(cls)

            # Set default ordering
            if config.ordering:
                cls._default_ordering = config.ordering  # type: ignore[reportAttributeAccessIssue]

            # Integrate field-level config into model config
            config = mcs._integrate_field_config(cls, config)

            # Register validators
            mcs._register_field_validators(cls, config)

            # Apply dataclass functionality
            cls = mcs._apply_dataclass_functionality(cls)

            # Build table
            table = mcs._build_table(cls, config, registry)
            cls.__table__ = table

            # Bind ColumnAttribute instances to table columns
            mcs._bind_column_attributes_to_table(cls, table)

            # Initialize field cache (after table creation)
            mcs._initialize_field_cache(cls)

            # Normalize index and constraint names after table construction
            mcs._post_process_table_indexes(table, config.table_name)
            mcs._post_process_table_constraints(table, config.table_name)

            # Auto-register model to ModelRegistry
            registry.register_model(cast(type["ObjectModel"], cls))

            # Resolve class name foreign key references to actual table names
            mcs._resolve_class_foreign_keys(registry)

            # Process pending M2M tables
            registry.process_pending_m2m()

            # Resolve relationships after all models are registered
            registry.resolve_all_relationships()

        return cls

    @classmethod
    def _create_column_copy(mcs, original_column, name: str):
        """Create a copy of Column for inheritance."""

        # Creates a new ColumnAttribute instance, not bound to any table
        new_column = ColumnAttribute(
            name=name,
            type_=original_column.type,
            foreign_key=None,
            model_class=None,
            primary_key=getattr(original_column, "primary_key", False),
            nullable=getattr(original_column, "nullable", True),
            default=getattr(original_column, "default", None),
            index=getattr(original_column, "index", False),
            unique=getattr(original_column, "unique", False),
            autoincrement=getattr(original_column, "autoincrement", "auto"),
            doc=getattr(original_column, "doc", None),
            key=getattr(original_column, "key", None),
            onupdate=getattr(original_column, "onupdate", None),
            comment=getattr(original_column, "comment", None),
            system=getattr(original_column, "system", False),
            server_default=getattr(original_column, "server_default", None),
            server_onupdate=getattr(original_column, "server_onupdate", None),
            quote=getattr(original_column, "quote", None),
            info=original_column.info.copy() if hasattr(original_column, "info") and original_column.info else None,
        )

        return new_column

    @classmethod
    def _integrate_field_config(mcs, cls: Any, config: ModelConfig) -> ModelConfig:
        field_indexes, field_validators, field_metadata = mcs._collect_all_field_config(cls, config.table_name)
        config.indexes = field_indexes + config.indexes
        config.field_validators = field_validators
        config.field_metadata = field_metadata
        return config

    @classmethod
    def _collect_all_field_config(
        mcs, cls: Any, table_name: str
    ) -> tuple[list[Index], dict[str, list[Any]], dict[str, dict[str, Any]]]:
        """Collect all field configuration in single pass (performance optimization).

        Args:
            cls: Model class
            table_name: Database table name

        Returns:
            Tuple of (indexes, validators, metadata)
        """
        indexes = []
        validators = {}
        metadata = {}

        try:
            fields = mcs._get_fields(cls)
        except Exception as e:
            raise RuntimeError(f"Failed to get fields for {cls.__name__}: {e}") from e

        for name, field_def in fields.items():
            try:
                if not is_field_definition(field_def):
                    continue

                column = get_column_from_field(field_def)

                # Collect indexes
                if getattr(column, "unique", False) and not getattr(column, "primary_key", False):
                    index_name = f"idx_{table_name}_{name}"
                    indexes.append(Index(index_name, name, unique=True))
                elif getattr(column, "index", False) and not getattr(column, "primary_key", False):
                    index_name = f"idx_{table_name}_{name}"
                    indexes.append(Index(index_name, name))

                # Collect validators
                column_info = getattr(column, "info", None)
                if column_info is not None:
                    field_validators = column_info.get("_enhanced", {}).get("validators")
                    if field_validators:
                        validators[name] = field_validators

                # Collect metadata
                field_meta = {}

                # Collect basic metadata
                column_comment = getattr(column, "comment", None)
                if column_comment is not None:
                    field_meta["comment"] = column_comment
                column_doc = getattr(column, "doc", None)
                if column_doc is not None:
                    field_meta["doc"] = column_doc

                # Collect type information
                column_type = getattr(column, "type", None)
                if column_type is not None:
                    field_meta["type"] = str(column_type)
                field_meta["nullable"] = getattr(column, "nullable", True)
                field_meta["primary_key"] = getattr(column, "primary_key", False)
                field_meta["unique"] = getattr(column, "unique", False)

                # Collect extended parameters
                if column_info is not None:
                    enhanced_params = column_info.get("_enhanced", {})
                    performance_params = column_info.get("_performance", {})
                    codegen_params = column_info.get("_codegen", {})

                    if enhanced_params:
                        field_meta["enhanced"] = enhanced_params
                    if performance_params:
                        field_meta["performance"] = performance_params
                    if codegen_params:
                        field_meta["codegen"] = codegen_params

                if field_meta:
                    metadata[name] = field_meta

            except AttributeError:
                # Field missing expected attributes, skip silently
                continue
            except Exception as e:
                raise RuntimeError(f"Error processing field {name} in {cls.__name__}: {e}") from e

        return indexes, validators, metadata

    @classmethod
    def _register_field_validators(mcs, cls: Any, config: ModelConfig) -> None:
        """Register field-level validators to model class.

        Args:
            cls: Model class
            config: Model configuration containing validators
        """
        if config.field_validators:
            setattr(cls, "_field_validators", config.field_validators)  # noqa: B010

    @classmethod
    def _build_table(mcs, cls: Any, config: ModelConfig, registry):
        """Build SQLAlchemy Core Table and integrate configuration.

        Args:
            cls: Model class
            config: Model configuration
            registry: Model registry for metadata

        Returns:
            SQLAlchemy Table instance
        """
        from sqlalchemy import Table

        # Collect fields with explicit indexes to avoid duplicates
        indexed_fields = set()
        for idx in config.indexes:
            if hasattr(idx, "_columns"):
                for col in idx._columns:
                    if isinstance(col, str):
                        indexed_fields.add(col.split(".")[-1])

        # Collect column definitions and relationship fields
        columns = []
        relationships = {}

        for name, field_def in mcs._get_fields(cls).items():
            if is_field_definition(field_def):
                # Handle relationship fields
                if hasattr(field_def, "_is_relationship") and field_def._is_relationship:  # noqa
                    if hasattr(field_def, "_relationship_descriptor") and field_def._relationship_descriptor:  # noqa
                        relationships[name] = field_def._relationship_descriptor  # noqa
                    continue

                column_attr = get_column_from_field(field_def)
                if column_attr is not None:
                    # Use create_table_column method to get independent Column instance
                    if hasattr(column_attr, "create_table_column"):
                        column = column_attr.create_table_column(name)
                        # Clear index attributes if field has explicit index
                        if name in indexed_fields:
                            column.index = False
                            column.unique = False
                    else:
                        # Fallback for non-ColumnAttribute fields
                        column = column_attr
                        if hasattr(column, "table") and column.table is not None:
                            column = mcs._create_column_copy(column, name)
                        if column.name is None:
                            column.name = name  # type: ignore[reportAttributeAccessIssue]
                    columns.append(column)

        # Store relationships on the class
        if relationships:
            cls._relationships = relationships

        # Build table arguments
        table_args = []
        table_kwargs = {}

        # Add indexes and constraints (already integrated)
        table_args.extend(config.indexes)
        table_args.extend(config.constraints)

        # Handle database-specific options
        if config.db_options:
            for db_name, options in config.db_options.items():
                if db_name == "generic":
                    table_kwargs.update(options)
                else:
                    for key, value in options.items():
                        table_kwargs[f"{db_name}_{key}"] = value

        return Table(config.table_name, registry, *columns, *table_args, **table_kwargs)

    @classmethod
    def _post_process_table_indexes(mcs, table, table_name: str) -> None:
        def col_sig(idx):
            return tuple(sorted(col.name for col in idx.columns)) if idx.columns else None

        def dialect_sig(idx):
            # Dialect kwargs (postgresql_where / postgresql_using / mysql_using, etc.)
            # are part of an index's identity: same columns with different partial
            # predicates or access methods are distinct indexes, not duplicates.
            # Values may be str or SQLAlchemy expressions, so compare via str().
            # dialect_kwargs only holds explicitly passed args, not dialect defaults.
            kwargs = getattr(idx, "dialect_kwargs", None) or {}
            return tuple(sorted((k, str(v)) for k, v in kwargs.items() if v is not None))

        def is_partial(idx):
            return any(k.endswith("_where") for k, _ in dialect_sig(idx))

        full_sig_map: dict[tuple, list] = {}  # (cols, unique, dialect_sig) -> indexes
        col_map: dict[tuple, list] = {}  # cols -> indexes

        for idx in list(table.indexes):
            cs = col_sig(idx)
            if cs is None:
                continue
            full_sig_map.setdefault((cs, getattr(idx, "unique", False), dialect_sig(idx)), []).append(idx)
            col_map.setdefault(cs, []).append(idx)

        to_remove: set = set()

        # Remove exact duplicates (same columns, unique flag, and dialect kwargs):
        # prefer explicit names over SQLAlchemy auto-generated "ix_*". Sort by name
        # so the kept index is deterministic regardless of set iteration order.
        for indexes in full_sig_map.values():
            if len(indexes) > 1:
                explicit = sorted(
                    (i for i in indexes if not (i.name and i.name.startswith("ix_"))),
                    key=lambda i: i.name or "",
                )
                keep = explicit[0] if explicit else sorted(indexes, key=lambda i: i.name or "")[0]
                to_remove.update(i for i in indexes if i is not keep)

        # Remove full-table non-unique when a full-table unique exists on same columns.
        # Partial indexes (unique or not) never participate: a partial unique index
        # only covers rows matching its predicate and cannot replace a full index.
        for indexes in col_map.values():
            if any(getattr(i, "unique", False) and not is_partial(i) for i in indexes):
                to_remove.update(i for i in indexes if not getattr(i, "unique", False) and not is_partial(i))

        for idx in to_remove:
            table.indexes.discard(idx)

        # Normalize temp names after dedup
        for idx in table.indexes:
            if idx.name and idx.name.startswith(_TEMP_INDEX_PREFIX) and idx.columns:
                idx.name = f"idx_{table_name}_{'_'.join(col.name for col in idx.columns)}"

    @classmethod
    def _post_process_table_constraints(mcs, table, table_name: str) -> None:
        """Normalize constraint names after table construction.

        Args:
            table: SQLAlchemy Table instance
            table_name: Database table name
        """
        for cst in table.constraints:
            if cst.name is None:
                if isinstance(cst, CheckConstraint):
                    # Extract field names from condition
                    field_matches = _FIELD_NAME_PATTERN.findall(str(cst.sqltext))
                    if field_matches:
                        field_part = "_".join(field_matches[:2])
                        cst.name = f"ck_{table_name}_{field_part}"
                    else:
                        cst.name = f"ck_{table_name}_constraint"
                elif isinstance(cst, UniqueConstraint) and hasattr(cst, "columns"):
                    field_names = "_".join(col.name for col in cst.columns)
                    cst.name = f"uq_{table_name}_{field_names}"
                elif isinstance(cst, ForeignKeyConstraint) and hasattr(cst, "columns"):
                    # Handle foreign key constraints
                    field_names = "_".join(col.name for col in cst.columns)
                    # Get referenced table and column names
                    if cst.elements:
                        try:
                            ref_table = cst.elements[0].column.table.name
                            ref_columns = "_".join(elem.column.name for elem in cst.elements)
                            cst.name = f"fk_{table_name}_{field_names}_{ref_table}_{ref_columns}"
                        except Exception:
                            # Fallback if reference cannot be resolved yet
                            cst.name = f"fk_{table_name}_{field_names}"
                    else:
                        cst.name = f"fk_{table_name}_{field_names}"

    @classmethod
    def _apply_dataclass_functionality(mcs, cls: Any) -> Any:
        """Apply dataclass functionality to model class.

        Args:
            cls: Model class to enhance

        Returns:
            Enhanced model class with dataclass methods
        """
        # Collect field information for generating dataclass methods
        field_configs = {}
        for name, field_def in mcs._get_fields(cls).items():
            if is_field_definition(field_def):
                column_attr = getattr(cls, name)
                if hasattr(column_attr, "get_codegen_params"):
                    codegen_params = column_attr.get_codegen_params()
                    field_configs[name] = codegen_params

        # Generate dataclass methods if field configs exist
        if field_configs:
            mcs._generate_dataclass_methods(cls, field_configs)

        return cls

    @classmethod
    def _generate_dataclass_methods(mcs, cls: Any, field_configs: dict) -> None:
        """Generate dataclass-style methods.

        Args:
            cls: Model class
            field_configs: Field configuration dictionary
        """
        # Generate __init__ method
        mcs._generate_init_method(cls, field_configs)

        # Generate __repr__ method
        mcs._generate_repr_method(cls, field_configs)

        # Generate __eq__ method
        mcs._generate_eq_method(cls, field_configs)

        # Set standard dataclass compatibility markers
        cls.__dataclass_fields__ = dict.fromkeys(field_configs.keys(), True)
        cls.__dataclass_params__ = {
            "init": True,
            "repr": True,
            "eq": True,
            "order": False,
            "unsafe_hash": False,
            "frozen": False,
        }
        cls.__dataclass_transform__ = True

    @classmethod
    def _generate_init_method(mcs, cls: Any, field_configs: dict) -> None:
        """Generate __init__ method with support for defaults and default_factory.

        Args:
            cls: Model class
            field_configs: Field configuration dictionary
        """
        init_fields = [name for name, config in field_configs.items() if config.get("init", True)]

        if not init_fields:
            return

        # Collect field defaults and factory functions
        field_defaults = {}
        field_factories = {}

        for name in init_fields:
            field_attr = getattr(cls, name)
            if is_field_definition(field_attr):
                column = get_column_from_field(field_attr)

                # Check default_factory first
                if hasattr(field_attr, "get_default_factory"):
                    factory = field_attr.get_default_factory()
                    if factory and callable(factory):
                        field_factories[name] = factory
                        continue

                # Handle SQLAlchemy default values
                if column is not None and column.default is not None:
                    default_value = getattr(column.default, "arg", None)
                    if default_value is not None:
                        field_defaults[name] = default_value
                    elif hasattr(column.default, "is_scalar") and column.default.is_scalar:
                        scalar_value = getattr(column.default, "arg", None)
                        if scalar_value is not None:
                            field_defaults[name] = scalar_value

        def __init__(self, **kwargs):
            # Call parent __init__
            super(cls, self).__init__()

            # Only allow init=True fields as parameters
            for key in kwargs:
                if key not in init_fields:
                    raise TypeError(f"{cls.__name__}.__init__() got an unexpected keyword argument '{key}'")

            # Set field values
            for field_name in init_fields:
                if field_name in kwargs:
                    setattr(self, field_name, kwargs[field_name])
                elif field_name in field_factories:
                    # Call factory function to generate default value
                    setattr(self, field_name, field_factories[field_name]())
                elif field_name in field_defaults:
                    # Use static default value
                    setattr(self, field_name, field_defaults[field_name])

        cls.__init__ = __init__

    @classmethod
    def _generate_repr_method(mcs, cls: Any, field_configs: dict) -> None:
        """Generate __repr__ method.

        Args:
            cls: Model class
            field_configs: Field configuration dictionary
        """
        repr_fields = [name for name, config in field_configs.items() if config.get("repr", True)]

        if not repr_fields:
            return

        def __repr__(self):
            field_strs = []
            for field_name in repr_fields:
                try:
                    value = getattr(self, field_name, None)
                    field_strs.append(f"{field_name}={value!r}")
                except AttributeError:
                    continue
            return f"{cls.__name__}({', '.join(field_strs)})"

        cls.__repr__ = __repr__

    @classmethod
    def _generate_eq_method(mcs, cls: Any, field_configs: dict) -> None:
        """Generate intelligent __eq__ method.

        Args:
            cls: Model class
            field_configs: Field configuration dictionary
        """
        compare_fields = [name for name, config in field_configs.items() if config.get("compare", False)]

        if not compare_fields:
            return

        # Identify primary key fields
        pk_fields = []
        for name in compare_fields:
            field_attr = getattr(cls, name)
            if is_field_definition(field_attr):
                column = get_column_from_field(field_attr)
                if column is not None and getattr(column, "primary_key", False):
                    pk_fields.append(name)

        def __eq__(self, other):
            if not isinstance(other, cls):
                return NotImplemented

            # Smart comparison logic: prioritize primary keys
            if pk_fields:
                self_pk_values = [getattr(self, name, None) for name in pk_fields]
                other_pk_values = [getattr(other, name, None) for name in pk_fields]

                # If all primary keys are not None, compare only primary keys
                if all(v is not None for v in self_pk_values + other_pk_values):
                    return self_pk_values == other_pk_values

                # If some primary keys are None but not all, not equal
                if any(v is not None for v in self_pk_values + other_pk_values):
                    return False

            # Fall back to comparing all compare=True fields
            for field_name in compare_fields:
                try:
                    self_value = getattr(self, field_name, None)
                    other_value = getattr(other, field_name, None)
                    if self_value != other_value:
                        return False
                except AttributeError:
                    return False
            return True

        cls.__eq__ = __eq__

    @classmethod
    def _resolve_class_foreign_keys(mcs, registry):
        """延迟解析外键引用：优先按类名匹配，匹配不到则视为表名。

        foreign_key("User.id") 传入时原样交给 SQLAlchemy（_colspec="User.id"）。
        每次新模型注册后，此方法遍历所有 FK：
        1. 取出 info["_fk_ref"]（即 "." 前的那段，如 "User"）
        2. 尝试在 registry 中按类名查找模型
        3. 找到 → 替换 _colspec 为实际表名，标记 _resolved
        4. 找不到 → 保留原样（视为已经是表名）
        """
        for table in registry.tables.values():
            for col in table.columns:
                for fk in col.foreign_keys:
                    fk_info = fk.info
                    if fk_info.get("_fk_resolved"):
                        continue
                    ref_name = fk_info.get("_fk_ref")
                    if not ref_name:
                        continue
                    model = registry.get_model(ref_name)
                    if not model or not hasattr(model, "__table__"):
                        continue
                    # Found matching model — rewrite _colspec to actual table name
                    actual_table = model.__table__.name
                    schema, tname, colname = fk._column_tokens
                    if tname != actual_table:
                        if schema:
                            fk._colspec = f"{schema}.{actual_table}.{colname}"
                        else:
                            fk._colspec = f"{actual_table}.{colname}"
                        fk.__dict__.pop("_column_tokens", None)
                    fk_info["_fk_resolved"] = True

    @classmethod
    def _bind_column_attributes_to_table(mcs, cls: Any, table) -> None:
        """Bind ColumnAttribute instances to their corresponding table columns.

        Args:
            cls: Model class
            table: SQLAlchemy Table instance
        """
        for name in table.columns.keys():
            for klass in cls.__mro__:
                descriptor = klass.__dict__.get(name)
                if descriptor is not None and hasattr(descriptor, "_column_attribute"):
                    column_attr = descriptor._column_attribute
                    if column_attr is None or not hasattr(column_attr, "__column__"):
                        break
                    if klass is cls:
                        column_attr.__column__ = table.columns[name]
                    else:
                        new_col_attr = object.__new__(type(column_attr))
                        new_col_attr.__dict__.update(column_attr.__dict__)
                        new_col_attr.__column__ = table.columns[name]
                        new_col_attr.model_class = cls
                        new_descriptor = object.__new__(type(descriptor))
                        new_descriptor.__dict__.update(descriptor.__dict__)
                        new_descriptor._column_attribute = new_col_attr
                        type.__setattr__(cls, name, new_descriptor)
                    break

    @classmethod
    def _initialize_field_cache(mcs, cls: Any) -> None:
        """Initialize field cache for performance optimization.

        Args:
            cls: Model class
        """
        cls._field_cache = {"deferred_fields": set(), "relationship_fields": set(), "regular_fields": set()}

        # Get field information from table
        if hasattr(cls, "__table__"):
            table = cls.__table__
            for col_name in table.columns.keys():
                try:
                    attr = getattr(cls, col_name, None)
                    if attr is not None and is_field_definition(attr):
                        column = get_column_from_field(attr)
                        if column is not None and hasattr(column, "info") and column.info is not None:
                            performance_params = column.info.get("_performance", {})
                            if performance_params.get("deferred", False):
                                cls._field_cache["deferred_fields"].add(col_name)
                            else:
                                cls._field_cache["regular_fields"].add(col_name)
                        else:
                            cls._field_cache["regular_fields"].add(col_name)
                except (AttributeError, TypeError):
                    cls._field_cache["regular_fields"].add(col_name)

        # Check relationship fields
        if hasattr(cls, "_relationships"):
            relationships = getattr(cls, "_relationships", {})
            for rel_name in relationships.keys():
                cls._field_cache["relationship_fields"].add(rel_name)

    @classmethod
    def _get_fields(mcs, cls: Any) -> dict[str, Any]:
        """Get class field definitions with enhanced error handling.

        Args:
            cls: Model class

        Returns:
            Dictionary of field name to field definition
        """

        fields = {}

        for base in reversed(cls.__mro__):
            for name, _ in getattr(base, "__dict__", {}).items():
                if name.startswith("_"):
                    continue
                try:
                    attr = getattr(cls, name)
                    if is_field_definition(attr):
                        fields[name] = attr
                except AttributeError:
                    # Attribute not accessible, skip silently
                    continue
                except Exception as e:
                    raise RuntimeError(f"Unexpected error accessing {name} on {cls.__name__}: {e}") from e

        return fields


def _parse_model_config(model_class: Any) -> ModelConfig:
    config_class = getattr(model_class, "Config", None)
    raw = _parse_config_class(config_class) if config_class else _RawModelConfig()

    table_name = raw.table_name or pluralize(to_snake_case(model_class.__name__))
    verbose_name = raw.verbose_name or model_class.__name__
    verbose_name_plural = raw.verbose_name_plural or pluralize(verbose_name)

    return ModelConfig(
        table_name=table_name,
        verbose_name=verbose_name,
        verbose_name_plural=verbose_name_plural,
        ordering=raw.ordering,
        indexes=raw.indexes,
        constraints=raw.constraints,
        description=raw.description,
        db_options=raw.db_options,
        custom=raw.custom,
    )


def _parse_config_class(config_class: type) -> _RawModelConfig:
    return _RawModelConfig(
        table_name=getattr(config_class, "table_name", None),
        verbose_name=getattr(config_class, "verbose_name", None),
        verbose_name_plural=getattr(config_class, "verbose_name_plural", None),
        ordering=getattr(config_class, "ordering", []),
        indexes=getattr(config_class, "indexes", []),
        constraints=getattr(config_class, "constraints", []),
        description=getattr(config_class, "description", None),
        db_options=getattr(config_class, "db_options", {}),
        custom=getattr(config_class, "custom", {}),
    )


# Convenience functions for creating indexes and constraints


def index(
    name: str | None = None,
    *fields: str,
    unique: bool = False,  # noqa
    postgresql_where: str | None = None,
    postgresql_using: str | None = None,
    mysql_using: str | None = None,
    **kwargs: Any,
) -> Index:
    """Create an Index with convenient field name support.

    Args:
        name: Index name (will be normalized to idx_tablename_fields format)
        *fields: Field names as strings
        unique: Whether index should be unique
        postgresql_where: PostgreSQL WHERE clause for partial indexes
        postgresql_using: PostgreSQL index method (btree, hash, gin, gist, etc.)
        mysql_using: MySQL index method (btree, hash)
        **kwargs: Additional SQLAlchemy Index arguments

    Returns:
        SQLAlchemy Index instance

    Examples:
        >>> index("idx_users_email", "email", unique=True)
        >>> index("idx_users_name_age", "name", "age")
        >>> index("idx_users_status", "status", postgresql_where="status = 'active'")
        >>> index("idx_users_tags", "tags", postgresql_using="gin")
    """
    if name is None:
        field_part = "_".join(fields)
        name = f"{_TEMP_INDEX_PREFIX}{field_part}"

    # Build dialect-specific kwargs
    dialect_kwargs = {}
    if postgresql_where is not None:
        dialect_kwargs["postgresql_where"] = postgresql_where
    if postgresql_using is not None:
        dialect_kwargs["postgresql_using"] = postgresql_using
    if mysql_using is not None:
        dialect_kwargs["mysql_using"] = mysql_using

    # Merge with additional kwargs
    dialect_kwargs.update(kwargs)

    return Index(name, *fields, unique=unique, **dialect_kwargs)


def constraint(
    condition: str,
    name: str | None = None,
    **kwargs: Any,
) -> CheckConstraint:
    """Create a CheckConstraint with convenient syntax.

    Args:
        condition: SQL condition expression
        name: Constraint name (optional, will be normalized if needed)
        **kwargs: Additional SQLAlchemy CheckConstraint arguments

    Returns:
        SQLAlchemy CheckConstraint instance

    Examples:
        >>> constraint("age >= 0", "ck_age_positive")
        >>> constraint("length(name) > 0")
        >>> constraint("price > 0 AND price < 10000")
    """
    return CheckConstraint(condition, name=name, **kwargs)


def unique(
    *fields: str,
    name: str | None = None,
    **kwargs: Any,
) -> UniqueConstraint:
    """Create a UniqueConstraint with convenient field name support.

    Args:
        *fields: Field names as strings
        name: Constraint name (optional, will be normalized if needed)
        **kwargs: Additional SQLAlchemy UniqueConstraint arguments

    Returns:
        SQLAlchemy UniqueConstraint instance

    Examples:
        >>> unique("email")
        >>> unique("first_name", "last_name", name="uq_full_name")
    """
    return UniqueConstraint(*fields, name=name, **kwargs)


def foreignkey(
    fields: str | list[str],
    references: str | list[str],
    *,
    name: str | None = None,
    ondelete: str | None = None,
    onupdate: str | None = None,
    deferrable: bool = False,
    initially: str = "IMMEDIATE",
    **kwargs: Any,
) -> ForeignKeyConstraint:
    """Create a ForeignKeyConstraint with convenient field name support.

    Use this in Config.constraints for explicit constraint definition, custom
    names, or composite foreign keys. For simple single-column foreign keys,
    prefer the ``foreign_key()`` field descriptor instead.

    Args:
        fields: Local field name(s) as string or list of strings.
        references: Referenced column(s) as "Table.column" or list thereof.
            Supports class names (e.g. "User.id") or table names (e.g. "users.id").
        name: Constraint name (optional, auto-generated if not provided).
        ondelete: Referential action on delete (CASCADE, SET NULL, RESTRICT, etc.).
        onupdate: Referential action on update.
        deferrable: Whether the constraint can be deferred.
        initially: Initial deferral state ("IMMEDIATE" or "DEFERRED").
        **kwargs: Additional SQLAlchemy ForeignKeyConstraint arguments.

    Returns:
        SQLAlchemy ForeignKeyConstraint instance.

    Examples:
        >>> foreignkey("author_id", "User.id")
        >>> foreignkey("author_id", "User.id", name="fk_posts_author", ondelete="CASCADE")
        >>> foreignkey(["a_id", "b_id"], ["A.id", "B.id"])
    """
    if isinstance(fields, str):
        fields = [fields]
    if isinstance(references, str):
        references = [references]
    return ForeignKeyConstraint(
        fields,
        references,
        name=name,
        ondelete=ondelete,
        onupdate=onupdate,
        deferrable=deferrable or None,
        initially=initially if deferrable else None,
        **kwargs,
    )

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Union, cast

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
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
]


_FIELD_NAME_PATTERN = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")


@dataclass
class _RawModelConfig:
    """Raw model configuration with optional fields for parsing phase."""

    table_name: str | None = None
    verbose_name: str | None = None
    verbose_name_plural: str | None = None
    ordering: list[str] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    constraints: list[CheckConstraint | UniqueConstraint] = field(default_factory=list)
    description: str | None = None
    db_options: dict[str, dict[str, Any]] = field(default_factory=dict)
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelConfig:
    """Complete model configuration with all required fields filled.

    This dataclass holds all configuration options that can be applied to a model,
    including basic settings, database constraints, metadata, and database-specific
    optimizations. All required fields are guaranteed to have values.

    Attributes:
        table_name: Database table name (never None after processing)
        verbose_name: Human-readable singular name for the model (never None)
        verbose_name_plural: Human-readable plural name for the model (never None)
        ordering: Default ordering for queries (e.g., ['-created_at', 'name'])
        indexes: List of database indexes to create for the table
        constraints: List of database constraints (check, unique) for the table
        description: Detailed description of the model's purpose (can be None)
        db_options: Database-specific configuration options by dialect
        custom: Custom configuration values for application-specific use
        field_validators: Field-level validators registry
        field_metadata: Unified field metadata information
    """

    table_name: str
    verbose_name: str
    verbose_name_plural: str
    ordering: list[str] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    constraints: list[CheckConstraint | UniqueConstraint] = field(default_factory=list)
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
                                property_.foreign_keys = col.name
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
        """Integrate field-level configuration into model configuration - optimized version.

        Args:
            cls: Model class
            config: Current model configuration

        Returns:
            Updated model configuration with field-level settings integrated
        """
        # Collect all field configuration in single pass
        field_indexes, field_validators, field_metadata = mcs._collect_all_field_config(cls, config.table_name)

        # Merge indexes (avoid duplicates)
        config.indexes = mcs._merge_indexes(field_indexes, config.indexes, config.table_name)

        # Set validators and metadata
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
    def _merge_indexes(mcs, field_indexes: list[Index], table_indexes: list[Index], table_name: str) -> list[Index]:
        """Merge field-level and table-level indexes, avoiding duplicates.

        Args:
            field_indexes: Indexes generated from field definitions
            table_indexes: Indexes defined at table level
            table_name: Database table name

        Returns:
            Merged list of unique indexes
        """

        def get_index_signature(idx):  # noqa
            if hasattr(idx, "_columns") and idx._columns:  # noqa
                columns = tuple(sorted(str(col) for col in idx._columns))  # noqa
                return (columns, idx.unique)  # noqa
            return None

        # Collect table-level index signatures
        table_signatures = set()
        for idx in table_indexes:
            sig = get_index_signature(idx)
            if sig:
                table_signatures.add(sig)

        # Filter duplicate field-level indexes
        merged_indexes = []
        for idx in field_indexes:
            sig = get_index_signature(idx)
            if sig and sig not in table_signatures:
                merged_indexes.append(idx)

        # Add table-level indexes
        merged_indexes.extend(table_indexes)

        # Normalize all index naming format
        return mcs._normalize_all_indexes(merged_indexes, table_name)

    @classmethod
    def _normalize_all_indexes(mcs, indexes: list[Index], table_name: str) -> list[Index]:
        """Force uniform naming format for all indexes.

        Args:
            indexes: List of indexes to normalize
            table_name: Database table name

        Returns:
            List of indexes with normalized names
        """
        normalized_indexes = []

        for idx in indexes:
            # Get field name list
            if hasattr(idx, "columns") and idx.columns:
                field_names = "_".join(col.name for col in idx.columns)  # noqa
            elif hasattr(idx, "_columns") and idx._columns:  # noqa
                # Handle indexes not yet bound to table
                field_names = "_".join(str(col).split(".")[-1] for col in idx._columns)  # noqa
            else:
                normalized_indexes.append(idx)
                continue

            # Generate standardized name
            new_name = f"idx_{table_name}_{field_names}"

            # Directly modify index name (instead of rebuilding)
            idx.name = new_name  # type: ignore[reportAttributeAccessIssue]
            normalized_indexes.append(idx)

        return normalized_indexes

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
        """Normalize index names after table construction.

        Args:
            table: SQLAlchemy Table instance
            table_name: Database table name
        """
        for idx in table.indexes:
            if hasattr(idx, "columns") and idx.columns:
                field_names = "_".join(col.name for col in idx.columns)
                new_name = f"idx_{table_name}_{field_names}"
                idx.name = new_name

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
    def _bind_column_attributes_to_table(mcs, cls: Any, table) -> None:
        """Bind ColumnAttribute instances to their corresponding table columns.

        Args:
            cls: Model class
            table: SQLAlchemy Table instance
        """
        for name, field_def in mcs._get_fields(cls).items():
            if is_field_definition(field_def) and not getattr(field_def, "_is_relationship", False):
                column_attr = get_column_from_field(field_def)
                if column_attr is not None and hasattr(column_attr, "__column__"):
                    # Update the ColumnAttribute's internal column to reference the table column
                    if name in table.columns:
                        column_attr.__column__ = table.columns[name]  # type: ignore[reportAttributeAccessIssue]

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
        for name in dir(cls):
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
    """Parse complete configuration for a model class.

    Args:
        model_class: Model class to process configuration for

    Returns:
        Complete ModelConfig with all defaults filled
    """
    config_class = getattr(model_class, "Config", None)
    if config_class:
        raw_config = _parse_config_class(config_class)
    else:
        raw_config = _RawModelConfig()

    return _fill_config_defaults(raw_config, model_class)


def _parse_config_class(config_class: type) -> _RawModelConfig:
    """Parse configuration from a Config inner class.

    Args:
        config_class: The Config inner class to parse

    Returns:
        _RawModelConfig instance with parsed configuration
    """
    config = _RawModelConfig()

    # Basic configuration
    config.table_name = getattr(config_class, "table_name", None)
    config.ordering = getattr(config_class, "ordering", [])

    # Index configuration
    config.indexes = getattr(config_class, "indexes", [])

    # Constraint configuration
    config.constraints = getattr(config_class, "constraints", [])

    # Metadata
    config.verbose_name = getattr(config_class, "verbose_name", None)
    config.verbose_name_plural = getattr(config_class, "verbose_name_plural", None)
    config.description = getattr(config_class, "description", None)

    # Database-specific configuration
    config.db_options = getattr(config_class, "db_options", {})

    # Custom configuration
    config.custom = getattr(config_class, "custom", {})

    return config


def _fill_config_defaults(config: _RawModelConfig, model_class: Any) -> ModelConfig:
    """Fill default values for configuration fields that are None.

    Args:
        config: _RawModelConfig instance to fill defaults for
        model_class: Model class to generate defaults from

    Returns:
        ModelConfig instance with defaults filled
    """
    # Fill table_name if not set
    table_name = config.table_name
    if table_name is None:
        snake_case_name = to_snake_case(model_class.__name__)
        table_name = pluralize(snake_case_name)

    # Fill verbose_name if not set
    verbose_name = config.verbose_name
    if verbose_name is None:
        verbose_name = model_class.__name__

    # Fill verbose_name_plural if not set
    verbose_name_plural = config.verbose_name_plural
    if verbose_name_plural is None:
        verbose_name_plural = pluralize(verbose_name)

    # Create complete config with required fields
    return ModelConfig(
        table_name=table_name,
        verbose_name=verbose_name,
        verbose_name_plural=verbose_name_plural,
        ordering=config.ordering,
        indexes=config.indexes,
        constraints=config.constraints,
        description=config.description,
        db_options=config.db_options,
        custom=config.custom,
        field_validators={},
        field_metadata={},
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
    # Note: Don't auto-generate name here because table_name is needed
    # Actual name normalization is handled in _merge_indexes
    if name is None:
        field_part = "_".join(fields)
        name = f"idx_{field_part}"  # Temporary name, will be replaced later

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

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from .utils.naming import to_snake_case
from .utils.pattern import pluralize


__all__ = [
    "ModelConfig",
    "ConfigManager",
    "get_model_config",
    "process_model_config",
    "index",
    "constraint",
    "unique",
    "database_specific",
    "mysql_config",
    "postgresql_config",
    "sqlite_config",
    "multi_db_config",
    "high_performance_mysql",
    "compressed_mysql",
    "read_only_mysql",
    "memory_mysql",
    "high_performance_postgresql",
    "analytics_postgresql",
    "optimized_sqlite",
]


# Constants
_DB_PREFIX_MAPPING = {
    "mysql_": ("mysql", 6),
    "postgresql_": ("postgresql", 11),
    "sqlite_": ("sqlite", 7),
}

_GENERIC_DB_NAME = "generic"

_INDEX_PREFIXES = {
    "unique": "uq",
    "regular": "idx",
}

_CONSTRAINT_PREFIXES = {
    "check": "ck",
    "unique": "uq",
}

_SQLALCHEMY_ATTRS = {
    "abstract": "__abstract__",
    "tablename": "__tablename__",
    "table_args": "__table_args__",
}

_DEFAULT_MYSQL_ENGINE = "InnoDB"
_DEFAULT_CHARSET = "utf8mb4"
_DEFAULT_CONSTRAINT_NAME = "ck_constraint"

_FIELD_NAME_PATTERN = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")


@dataclass
class _RawModelConfig:
    """Raw model configuration with optional fields for parsing phase."""

    table_name: str | None = None
    verbose_name: str | None = None
    verbose_name_plural: str | None = None
    ordering: list[str] = field(default_factory=list)
    abstract: bool = False
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
        abstract: Whether this is an abstract model (no database table created)
        indexes: List of database indexes to create for the table
        constraints: List of database constraints (check, unique) for the table
        description: Detailed description of the model's purpose (can be None)
        db_options: Database-specific configuration options by dialect
        custom: Custom configuration values for application-specific use
    """

    table_name: str
    verbose_name: str
    verbose_name_plural: str
    ordering: list[str] = field(default_factory=list)
    abstract: bool = False
    indexes: list[Index] = field(default_factory=list)
    constraints: list[CheckConstraint | UniqueConstraint] = field(default_factory=list)
    description: str | None = None
    db_options: dict[str, dict[str, Any]] = field(default_factory=dict)
    custom: dict[str, Any] = field(default_factory=dict)


class _ConfigParser:
    """Parser for extracting model configuration from various sources.

    This class handles parsing configuration from multiple sources including
    SQLAlchemy class attributes (__tablename__, __table_args__) and SQLObjects
    Config inner classes, then merges them with proper precedence.
    """

    def parse_config_class(self, config_class: type) -> _RawModelConfig:  # noqa: method mayby static
        """Parse configuration from a Config inner class.

        Extracts all configuration attributes from a Config inner class and
        returns a _RawModelConfig instance with the parsed values.

        Args:
            config_class: The Config inner class to parse

        Returns:
            _RawModelConfig instance with parsed configuration

        Examples:
            >>> class MyModelConfig:
            ...     table_name = "custom_table"
            ...     ordering = ["-created_at"]
            ...     verbose_name = "My Model"
            # This method is used internally by ConfigManager
        """
        config = _RawModelConfig()

        # Basic configuration
        config.table_name = getattr(config_class, "table_name", None)
        config.ordering = getattr(config_class, "ordering", [])
        config.abstract = getattr(config_class, "abstract", False)

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

    def parse_class_attributes(self, model_class: type) -> _RawModelConfig:
        """Parse configuration from SQLAlchemy built-in class attributes.

        Extracts configuration from standard SQLAlchemy attributes like
        __tablename__, __abstract__, and __table_args__.

        Args:
            model_class: The model class to parse attributes from

        Returns:
            _RawModelConfig instance with parsed SQLAlchemy configuration

        Examples:
            >>> class MyModel:
            ...     __tablename__ = "my_table"
            ...     __abstract__ = True
            ...     __table_args__ = (Index("idx_name", "name"),)
            # This method is used internally by ConfigManager
        """
        config = _RawModelConfig()

        # Only parse SQLAlchemy built-in attributes
        config.table_name = getattr(model_class, _SQLALCHEMY_ATTRS["tablename"], None)
        config.abstract = (
            _SQLALCHEMY_ATTRS["abstract"] in model_class.__dict__
            and model_class.__dict__[_SQLALCHEMY_ATTRS["abstract"]]
        )

        # Parse __table_args__ if present
        table_args = getattr(model_class, _SQLALCHEMY_ATTRS["table_args"], None)
        if table_args:
            self._parse_table_args(table_args, config)

        return config

    @staticmethod
    def merge_configs(*configs: _RawModelConfig) -> _RawModelConfig:
        """Merge multiple _RawModelConfig instances with proper precedence.

        Combines multiple configuration sources using the following rules:
        - Basic settings: Later configs override earlier ones
        - Lists (indexes, constraints): All items are combined
        - Metadata: Later configs override earlier ones
        - Database options: Dictionaries are merged, later values override
        - Custom settings: Dictionaries are merged, later values override

        Args:
            *configs: _RawModelConfig instances to merge, in order of precedence

        Returns:
            Single merged _RawModelConfig instance

        Examples:
            >>> config1 = _RawModelConfig(table_name="table1", ordering=["-id"])
            >>> config2 = _RawModelConfig(table_name="table2", verbose_name="Model")
            # This method is used internally by ConfigManager
            # merged.table_name would be "table2" (later wins)
            # merged.ordering would be ["-id"] (from config1)
        """
        merged = _RawModelConfig()

        for config in configs:
            # Basic configuration (last wins)
            if config.table_name is not None:
                merged.table_name = config.table_name
            if config.ordering:
                merged.ordering = config.ordering
            if config.abstract:
                merged.abstract = config.abstract

            # Lists are extended
            merged.indexes.extend(config.indexes)
            merged.constraints.extend(config.constraints)

            # Metadata (last wins)
            if config.verbose_name is not None:
                merged.verbose_name = config.verbose_name
            if config.verbose_name_plural is not None:
                merged.verbose_name_plural = config.verbose_name_plural
            if config.description is not None:
                merged.description = config.description

            # Database-specific (merge dictionaries)
            for db_name, db_config in config.db_options.items():
                if db_name not in merged.db_options:
                    merged.db_options[db_name] = {}
                merged.db_options[db_name].update(db_config)

            # Custom configuration is merged
            merged.custom.update(config.custom)

        return merged

    @staticmethod
    def fill_defaults(config: _RawModelConfig, model_class: type) -> ModelConfig:
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
            abstract=config.abstract,
            indexes=config.indexes,
            constraints=config.constraints,
            description=config.description,
            db_options=config.db_options,
            custom=config.custom,
        )

    def process_complete_config(self, model_class: type) -> ModelConfig:
        """Process complete configuration for a model class.

        This is the main entry point that handles all configuration processing:
        1. Parse class attributes
        2. Parse Config inner class
        3. Merge configurations
        4. Fill default values

        Args:
            model_class: Model class to process configuration for

        Returns:
            Complete ModelConfig with all defaults filled
        """
        configs = [self.parse_class_attributes(model_class)]

        config_class = getattr(model_class, "Config", None)
        if config_class:
            configs.append(self.parse_config_class(config_class))

        merged_config = _ConfigParser.merge_configs(*configs)
        return _ConfigParser.fill_defaults(merged_config, model_class)

    @staticmethod
    def _parse_table_args(table_args: Any, config: _RawModelConfig) -> None:
        """Parse SQLAlchemy __table_args__ tuple for indexes, constraints, and options.

        Extracts indexes, constraints, and database-specific options from the
        __table_args__ tuple and adds them to the configuration.

        Args:
            table_args: The __table_args__ tuple from a model class
            config: RawModelConfig instance to populate with parsed values

        Note:
            Database-specific options are identified by prefixes:
            - mysql_* -> mysql database options
            - postgresql_* -> postgresql database options
            - sqlite_* -> sqlite database options
            - others -> generic options
        """
        if not isinstance(table_args, tuple):
            return

        # Process each argument in the __table_args__ tuple
        for arg in table_args:
            if isinstance(arg, Index):
                # Add index to configuration
                config.indexes.append(arg)
            elif isinstance(arg, CheckConstraint | UniqueConstraint):
                # Add constraint to configuration
                config.constraints.append(arg)
            elif isinstance(arg, dict):
                # Process database-specific options dictionary
                for key, value in arg.items():
                    # Determine database type from option key prefix
                    db_name = _GENERIC_DB_NAME
                    option_name = key

                    for prefix, (name, offset) in _DB_PREFIX_MAPPING.items():
                        if key.startswith(prefix):
                            db_name = name
                            option_name = key[offset:]
                            break

                    # Initialize database options if not exists
                    if db_name not in config.db_options:
                        config.db_options[db_name] = {}
                    # Store the option value
                    config.db_options[db_name][option_name] = value


class ConfigManager:
    """Unified configuration manager for handling complete model configuration lifecycle."""

    def __init__(self):
        self.parser = _ConfigParser()
        self._config_cache: dict[type, ModelConfig] = {}

    def get_config(self, model_class: type) -> ModelConfig:
        """Get model configuration, process and cache if not exists.

        Args:
            model_class: Model class to get configuration for

        Returns:
            ModelConfig object containing all configuration settings
        """
        if model_class not in self._config_cache:
            self.process_model_config(model_class)
        return self._config_cache[model_class]

    def process_model_config(self, model_class: type) -> tuple[ModelConfig, bool]:
        """Process model configuration and cache the result.

        Args:
            model_class: Model class to process configuration for

        Returns:
            Tuple of (complete model configuration, is abstract model)
        """
        # Check cache first
        if model_class in self._config_cache:
            config = self._config_cache[model_class]
            is_abstract = self._is_abstract_model(model_class, config)
            return config, is_abstract

        # Process configuration
        config = self.parser.process_complete_config(model_class)

        # Apply configuration to model class (non-abstract classes)
        is_abstract = self._is_abstract_model(model_class, config)
        if not is_abstract:
            self._apply_config_to_model(model_class, config)

        # Cache configuration
        self._config_cache[model_class] = config
        return config, is_abstract

    def _is_abstract_model(self, model_class: type, config: ModelConfig) -> bool:  # noqa
        """Determine if the model is abstract."""
        return (
            _SQLALCHEMY_ATTRS["abstract"] in model_class.__dict__
            and model_class.__dict__[_SQLALCHEMY_ATTRS["abstract"]]
        ) or config.abstract

    def _apply_config_to_model(self, model_class: type, config: ModelConfig) -> None:
        """Apply configuration to model class."""
        # Set table name
        if config.table_name:
            setattr(model_class, _SQLALCHEMY_ATTRS["tablename"], config.table_name)

        # Set abstract flag
        if config.abstract:
            setattr(model_class, _SQLALCHEMY_ATTRS["abstract"], True)

        # Set default ordering
        if config.ordering:
            model_class._default_ordering = config.ordering

        # Build __table_args__
        self._build_table_args(model_class, config)

    def _build_table_args(self, model_class: type, config: ModelConfig) -> None:  # noqa
        """Build __table_args__ for the model class."""
        table_args = []

        # Preserve existing __table_args__
        existing_args = getattr(model_class, _SQLALCHEMY_ATTRS["table_args"], ())
        if existing_args:
            for arg in existing_args:
                if not isinstance(arg, dict):
                    table_args.append(arg)

        # Add indexes and constraints
        table_args.extend(config.indexes)
        table_args.extend(config.constraints)

        # Add database options
        if config.db_options:
            db_dict = {}
            for db_name, options in config.db_options.items():
                if db_name == _GENERIC_DB_NAME:
                    db_dict.update(options)
                else:
                    for key, value in options.items():
                        db_dict[f"{db_name}_{key}"] = value
            if db_dict:
                table_args.append(db_dict)

        if table_args:
            setattr(model_class, _SQLALCHEMY_ATTRS["table_args"], tuple(table_args))


# Global configuration manager instance
_config_manager = ConfigManager()


# Factory functions for configuration management
def get_model_config(model_class: type) -> ModelConfig:
    """Get model configuration using the global configuration manager.

    This is the recommended way to access model configuration throughout
    the application, as it uses a single global ConfigManager instance.

    Args:
        model_class: Model class to get configuration for

    Returns:
        ModelConfig object containing all configuration settings
    """
    return _config_manager.get_config(model_class)


def process_model_config(model_class: type) -> tuple[ModelConfig, bool]:
    """Process model configuration using the global configuration manager.

    This function is primarily used during model class initialization.

    Args:
        model_class: Model class to process configuration for

    Returns:
        Tuple of (complete model configuration, is abstract model)
    """
    return _config_manager.process_model_config(model_class)


# Convenience functions for creating indexes and constraints


def index(
    name: str | None = None,
    *fields: str,
    unique: bool = False,  # noqa: 'unique' from outer scope
    postgresql_where: str | None = None,
    postgresql_using: str | None = None,
    mysql_using: str | None = None,
    **kwargs: Any,
) -> Index:
    """Create an Index with convenient field name support.

    Args:
        name: Index name (auto-generated if None)
        *fields: Field names as strings
        unique: Whether index should be unique
        postgresql_where: PostgreSQL WHERE clause for partial indexes
        postgresql_using: PostgreSQL index method (btree, hash, gin, gist, etc.)
        mysql_using: MySQL index method (btree, hash)
        **kwargs: Additional SQLAlchemy Index arguments

    Returns:
        SQLAlchemy Index instance

    Examples:
        >>> index("idx_email", "email", unique=True)
        >>> index("idx_name_age", "name", "age")
        >>> index("idx_active_users", "status", postgresql_where="status = 'active'")
        >>> index("idx_tags", "tags", postgresql_using="gin")
    """
    # Auto-generate index name if not provided
    if name is None:
        field_part = "_".join(fields)
        prefix = _INDEX_PREFIXES["unique"] if unique else _INDEX_PREFIXES["regular"]
        name = f"{prefix}_{field_part}"

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
        name: Constraint name (auto-generated if None)
        **kwargs: Additional SQLAlchemy CheckConstraint arguments

    Returns:
        SQLAlchemy CheckConstraint instance

    Examples:
        >>> constraint("age >= 0", "ck_age_positive")
        >>> constraint("length(name) > 0")
        >>> constraint("price > 0 AND price < 10000")
    """
    # Auto-generate constraint name if not provided
    if name is None:
        # Extract field names from condition
        field_matches = _FIELD_NAME_PATTERN.findall(condition)
        if field_matches:
            field_part = "_".join(field_matches[:2])  # Use first 2 fields
            name = f"{_CONSTRAINT_PREFIXES['check']}_{field_part}"
        else:
            name = _DEFAULT_CONSTRAINT_NAME

    return CheckConstraint(condition, name=name, **kwargs)


def unique(
    *fields: str,
    name: str | None = None,
    **kwargs: Any,
) -> UniqueConstraint:
    """Create a UniqueConstraint with convenient field name support.

    Args:
        *fields: Field names as strings
        name: Constraint name (auto-generated if None)
        **kwargs: Additional SQLAlchemy UniqueConstraint arguments

    Returns:
        SQLAlchemy UniqueConstraint instance

    Examples:
        >>> unique("email")
        >>> unique("first_name", "last_name", name="uq_full_name")
    """
    # Auto-generate constraint name if not provided
    if name is None:
        field_part = "_".join(fields)
        name = f"{_CONSTRAINT_PREFIXES['unique']}_{field_part}"

    return UniqueConstraint(*fields, name=name, **kwargs)


def database_specific(**configs: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    """Create database-specific configuration factory function.

    This function creates a configuration factory that can return different
    configurations based on the database dialect being used. It's useful for
    creating models that need different settings for different databases.

    Args:
        **configs: Database-specific configurations where keys are database
                  dialect names ('postgresql', 'mysql', 'sqlite') and values
                  are configuration dictionaries

    Returns:
        Function that takes a dialect name and returns the appropriate configuration

    Examples:
        >>> db_config = database_specific(
        ...     postgresql={"tablespace": "fast_storage"},
        ...     mysql={"engine": "InnoDB", "charset": "utf8mb4"},
        ...     sqlite={"without_rowid": True},
        ... )
        >>> mysql_opts = db_config("mysql")
        >>> postgresql_opts = db_config("postgresql")
    """

    def _get_config_for_dialect(dialect_name: str) -> dict[str, Any]:
        """Get configuration for the specified database dialect.

        Args:
            dialect_name: Name of the database dialect (e.g., 'mysql', 'postgresql', 'sqlite')

        Returns:
            Configuration dictionary for the specified dialect, or empty dict if not found
        """
        return configs.get(dialect_name, {})

    # For now, return a simple function
    # In a real implementation, this would detect the current database dialect
    return _get_config_for_dialect


# Convenient database-specific configuration functions


def mysql_config(
    engine: str = _DEFAULT_MYSQL_ENGINE,
    charset: str = _DEFAULT_CHARSET,
    collate: str | None = None,
    row_format: str | None = None,
    key_block_size: int | None = None,
    auto_increment: int | None = None,
    avg_row_length: int | None = None,  # Expected average row length for MyISAM optimization
    checksum: bool | None = None,  # Maintain live checksum for MyISAM tables (slower writes, faster integrity checks)
    comment: str | None = None,
    connection: str | None = None,
    data_directory: str | None = None,
    delay_key_write: bool | None = None,  # Delay key writes for MyISAM (faster bulk inserts, risk of corruption)
    index_directory: str | None = None,
    insert_method: str | None = None,
    max_rows: int | None = None,
    min_rows: int | None = None,
    pack_keys: bool | str | None = None,  # Pack string keys (True/False/'DEFAULT') - saves space but slower access
    password: str | None = None,
    stats_auto_recalc: bool | None = None,  # Auto recalculate InnoDB statistics when 10% of table changes
    stats_persistent: bool | None = None,  # Store InnoDB statistics persistently across server restarts
    stats_sample_pages: int | None = None,  # Number of index pages to sample for statistics (1-65535)
    tablespace: str | None = None,
    union: str | None = None,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """Create MySQL-specific configuration with comprehensive options.

    Args:
        engine: Storage engine (InnoDB, MyISAM, Memory, Archive, CSV, etc.)
        charset: Character set (utf8, utf8mb4, latin1, ascii, etc.)
        collate: Collation rule (utf8mb4_unicode_ci, utf8mb4_general_ci, etc.)
        row_format: Row format (DYNAMIC, FIXED, COMPRESSED, REDUNDANT, COMPACT)
        key_block_size: Key block size for compressed tables (1, 2, 4, 8, 16)
        auto_increment: Initial AUTO_INCREMENT value
        avg_row_length: Average row length for MyISAM tables
        checksum: Whether to maintain live checksum for MyISAM tables
        comment: Table comment (up to 2048 characters)
        connection: Connection string for federated tables
        data_directory: Data directory path for MyISAM tables
        delay_key_write: Delay key writes for MyISAM tables
        index_directory: Index directory path for MyISAM tables
        insert_method: Insert method for MERGE tables (NO, FIRST, LAST)
        max_rows: Maximum number of rows
        min_rows: Minimum number of rows
        pack_keys: Pack keys option (True, False, 'DEFAULT')
        password: Password for table encryption
        stats_auto_recalc: Auto recalculate statistics for InnoDB
        stats_persistent: Persistent statistics for InnoDB
        stats_sample_pages: Sample pages for InnoDB statistics
        tablespace: Tablespace name for InnoDB
        union: Union tables for MERGE engine
        **kwargs: Additional MySQL table options

    Returns:
        Dictionary with MySQL configuration

    Examples:
        >>> mysql_config(engine="InnoDB", charset="utf8mb4")
        >>> mysql_config(engine="MyISAM", row_format="COMPRESSED", checksum=True)
        >>> mysql_config(engine="InnoDB", tablespace="innodb_file_per_table")
        >>> mysql_config(engine="Memory", max_rows=1000000)
    """
    config = {"engine": engine, "charset": charset}

    # Add optional parameters if provided
    optional_params = {
        "collate": collate,
        "row_format": row_format,
        "key_block_size": key_block_size,
        "auto_increment": auto_increment,
        "avg_row_length": avg_row_length,
        "checksum": checksum,
        "comment": comment,
        "connection": connection,
        "data_directory": data_directory,
        "delay_key_write": delay_key_write,
        "index_directory": index_directory,
        "insert_method": insert_method,
        "max_rows": max_rows,
        "min_rows": min_rows,
        "pack_keys": pack_keys,
        "password": password,
        "stats_auto_recalc": stats_auto_recalc,
        "stats_persistent": stats_persistent,
        "stats_sample_pages": stats_sample_pages,
        "tablespace": tablespace,
        "union": union,
    }

    for key, value in optional_params.items():
        if value is not None:
            config[key] = value

    config.update(kwargs)
    return {"mysql": config}


def postgresql_config(
    tablespace: str | None = None,
    with_oids: bool | None = None,
    fillfactor: int | None = None,  # Page fill factor (10-100) - lower values leave space for updates
    toast_tuple_target: int
    | None = None,  # TOAST compression threshold (128-8160 bytes) - when to compress large values
    parallel_workers: int | None = None,  # Max parallel workers for queries on this table (0-1024)
    autovacuum_enabled: bool | None = None,
    autovacuum_vacuum_threshold: int | None = None,
    autovacuum_vacuum_scale_factor: float
    | None = None,  # Fraction of table size to add to vacuum threshold (0.0-100.0)
    autovacuum_analyze_threshold: int | None = None,
    autovacuum_analyze_scale_factor: float
    | None = None,  # Fraction of table size to add to analyze threshold (0.0-100.0)
    autovacuum_vacuum_cost_delay: int | None = None,
    autovacuum_vacuum_cost_limit: int | None = None,
    autovacuum_freeze_min_age: int
    | None = None,  # Minimum age for freezing tuples (0-1000000000) - prevents premature freezing
    autovacuum_freeze_max_age: int
    | None = None,  # Maximum age before forced vacuum (0-2000000000) - prevents wraparound
    autovacuum_freeze_table_age: int | None = None,
    log_autovacuum_min_duration: int | None = None,
    user_catalog_table: bool | None = None,  # Whether table is a user catalog table (affects system catalog behavior)
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """Create PostgreSQL-specific configuration with comprehensive options.

    Args:
        tablespace: Tablespace name for the table
        with_oids: Whether to create table with OIDs (deprecated in PostgreSQL 12+)
        fillfactor: Fill factor percentage (10-100) for table pages
        toast_tuple_target: Target for TOAST compression (128-8160 bytes)
        parallel_workers: Number of parallel workers for queries
        autovacuum_enabled: Enable/disable autovacuum for this table
        autovacuum_vacuum_threshold: Minimum number of updated/deleted tuples before vacuum
        autovacuum_vacuum_scale_factor: Fraction of table size to add to vacuum threshold
        autovacuum_analyze_threshold: Minimum number of inserted/updated/deleted tuples before analyze
        autovacuum_analyze_scale_factor: Fraction of table size to add to analyze threshold
        autovacuum_vacuum_cost_delay: Cost delay for autovacuum (milliseconds)
        autovacuum_vacuum_cost_limit: Cost limit for autovacuum
        autovacuum_freeze_min_age: Minimum age for freezing tuples
        autovacuum_freeze_max_age: Maximum age before forced vacuum
        autovacuum_freeze_table_age: Age at which to scan whole table for freezing
        log_autovacuum_min_duration: Minimum duration to log autovacuum actions
        user_catalog_table: Whether table is a user catalog table
        **kwargs: Additional PostgreSQL table options

    Returns:
        Dictionary with PostgreSQL configuration

    Examples:
        >>> postgresql_config(tablespace="fast_storage")
        >>> postgresql_config(fillfactor=80, autovacuum_enabled=True)
        >>> postgresql_config(parallel_workers=4, toast_tuple_target=2048)
        >>> postgresql_config(autovacuum_vacuum_scale_factor=0.1)
    """
    config = {}

    # Add optional parameters if provided
    optional_params = {
        "tablespace": tablespace,
        "with_oids": with_oids,
        "fillfactor": fillfactor,
        "toast_tuple_target": toast_tuple_target,
        "parallel_workers": parallel_workers,
        "autovacuum_enabled": autovacuum_enabled,
        "autovacuum_vacuum_threshold": autovacuum_vacuum_threshold,
        "autovacuum_vacuum_scale_factor": autovacuum_vacuum_scale_factor,
        "autovacuum_analyze_threshold": autovacuum_analyze_threshold,
        "autovacuum_analyze_scale_factor": autovacuum_analyze_scale_factor,
        "autovacuum_vacuum_cost_delay": autovacuum_vacuum_cost_delay,
        "autovacuum_vacuum_cost_limit": autovacuum_vacuum_cost_limit,
        "autovacuum_freeze_min_age": autovacuum_freeze_min_age,
        "autovacuum_freeze_max_age": autovacuum_freeze_max_age,
        "autovacuum_freeze_table_age": autovacuum_freeze_table_age,
        "log_autovacuum_min_duration": log_autovacuum_min_duration,
        "user_catalog_table": user_catalog_table,
    }

    for key, value in optional_params.items():
        if value is not None:
            config[key] = value

    config.update(kwargs)
    return {"postgresql": config}


def sqlite_config(
    without_rowid: bool | None = None,
    strict: bool | None = None,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """Create SQLite-specific configuration with comprehensive options.

    Args:
        without_rowid: Create table WITHOUT ROWID (more efficient for certain use cases)
        strict: Enable strict type checking (SQLite 3.37.0+)
        **kwargs: Additional SQLite table options

    Returns:
        Dictionary with SQLite configuration

    Examples:
        >>> sqlite_config(without_rowid=True)
        >>> sqlite_config(strict=True)
        >>> sqlite_config(without_rowid=True, strict=True)

    Notes:
        - WITHOUT ROWID tables are more efficient when:
          * The table has a primary key
          * The primary key is frequently used for lookups
          * The table is read-only or read-mostly
        - STRICT mode enforces type affinity (requires SQLite 3.37.0+)
    """
    config = {}

    # Add optional parameters if provided
    if without_rowid is not None:
        config["without_rowid"] = without_rowid
    if strict is not None:
        config["strict"] = strict

    config.update(kwargs)
    return {"sqlite": config}


def multi_db_config(
    mysql: dict[str, Any] | None = None,
    postgresql: dict[str, Any] | None = None,
    sqlite: dict[str, Any] | None = None,
    generic: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Create multi-database configuration.

    Args:
        mysql: MySQL-specific options
        postgresql: PostgreSQL-specific options
        sqlite: SQLite-specific options
        generic: Generic options applied to all databases

    Returns:
        Dictionary with multi-database configuration

    Examples:
        >>> multi_db_config(
        ...     mysql={"engine": "InnoDB", "charset": "utf8mb4"},
        ...     postgresql={"tablespace": "fast_storage"},
        ...     generic={"comment": "User data table"},
        ... )
    """
    config = {}
    if mysql:
        config["mysql"] = mysql
    if postgresql:
        config["postgresql"] = postgresql
    if sqlite:
        config["sqlite"] = sqlite
    if generic:
        config["generic"] = generic
    return config


# Specialized configuration functions for common use cases


def high_performance_mysql(
    charset: str = _DEFAULT_CHARSET,
    row_format: str = "DYNAMIC",
    stats_persistent: bool = True,
    stats_auto_recalc: bool = True,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """MySQL configuration optimized for high performance.

    Args:
        charset: Character set (default: utf8mb4)
        row_format: Row format (default: DYNAMIC for better compression)
        stats_persistent: Enable persistent statistics
        stats_auto_recalc: Enable automatic statistics recalculation
        **kwargs: Additional MySQL options

    Returns:
        Dictionary with high-performance MySQL configuration

    Examples:
        >>> high_performance_mysql()
        >>> high_performance_mysql(key_block_size=8)
    """
    return mysql_config(
        engine="InnoDB",
        charset=charset,
        row_format=row_format,
        stats_persistent=stats_persistent,
        stats_auto_recalc=stats_auto_recalc,
        **kwargs,
    )


def compressed_mysql(
    charset: str = _DEFAULT_CHARSET,
    row_format: str = "COMPRESSED",
    key_block_size: int = 8,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """MySQL configuration for compressed storage.

    Args:
        charset: Character set (default: utf8mb4)
        row_format: Row format (default: COMPRESSED)
        key_block_size: Key block size for compression (default: 8)
        **kwargs: Additional MySQL options

    Returns:
        Dictionary with compressed MySQL configuration

    Examples:
        >>> compressed_mysql()
        >>> compressed_mysql(key_block_size=4)
    """
    return mysql_config(
        engine=_DEFAULT_MYSQL_ENGINE, charset=charset, row_format=row_format, key_block_size=key_block_size, **kwargs
    )


def read_only_mysql(
    charset: str = _DEFAULT_CHARSET,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """MySQL configuration optimized for read-only tables.

    Args:
        charset: Character set (default: utf8mb4)
        **kwargs: Additional MySQL options

    Returns:
        Dictionary with read-only optimized MySQL configuration

    Examples:
        >>> read_only_mysql()
        >>> read_only_mysql(pack_keys=True)
    """
    return mysql_config(engine="MyISAM", charset=charset, pack_keys=True, **kwargs)


def memory_mysql(
    charset: str = _DEFAULT_CHARSET,
    max_rows: int = 1000000,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """MySQL configuration for in-memory tables.

    Args:
        charset: Character set (default: utf8mb4)
        max_rows: Maximum number of rows (default: 1000000)
        **kwargs: Additional MySQL options

    Returns:
        Dictionary with memory-optimized MySQL configuration

    Examples:
        >>> memory_mysql()
        >>> memory_mysql(max_rows=500000)
    """
    return mysql_config(engine="Memory", charset=charset, max_rows=max_rows, **kwargs)


def high_performance_postgresql(
    fillfactor: int = 90,
    parallel_workers: int = 4,
    autovacuum_enabled: bool = True,
    autovacuum_vacuum_scale_factor: float = 0.1,
    autovacuum_analyze_scale_factor: float = 0.05,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """PostgreSQL configuration optimized for high performance.

    Args:
        fillfactor: Fill factor for better update performance (default: 90)
        parallel_workers: Number of parallel workers (default: 4)
        autovacuum_enabled: Enable autovacuum (default: True)
        autovacuum_vacuum_scale_factor: Vacuum scale factor (default: 0.1)
        autovacuum_analyze_scale_factor: Analyze scale factor (default: 0.05)
        **kwargs: Additional PostgreSQL options

    Returns:
        Dictionary with high-performance PostgreSQL configuration

    Examples:
        >>> high_performance_postgresql()
        >>> high_performance_postgresql(parallel_workers=8)
    """
    return postgresql_config(
        fillfactor=fillfactor,
        parallel_workers=parallel_workers,
        autovacuum_enabled=autovacuum_enabled,
        autovacuum_vacuum_scale_factor=autovacuum_vacuum_scale_factor,
        autovacuum_analyze_scale_factor=autovacuum_analyze_scale_factor,
        **kwargs,
    )


def analytics_postgresql(
    fillfactor: int = 100,
    parallel_workers: int = 8,
    autovacuum_vacuum_scale_factor: float = 0.02,
    autovacuum_analyze_scale_factor: float = 0.01,
    toast_tuple_target: int = 2048,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """PostgreSQL configuration optimized for analytics workloads.

    Args:
        fillfactor: Fill factor for read-heavy workloads (default: 100)
        parallel_workers: Number of parallel workers (default: 8)
        autovacuum_vacuum_scale_factor: Lower vacuum frequency (default: 0.02)
        autovacuum_analyze_scale_factor: More frequent analyze (default: 0.01)
        toast_tuple_target: TOAST compression target (default: 2048)
        **kwargs: Additional PostgreSQL options

    Returns:
        Dictionary with analytics-optimized PostgreSQL configuration

    Examples:
        >>> analytics_postgresql()
        >>> analytics_postgresql(parallel_workers=16)
    """
    return postgresql_config(
        fillfactor=fillfactor,
        parallel_workers=parallel_workers,
        autovacuum_vacuum_scale_factor=autovacuum_vacuum_scale_factor,
        autovacuum_analyze_scale_factor=autovacuum_analyze_scale_factor,
        toast_tuple_target=toast_tuple_target,
        **kwargs,
    )


def optimized_sqlite(
    without_rowid: bool = True,
    strict: bool = True,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """SQLite configuration with modern optimizations.

    Args:
        without_rowid: Use WITHOUT ROWID for better performance (default: True)
        strict: Enable strict type checking (default: True)
        **kwargs: Additional SQLite options

    Returns:
        Dictionary with optimized SQLite configuration

    Examples:
        >>> optimized_sqlite()
        >>> optimized_sqlite(without_rowid=False)
    """
    return sqlite_config(without_rowid=without_rowid, strict=strict, **kwargs)

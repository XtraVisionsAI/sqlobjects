from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import CheckConstraint, Index, UniqueConstraint


__all__ = [
    "ModelConfig",
    "ConfigParser",
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


@dataclass
class ModelConfig:
    """Comprehensive model configuration class for SQLObjects models.

    This dataclass holds all configuration options that can be applied to a model,
    including basic settings, database constraints, metadata, and database-specific
    optimizations. It supports configuration from both class attributes and
    Config inner classes.

    Attributes:
        table_name: Custom database table name (overrides default lowercase class name)
        ordering: Default ordering for queries (e.g., ['-created_at', 'name'])
        abstract: Whether this is an abstract model (no database table created)
        indexes: List of database indexes to create for the table
        constraints: List of database constraints (check, unique) for the table
        verbose_name: Human-readable singular name for the model
        verbose_name_plural: Human-readable plural name for the model
        description: Detailed description of the model's purpose
        permissions: List of permission tuples for access control
        db_options: Database-specific configuration options by dialect
        custom: Custom configuration values for application-specific use

    Examples:
        Basic configuration:
        >>> config = ModelConfig(
        ...     table_name="user_accounts", ordering=["-created_at"], verbose_name="User Account"
        ... )

        With database-specific options:
        >>> config = ModelConfig(
        ...     db_options={
        ...         "mysql": {"engine": "InnoDB", "charset": "utf8mb4"},
        ...         "postgresql": {"tablespace": "fast_storage"},
        ...     }
        ... )
    """

    # Basic configuration
    table_name: str | None = None
    ordering: list[str] = field(default_factory=list)
    abstract: bool = False

    # Index configuration
    indexes: list[Index] = field(default_factory=list)

    # Constraint configuration
    constraints: list[CheckConstraint | UniqueConstraint] = field(default_factory=list)

    # Metadata (Config class only)
    verbose_name: str | None = None
    verbose_name_plural: str | None = None
    description: str | None = None

    # Permissions (Config class only)
    permissions: list[tuple[str, str]] = field(default_factory=list)

    # Database-specific configuration
    db_options: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Custom configuration (Config class only)
    custom: dict[str, Any] = field(default_factory=dict)


class ConfigParser:
    """Parser for extracting model configuration from various sources.

    This class handles parsing configuration from multiple sources including
    SQLAlchemy class attributes (__tablename__, __table_args__) and SQLObjects
    Config inner classes, then merges them with proper precedence.
    """

    def parse_config_class(self, config_class: type) -> ModelConfig:  # noqa: method mayby static
        """Parse configuration from a Config inner class.

        Extracts all configuration attributes from a Config inner class and
        returns a ModelConfig instance with the parsed values.

        Args:
            config_class: The Config inner class to parse

        Returns:
            ModelConfig instance with parsed configuration

        Examples:
            >>> class MyModelConfig:
            ...     table_name = "custom_table"
            ...     ordering = ["-created_at"]
            ...     verbose_name = "My Model"
            >>> parser = ConfigParser()
            >>> config = parser.parse_config_class(MyModelConfig)
        """
        config = ModelConfig()

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

        # Permissions
        config.permissions = getattr(config_class, "permissions", [])

        # Database-specific configuration
        config.db_options = getattr(config_class, "db_options", {})

        # Custom configuration
        config.custom = getattr(config_class, "custom", {})

        return config

    def parse_class_attributes(self, model_class: type) -> ModelConfig:
        """Parse configuration from SQLAlchemy built-in class attributes.

        Extracts configuration from standard SQLAlchemy attributes like
        __tablename__, __abstract__, and __table_args__.

        Args:
            model_class: The model class to parse attributes from

        Returns:
            ModelConfig instance with parsed SQLAlchemy configuration

        Examples:
            >>> class MyModel:
            ...     __tablename__ = "my_table"
            ...     __abstract__ = True
            ...     __table_args__ = (Index("idx_name", "name"),)
            >>> parser = ConfigParser()
            >>> config = parser.parse_class_attributes(MyModel)
        """
        config = ModelConfig()

        # Only parse SQLAlchemy built-in attributes
        config.table_name = getattr(model_class, "__tablename__", None)
        config.abstract = "__abstract__" in model_class.__dict__ and model_class.__dict__["__abstract__"]

        # Parse __table_args__ if present
        table_args = getattr(model_class, "__table_args__", None)
        if table_args:
            self._parse_table_args(table_args, config)

        return config

    def merge_configs(self, *configs: ModelConfig) -> ModelConfig:  # noqa: method mayby static
        """Merge multiple ModelConfig instances with proper precedence.

        Combines multiple configuration sources using the following rules:
        - Basic settings: Later configs override earlier ones
        - Lists (indexes, constraints, permissions): All items are combined
        - Metadata: Later configs override earlier ones
        - Database options: Dictionaries are merged, later values override
        - Custom settings: Dictionaries are merged, later values override

        Args:
            *configs: ModelConfig instances to merge, in order of precedence

        Returns:
            Single merged ModelConfig instance

        Examples:
            >>> config1 = ModelConfig(table_name="table1", ordering=["-id"])
            >>> config2 = ModelConfig(table_name="table2", verbose_name="Model")
            >>> parser = ConfigParser()
            >>> merged = parser.merge_configs(config1, config2)
            >>> merged.table_name  # "table2" (later wins)
            >>> merged.ordering  # ["-id"] (from config1)
        """
        merged = ModelConfig()

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
            merged.permissions.extend(config.permissions)

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

    def _parse_table_args(self, table_args: Any, config: ModelConfig) -> None:  # noqa: method mayby static
        """Parse SQLAlchemy __table_args__ tuple for indexes, constraints, and options.

        Extracts indexes, constraints, and database-specific options from the
        __table_args__ tuple and adds them to the configuration.

        Args:
            table_args: The __table_args__ tuple from a model class
            config: ModelConfig instance to populate with parsed values

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
                    if key.startswith("mysql_"):
                        db_name = "mysql"
                        option_name = key[6:]  # Remove 'mysql_' prefix
                    elif key.startswith("postgresql_"):
                        db_name = "postgresql"
                        option_name = key[11:]  # Remove 'postgresql_' prefix
                    elif key.startswith("sqlite_"):
                        db_name = "sqlite"
                        option_name = key[7:]  # Remove 'sqlite_' prefix
                    else:
                        # Generic option applies to all databases
                        db_name = "generic"
                        option_name = key

                    # Initialize database options if not exists
                    if db_name not in config.db_options:
                        config.db_options[db_name] = {}
                    # Store the option value
                    config.db_options[db_name][option_name] = value


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
        prefix = "uq" if unique else "idx"
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
        # Simple name generation based on condition
        import re

        # Extract field names from condition
        field_matches = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", condition)
        if field_matches:
            field_part = "_".join(field_matches[:2])  # Use first 2 fields
            name = f"ck_{field_part}"
        else:
            name = "ck_constraint"

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
        name = f"uq_{field_part}"

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
    engine: str = "InnoDB",
    charset: str = "utf8mb4",
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
    charset: str = "utf8mb4",
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
    charset: str = "utf8mb4",
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
        engine="InnoDB", charset=charset, row_format=row_format, key_block_size=key_block_size, **kwargs
    )


def read_only_mysql(
    charset: str = "utf8mb4",
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
    charset: str = "utf8mb4",
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

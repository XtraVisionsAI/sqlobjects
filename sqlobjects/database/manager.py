from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


__all__ = [
    "DatabaseConfig",
    "Database",
    "init_db",
    "init_dbs",
    "create_tables",
    "drop_tables",
    "close_db",
    "close_dbs",
    "set_default",
    "get_default",
    "get_database",
]


@dataclass(init=False)
class DatabaseConfig:
    """Database configuration class

    Uses dataclass to automatically generate initialization and other methods.

    Attributes:
        url: Database connection URL
        echo: Whether to print SQL statements
        pool_size: Connection pool size
        max_overflow: Maximum pool overflow count
        pool_timeout: Connection timeout in seconds
        pool_recycle: Connection recycle time in seconds
        engine_kwargs: Additional SQLAlchemy engine parameters

    Examples:
        >>> config = DatabaseConfig(
        ...     url="postgresql+asyncpg://user:pass@localhost/mydb",
        ...     pool_size=10,
        ...     echo=True,
        ...     isolation_level="READ_COMMITTED",
        ... )
    """

    url: str
    echo: bool
    pool_size: int
    max_overflow: int
    pool_timeout: int
    pool_recycle: int
    engine_kwargs: dict[str, Any]

    def __init__(
        self,
        url: str,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        **kwargs: Any,
    ) -> None:
        """Initialize database configuration

        Args:
            url: Database connection URL
            echo: Whether to print SQL statements
            pool_size: Connection pool size
            max_overflow: Maximum pool overflow count
            pool_timeout: Connection timeout in seconds
            pool_recycle: Connection recycle time in seconds
            **kwargs: Additional SQLAlchemy engine parameters
        """
        self.url = url
        self.echo = echo
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.pool_recycle = pool_recycle
        self.engine_kwargs = kwargs


class Database:
    """Single database connection with event handling and table operations

    Represents a single database connection, providing unified event registration
    interface and table operation methods.

    Attributes:
        name: Unique name for the database connection
        config: Database configuration
        engine: SQLAlchemy async engine

    Examples:
        >>> config = DatabaseConfig(url="sqlite+aiosqlite:///test.db")
        >>> db = Database("main", config)
        >>> @db.on("connect")
        ... def on_connect(conn, record):
        ...     print("Database connected")
    """

    def __init__(self, name: str, config: DatabaseConfig) -> None:
        """Initialize database instance

        Args:
            name: Unique name for the database connection
            config: Database configuration
        """
        self.name = name
        self.config = config

        # Build engine parameters
        engine_kwargs: dict[str, Any] = {
            "echo": config.echo,
            **config.engine_kwargs,
        }

        # Add connection pool parameters for non-SQLite databases
        if not config.url.startswith("sqlite"):
            engine_kwargs.update(
                {
                    "pool_size": config.pool_size,
                    "max_overflow": config.max_overflow,
                    "pool_timeout": config.pool_timeout,
                    "pool_recycle": config.pool_recycle,
                }
            )

        # Create async engine
        self.engine: AsyncEngine = create_async_engine(config.url, **engine_kwargs)

    def on(
        self,
        event_name: Literal[
            "connect",
            "close",
            "begin",
            "commit",
            "rollback",
            "before_commit",
            "before_rollback",
            "after_commit",
            "after_rollback",
            "checkout",
            "checkin",
            "invalidate",
            "soft_invalidate",
            "close_detached",
        ],
    ):
        """Unified event registration method

        Args:
            event_name: Event name (connect, close, before_commit, etc.)

        Returns:
            SQLAlchemy event listener decorator

        Examples:
            >>> @db.on("connect")
            ... def on_connect(conn, record):
            ...     print("Database connected")

            >>> @db.on("before_commit")
            ... def before_commit(conn):
            ...     print("About to commit transaction")
        """
        from sqlalchemy import event

        # Automatically select event target
        target = self.engine.sync_engine

        return event.listens_for(target, event_name)

    async def create_tables(self, base_class) -> None:
        """Create all tables defined in the model registry of SQLObjects base class

        Creates all tables, indexes, and constraints defined in the provided
        SQLAlchemy metadata object using the database engine.

        Args:
            base_class: SQLObjects base class containing model registry

        Examples:
            >>> from sqlobjects.base import ObjectModel
            >>> await db.create_tables(ObjectModel)
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(base_class.__registry__.create_all)

    async def drop_tables(self, base_class) -> None:
        """Drop all tables defined in the model registry of SQLObjects base class

        Drops all tables, indexes, and constraints defined in the provided
        SQLAlchemy metadata object from the database.

        Args:
            base_class: SQLObjects base class containing model registry

        Examples:
            >>> from sqlobjects.base import ObjectModel
            >>> await db.drop_tables(ObjectModel)
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(base_class.__registry__.drop_all)

    async def disconnect(self) -> None:
        """Disconnect database and clean up resources

        Properly disposes the SQLAlchemy engine and closes all connections.
        Should be called when the database is no longer needed.
        """
        await self.engine.dispose()


class _DatabaseManager:
    """Internal multi-database connection manager.

    Manages multiple database connections, handles default database selection,
    provides table operations and connection lifecycle management.
    """

    _databases: dict[str, Database] = {}
    _default_db: str | None = None

    @classmethod
    async def add_database(cls, name: str, config: DatabaseConfig, is_default: bool = False) -> Database:
        """Add database connection

        Args:
            name: Unique database name
            config: Database configuration
            is_default: Whether to set as default database

        Returns:
            Created database instance

        Raises:
            ValueError: When database connection fails
        """
        try:
            database = Database(name, config)
            cls._databases[name] = database

            if is_default:
                cls._default_db = name

            return database
        except Exception as e:
            raise RuntimeError(f"Failed to connect to database '{name}': {e}") from e

    @classmethod
    def get_database(cls, db_name: str | None = None) -> Database:
        """Get database instance

        Args:
            db_name: Database name, uses default database when None

        Returns:
            Database instance

        Raises:
            ValueError: When database does not exist
        """
        name = db_name or cls._default_db
        if not name or name not in cls._databases:
            raise ValueError(f"Database '{name}' not found")
        return cls._databases[name]

    @classmethod
    def get_engine(cls, db_name: str | None = None) -> AsyncEngine:
        """Get database engine

        Args:
            db_name: Database name, uses default database when None

        Returns:
            AsyncEngine instance

        Raises:
            ValueError: When database does not exist
        """
        database = cls.get_database(db_name)
        return database.engine

    @classmethod
    async def create_tables(cls, base_class, db_name: str | None = None) -> None:
        """Create all tables defined in the base class registry

        Creates all tables, indexes, and constraints for models registered
        in the base class registry using the specified database connection.

        Args:
            base_class: SQLObjects base class containing model registry
            db_name: Database name to use, uses default database if None

        Raises:
            ValueError: When specified database does not exist

        Examples:
            >>> from sqlobjects.base import ObjectModel
            >>> await DatabaseManager.create_tables(ObjectModel)
            >>> await DatabaseManager.create_tables(ObjectModel, "analytics")
        """
        database = cls.get_database(db_name)
        await database.create_tables(base_class)

    @classmethod
    async def drop_tables(cls, base_class, db_name: str | None = None) -> None:
        """Drop all tables defined in the base class registry

        Drops all tables, indexes, and constraints for models registered
        in the base class registry from the specified database connection.

        Args:
            base_class: SQLObjects base class containing model registry
            db_name: Database name to use, uses default database if None

        Raises:
            ValueError: When specified database does not exist

        Examples:
            >>> from sqlobjects.base import ObjectModel
            >>> await DatabaseManager.drop_tables(ObjectModel)
            >>> await DatabaseManager.drop_tables(ObjectModel, "analytics")
        """
        database = cls.get_database(db_name)
        await database.drop_tables(base_class)

    @classmethod
    async def close(cls, db_name: str | None = None, auto_default: bool = False) -> None:
        """Close database connection and clean up resources

        Closes the specified database connection and removes it from the manager.
        Handles default database reassignment when closing the default database.

        Args:
            db_name: Database name to close, closes default when None
            auto_default: Whether to automatically select new default when closing default database

        Raises:
            ValueError: When specified database does not exist
        """
        # Determine target database name
        target_db = db_name or cls._default_db
        if not target_db or target_db not in cls._databases:
            raise ValueError(f"Database '{target_db}' not found")

        # Close specified database
        await cls._databases[target_db].engine.dispose()
        del cls._databases[target_db]

        # Handle default database change if closing default
        if cls._default_db == target_db:
            if auto_default:
                cls._default_db = next(iter(cls._databases), None)
            else:
                cls._default_db = None

    @classmethod
    async def close_all(cls) -> None:
        """Close all database connections and clean up resources

        Closes all managed database connections, disposes their engines,
        and resets the manager to initial state.
        """
        for _, db in cls._databases.items():
            await db.engine.dispose()

        cls._databases.clear()
        cls._default_db = None

    @classmethod
    def set_default(cls, db_name: str) -> None:
        """Set default database for operations

        Changes the default database used when no specific database
        name is provided in operations.

        Args:
            db_name: Database name to set as default

        Raises:
            ValueError: When database does not exist
        """
        if db_name not in cls._databases:
            raise ValueError(f"Database '{db_name}' not found")

        cls._default_db = db_name

    @classmethod
    def get_default(cls) -> str:
        """Get default database name"""
        if cls._default_db is None:
            raise ValueError("No default database set")
        return cls._default_db


async def init_db(
    url: str,
    name: str | None = None,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_timeout: int = 30,
    pool_recycle: int = 3600,
    is_default: bool = True,
    **engine_kwargs: Any,
) -> Database:
    """Initialize single database connection.

    Args:
        url: Database URL (e.g., 'sqlite+aiosqlite:///db.sqlite', 'postgresql+asyncpg://user:pass@host/db')
        name: Name for the database connection, uses "default" if None
        echo: Whether to log all SQL statements
        pool_size: Number of connections to maintain in the pool
        max_overflow: Maximum number of connections that can overflow the pool
        pool_timeout: Timeout in seconds for getting connection from pool
        pool_recycle: Time in seconds to recycle connections
        is_default: Whether this database should be set as the default database
        **engine_kwargs: Additional SQLAlchemy engine arguments

    Returns:
        Database instance with configured connection

    Raises:
        ValueError: If database URL format is invalid
        DatabaseError: If connection to database fails
        ImportError: If required database driver is not installed
    """
    config = DatabaseConfig(
        url=url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        **engine_kwargs,
    )
    db_name = name if name is not None else "default"
    return await _DatabaseManager.add_database(db_name, config, is_default=is_default)


async def init_dbs(
    databases: Mapping[str, dict[str, Any] | DatabaseConfig],
    default: str | None = None,
) -> tuple[Database, ...]:
    """Initialize multiple database connections.

    Args:
        databases: Dictionary mapping database names to their configurations
        default: Name of the default database to use when none is specified, or None for no default

    Returns:
        Tuple of Database instances in the order they appear in the databases dict

    Raises:
        ValueError: If default database name is not in databases dict or URL format is invalid
        DatabaseError: If connection to any database fails
        ImportError: If required database drivers are not installed
    """
    db_instances = []

    for name, config_data in databases.items():
        if isinstance(config_data, DatabaseConfig):
            config = config_data
        else:
            config = DatabaseConfig(**config_data)

        is_default = default is not None and name == default
        database = await _DatabaseManager.add_database(name, config, is_default)
        db_instances.append(database)

    return tuple(db_instances)


async def create_tables(base_class, db_name: str | None = None) -> None:
    """Create all tables defined in the base class registry

    Creates all tables, indexes, and constraints for models registered
    in the base class registry using the specified database connection.

    Args:
        base_class: SQLObjects base class containing model registry
        db_name: Name of the database, uses default if None

    Raises:
        ValueError: When specified database does not exist
    """
    await _DatabaseManager.create_tables(base_class, db_name)


async def drop_tables(base_class, db_name: str | None = None) -> None:
    """Drop all tables defined in the base class registry

    Drops all tables, indexes, and constraints for models registered
    in the base class registry from the specified database connection.

    Args:
        base_class: SQLObjects base class containing model registry
        db_name: Name of the database, uses default if None

    Raises:
        ValueError: When specified database does not exist
    """
    await _DatabaseManager.drop_tables(base_class, db_name)


async def close_db(db_name: str | None = None, auto_default: bool = False) -> None:
    """Close database connection and clean up resources

    Closes the specified database connection and removes it from the manager.
    Handles default database reassignment when closing the default database.

    Args:
        db_name: Name of specific database to close, closes default if None
        auto_default: Whether to update default database when closing the default database

    Raises:
        ValueError: When specified database does not exist
    """
    await _DatabaseManager.close(db_name, auto_default)


async def close_dbs(db_names: list[str] | None = None, auto_default: bool = False) -> None:
    """Close multiple specific database connections

    Closes all specified database connections in sequence.
    Handles default database reassignment if the default database is closed.

    Args:
        db_names: List of database names to close
        auto_default: Whether to update default database when closing the default database

    Raises:
        ValueError: When any specified database does not exist
    """
    if db_names is None:
        await _DatabaseManager.close_all()
    else:
        for db_name in db_names:
            await _DatabaseManager.close(db_name, auto_default)


def set_default(db_name: str) -> None:
    """Set the default database by name

    Changes the default database used when no specific database
    name is provided in operations.

    Args:
        db_name: Name of the database to set as default

    Raises:
        ValueError: If database is not found
    """
    _DatabaseManager.set_default(db_name)


def get_default() -> str:
    """Get the default database name

    Returns:
        Name of the default database

    Raises:
        ValueError: If no default database is set
    """
    return _DatabaseManager.get_default()


def get_database(db_name: str | None = None) -> Database:
    """Get database instance by name

    Args:
        db_name: Name of the database, uses default if None

    Returns:
        Database instance

    Raises:
        ValueError: If database is not found
    """
    return _DatabaseManager.get_database(db_name)

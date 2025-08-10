from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from .session import SessionContextManager


__all__ = [
    "DatabaseConfig",
    "Database",
    "DatabaseManager",
    "DatabaseObserver",
    "init_db",
    "init_dbs",
    "create_tables",
    "drop_tables",
    "close_db",
    "close_dbs",
    "close_all_dbs",
    "set_default_db",
]


class DatabaseObserver(Protocol):
    """数据库事件观察者协议"""

    def on_database_added(self, name: str, database: "Database", is_default: bool) -> None: ...
    def on_database_removed(self, name: str) -> None: ...
    def on_default_changed(self, old_default: str | None, new_default: str | None) -> None: ...


@dataclass
class DatabaseConfig:
    """数据库配置类

    使用 dataclass 自动生成初始化和其他方法，简化配置管理。

    Attributes:
        url: 数据库连接 URL
        echo: 是否打印 SQL 语句
        pool_size: 连接池大小
        max_overflow: 连接池最大溢出数量
        pool_timeout: 获取连接超时时间（秒）
        pool_recycle: 连接回收时间（秒）
        engine_kwargs: 其他 SQLAlchemy 引擎参数

    Examples:
        >>> config = DatabaseConfig(
        ...     url="postgresql+asyncpg://user:pass@localhost/mydb", pool_size=10, echo=True
        ... )
    """

    url: str
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    engine_kwargs: dict[str, Any] = field(default_factory=dict)


class Database:
    """单个数据库连接，提供事件处理和表操作能力

    代表单个数据库连接，提供统一的事件注册接口和表操作方法。

    Attributes:
        name: 数据库连接的唯一名称
        config: 数据库配置
        engine: SQLAlchemy 异步引擎
        session_factory: 会话工厂

    Examples:
        >>> config = DatabaseConfig(url="sqlite+aiosqlite:///test.db")
        >>> db = Database("main", config)
        >>> @db.on("connect")
        ... def on_connect(conn, record):
        ...     print("数据库已连接")
    """

    def __init__(self, name: str, config: DatabaseConfig) -> None:
        """初始化数据库实例

        Args:
            name: 数据库连接的唯一名称
            config: 数据库配置
        """
        self.name = name
        self.config = config

        # 构建引擎参数
        engine_kwargs: dict[str, Any] = {
            "echo": config.echo,
            **config.engine_kwargs,
        }

        # 为非 SQLite 数据库添加连接池参数
        if not config.url.startswith("sqlite"):
            engine_kwargs.update(
                {
                    "pool_size": config.pool_size,
                    "max_overflow": config.max_overflow,
                    "pool_timeout": config.pool_timeout,
                    "pool_recycle": config.pool_recycle,
                }
            )

        # 创建异步引擎和会话工厂
        self.engine: AsyncEngine = create_async_engine(config.url, **engine_kwargs)
        self.session_factory: async_sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    def on(self, event_name: str, target=None):
        """统一的事件注册方法

        Args:
            event_name: 事件名称 (connect, close, before_commit 等)
            target: 事件目标，默认自动选择

        Returns:
            SQLAlchemy 事件监听器装饰器

        Examples:
            >>> @db.on("connect")
            ... def on_connect(conn, record):
            ...     print("数据库已连接")

            >>> @db.on("before_commit")
            ... def before_commit(session):
            ...     print("即将提交事务")
        """
        from sqlalchemy import event
        from sqlalchemy.orm import Session

        # 自动选择事件目标
        if target is None:
            if event_name in ("before_commit", "after_commit", "before_rollback", "after_rollback"):
                target = Session
            else:
                target = self.engine.sync_engine

        return event.listens_for(target, event_name)

    async def create_tables(self, metadata) -> None:
        """创建表

        Args:
            metadata: SQLAlchemy 元数据对象
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def drop_tables(self, metadata) -> None:
        """删除表

        Args:
            metadata: SQLAlchemy 元数据对象
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)

    async def disconnect(self) -> None:
        """断开数据库连接并清理资源"""
        await self.engine.dispose()


class DatabaseManager:
    """多数据库连接管理器

    管理多个数据库连接，处理默认数据库选择，提供表操作和连接生命周期管理。
    使用观察者模式与 SessionContextManager 解耦。

    Examples:
        >>> manager = DatabaseManager()
        >>> await manager.add_database("main", main_config, is_default=True)
        >>> await manager.add_database("analytics", analytics_config)
        >>> await manager.create_tables(ObjectModel, "main")
    """

    def __init__(self) -> None:
        """初始化数据库管理器"""
        self._databases: dict[str, Database] = {}
        self._default_db: str | None = None
        self._observers: list[DatabaseObserver] = []

    def add_observer(self, observer: DatabaseObserver) -> None:
        """添加观察者"""
        self._observers.append(observer)

    def remove_observer(self, observer: DatabaseObserver) -> None:
        """移除观察者"""
        self._observers.remove(observer)

    def _notify_observers(self, event: str, **kwargs) -> None:
        """通知所有观察者"""
        for observer in self._observers:
            getattr(observer, event)(**kwargs)

    async def add_database(self, name: str, config: DatabaseConfig, is_default: bool = False) -> Database:
        """添加数据库连接

        Args:
            name: 数据库唯一名称
            config: 数据库配置
            is_default: 是否设为默认数据库

        Returns:
            创建的数据库实例

        Raises:
            ValueError: 数据库连接失败时
        """
        try:
            database = Database(name, config)
            self._databases[name] = database

            old_default = self._default_db
            if is_default:
                self._default_db = name

            # 通知观察者
            self._notify_observers("on_database_added", name=name, database=database, is_default=is_default)
            if is_default and old_default != name:
                self._notify_observers("on_default_changed", old_default=old_default, new_default=name)

            return database
        except Exception as e:
            raise ValueError(f"Failed to connect to database '{name}': {e}") from e

    def get_database(self, db_name: str | None = None) -> Database:
        """获取数据库实例

        Args:
            db_name: 数据库名称，None 时使用默认数据库

        Returns:
            数据库实例

        Raises:
            ValueError: 数据库不存在时
        """
        name = db_name or self._default_db
        if not name or name not in self._databases:
            raise ValueError(f"Database '{name}' not found")
        return self._databases[name]

    async def create_tables(self, base_class, db_name: str | None = None) -> None:
        """创建表 - 委托给 Database 实例"""
        database = self.get_database(db_name)
        await database.create_tables(base_class.metadata)

    async def drop_tables(self, base_class, db_name: str | None = None) -> None:
        """删除表 - 委托给 Database 实例"""
        database = self.get_database(db_name)
        await database.drop_tables(base_class.metadata)

    async def close(self, db_name: str | None = None, auto_default: bool = False) -> None:
        """关闭数据库连接

        Args:
            db_name: 要关闭的数据库名称，None 时关闭默认数据库
            auto_default: 关闭默认数据库时是否自动选择新的默认数据库
        """
        # 确定要关闭的数据库名称
        target_db = db_name or self._default_db
        if not target_db or target_db not in self._databases:
            raise ValueError(f"Database '{target_db}' not found")

        # 关闭指定数据库
        await self._databases[target_db].engine.dispose()
        del self._databases[target_db]
        self._notify_observers("on_database_removed", name=target_db)

        # 如果关闭的是默认数据库，处理默认数据库变更
        if self._default_db == target_db:
            old_default = self._default_db
            if auto_default:
                self._default_db = next(iter(self._databases), None)
            else:
                self._default_db = None
            self._notify_observers("on_default_changed", old_default=old_default, new_default=self._default_db)

    async def close_all(self) -> None:
        """关闭所有数据库连接"""
        for name, db in self._databases.items():
            await db.engine.dispose()
            self._notify_observers("on_database_removed", name=name)

        old_default = self._default_db
        self._databases.clear()
        self._default_db = None
        if old_default:
            self._notify_observers("on_default_changed", old_default=old_default, new_default=None)

    def set_default_db(self, db_name: str) -> None:
        """设置默认数据库

        Args:
            db_name: 数据库名称

        Raises:
            ValueError: 数据库不存在时
        """
        if db_name not in self._databases:
            raise ValueError(f"Database '{db_name}' not found")

        old_default = self._default_db
        self._default_db = db_name
        self._notify_observers("on_default_changed", old_default=old_default, new_default=db_name)


# Global database manager instance
_manager = DatabaseManager()

# 注册 SessionContextManager 作为观察者
_manager.add_observer(SessionContextManager)


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
        engine_kwargs=engine_kwargs,
    )
    db_name = name if name is not None else "default"
    return await _manager.add_database(db_name, config, is_default=is_default)


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
        database = await _manager.add_database(name, config, is_default)
        db_instances.append(database)

    return tuple(db_instances)


async def create_tables(base_class, db_name: str | None = None) -> None:
    """Create all tables defined in the base class metadata.

    Args:
        base_class: SQLAlchemy declarative base class containing table metadata
        db_name: Name of the database, uses default if None
    """
    await _manager.create_tables(base_class, db_name)


async def drop_tables(base_class, db_name: str | None = None) -> None:
    """Drop all tables defined in the base class metadata.

    Args:
        base_class: SQLAlchemy declarative base class containing table metadata
        db_name: Name of the database, uses default if None
    """
    await _manager.drop_tables(base_class, db_name)


async def close_db(db_name: str | None = None, auto_default: bool = False) -> None:
    """Close database connection and clean up resources.

    Args:
        db_name: Name of specific database to close, closes default if None
        auto_default: Whether to update default database when closing the default database
    """
    await _manager.close(db_name, auto_default)


async def close_dbs(db_names: list[str], auto_default: bool = False) -> None:
    """Close multiple specific database connections.

    Args:
        db_names: List of database names to close
        auto_default: Whether to update default database when closing the default database
    """
    for db_name in db_names:
        await _manager.close(db_name, auto_default)


async def close_all_dbs() -> None:
    """Close all database connections and clean up resources."""
    await _manager.close_all()


def set_default_db(db_name: str) -> None:
    """Set the default database by name.

    Args:
        db_name: Name of the database to set as default

    Raises:
        ValueError: If database is not found
    """
    _manager.set_default_db(db_name)

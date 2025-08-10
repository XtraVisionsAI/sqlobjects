import asyncio
import contextvars
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase


if TYPE_CHECKING:
    from .database import Database  # noqa


__all__ = [
    "SessionContextManager",
    "ctx_session",
    "ctx_sessions",
]


T = TypeVar("T", bound=DeclarativeBase)

# 显式会话管理（最高优先级）
_explicit_sessions: contextvars.ContextVar[dict[str, AsyncSession]] = contextvars.ContextVar("explicit_sessions")


class SessionContextManager:
    """多数据库会话上下文管理器。

    提供基于 SQLAlchemy async_scoped_session 的自动会话管理和显式会话控制，
    支持多数据库环境下的事务管理和会话隔离。

    核心特性：
    - 自动会话管理：基于 asyncio.current_task 的会话隔离
    - 显式会话控制：通过 ctx_session 进行事务管理
    - 多数据库支持：支持多个数据库的独立会话管理
    - 零维护成本：完全自动的会话生命周期管理

    Examples:
        >>> # 设置数据库会话工厂
        >>> SessionContextManager.set_session_factory(session_factory, "main", is_default=True)
        >>> # 自动会话使用
        >>> session = SessionContextManager.get_session()
        >>> # 显式会话管理
        >>> async with ctx_session() as session:
        ...     await User.objects.create(name="John", session=session)
    """

    _session_factories: dict[str, async_sessionmaker] = {}  # 原始会话工厂
    _scoped_sessions: dict[str, async_scoped_session] = {}  # 自动会话管理
    _default_db: str | None = None

    @classmethod
    def set_session_factory(
        cls, factory: async_sessionmaker, db_name: str = "default", is_default: bool = False
    ) -> None:
        """设置数据库的会话工厂。

        Args:
            factory: SQLAlchemy async_sessionmaker 实例
            db_name: 数据库名称（默认为 "default"）
            is_default: 是否设置为默认数据库

        Examples:
            >>> from sqlalchemy.ext.asyncio import async_sessionmaker
            >>> factory = async_sessionmaker(engine)
            >>> SessionContextManager.set_session_factory(factory, "main", is_default=True)
            >>> SessionContextManager.set_session_factory(analytics_factory, "analytics")
        """
        cls._session_factories[db_name] = factory
        # 创建基于 current_task 的 scoped_session，实现自动隔离和清理
        cls._scoped_sessions[db_name] = async_scoped_session(factory, scopefunc=asyncio.current_task)
        if is_default or cls._default_db is None:
            cls._default_db = db_name

    @classmethod
    def set_session(cls, session: AsyncSession, db_name: str | None = None) -> None:
        """在当前上下文中设置指定数据库的活动会话。

        此方法将会话绑定到当前异步上下文，使其在该上下文内可用于数据库操作。

        Args:
            session: 活动的 AsyncSession 实例
            db_name: 数据库名称（如果为 None 则使用默认数据库）

        Examples:
            >>> async with ctx_session() as session:
            ...     SessionContextManager.set_session(session, "main")
            ...     # 会话现在在此上下文中可用
        """
        name = db_name or cls._default_db or "default"
        try:
            current_sessions = _explicit_sessions.get({})
        except LookupError:
            current_sessions = {}
        new_sessions = current_sessions.copy()
        new_sessions[name] = session
        _explicit_sessions.set(new_sessions)

    @classmethod
    def get_session(cls, db_name: str | None = None) -> AsyncSession:
        """获取指定数据库的活动会话。

        此方法使用以下优先级检索会话：
        1. 显式设置的会话（ctx_session, ctx_sessions）
        2. 自动会话（async_scoped_session，基于 current_task）

        Args:
            db_name: 数据库名称（如果为 None 则使用默认数据库）

        Returns:
            活动的 AsyncSession 实例

        Raises:
            RuntimeError: 如果数据库未初始化

        Examples:
            >>> # 获取默认数据库会话
            >>> session = SessionContextManager.get_session()
            >>> # 获取特定数据库会话
            >>> analytics_session = SessionContextManager.get_session("analytics")
            >>> # 在模型操作中使用
            >>> users = await User.objects.all(session)
        """
        name = db_name or cls._default_db or "default"

        # 第1优先级：显式设置的会话（ctx_session, ctx_sessions）
        try:
            explicit_sessions = _explicit_sessions.get({})
            if name in explicit_sessions:
                return explicit_sessions[name]
        except LookupError:
            pass

        # 第2优先级：scoped_session（自动会话，基于 current_task）
        if name not in cls._scoped_sessions:
            raise RuntimeError(f"Database '{name}' is not initialized")
        return cls._scoped_sessions[name]()

    @classmethod
    def set_default(cls, db_name: str) -> None:
        """按名称设置默认数据库。

        Args:
            db_name: 要设置为默认的数据库名称

        Raises:
            RuntimeError: 如果数据库未注册

        Examples:
            >>> SessionContextManager.set_default("analytics")
            >>> # 现在 analytics 是默认数据库
            >>> session = SessionContextManager.get_session()  # 使用 analytics
        """
        if db_name not in cls._session_factories:
            raise RuntimeError(f"Database '{db_name}' is not initialized")
        cls._default_db = db_name

    @classmethod
    async def remove_scoped_session(cls, db_name: str | None = None) -> None:
        """Remove scoped session for explicit cleanup purposes."""
        name = db_name or cls._default_db or "default"
        if name in cls._scoped_sessions:
            await cls._scoped_sessions[name].remove()

    # DatabaseObserver 协议实现
    @classmethod
    def on_database_added(cls, name: str, database: "Database", is_default: bool) -> None:
        """数据库添加时注册会话工厂"""
        cls.set_session_factory(database.session_factory, name, is_default)

    @classmethod
    def on_database_removed(cls, name: str) -> None:
        """数据库移除时清理会话工厂"""
        if name in cls._session_factories:
            del cls._session_factories[name]
        if name in cls._scoped_sessions:
            del cls._scoped_sessions[name]

    @classmethod
    def on_default_changed(cls, old_default: str | None, new_default: str | None) -> None:
        """默认数据库变更时更新默认设置"""
        cls._default_db = new_default

    @classmethod
    def clear_session(cls, db_name: str | None = None) -> None:
        """从当前上下文中清除指定数据库的活动会话。

        Args:
            db_name: 要清除的数据库名称（如果为 None 则清除所有）

        Examples:
            >>> # 清除特定数据库会话
            >>> SessionContextManager.clear_session("analytics")
            >>> # 清除所有会话
            >>> SessionContextManager.clear_session()
        """
        try:
            current_sessions = _explicit_sessions.get({})
            if db_name:
                if db_name in current_sessions:
                    new_sessions = current_sessions.copy()
                    del new_sessions[db_name]
                    _explicit_sessions.set(new_sessions)
            else:
                _explicit_sessions.set({})
        except LookupError:
            pass


@asynccontextmanager
async def ctx_session(db_name: str | None = None) -> AsyncGenerator[AsyncSession, None]:
    """获取单个数据库会话的异步上下文管理器。

    此函数提供了在异步上下文中使用数据库会话的便捷方式，
    确保正确的事务处理和清理。支持统一事务和独立事务两种模式。

    Args:
        db_name: 数据库名称（如果为 None 则使用默认数据库）

    Yields:
        AsyncSession: 活动的数据库会话

    Examples:
        >>> # 使用默认数据库
        >>> async with ctx_session() as session:
        ...     user = await User.objects.create(name="John", session=session)
        ...     # 会话自动提交和关闭
        >>> # 使用特定数据库
        >>> async with ctx_session("analytics") as session:
        ...     stats = await Stats.objects.all(session)
        >>> # 统一事务模式：子任务共享会话
        >>> async with ctx_session() as session:
        ...     tasks = [asyncio.create_task(process_batch(batch)) for batch in batches]
        ...     await asyncio.gather(*tasks)  # 所有任务共享同一事务
        >>> # 异常处理
        >>> try:
        ...     async with ctx_session() as session:
        ...         await User.objects.create(name="Jane", session=session)
        ...         raise ValueError("Something went wrong")
        ... except ValueError:
        ...     # 会话自动回滚
        ...     pass
    """
    name = db_name or SessionContextManager._default_db or "default"  # noqa

    async with ctx_sessions(name) as sessions:
        yield sessions[name]


@asynccontextmanager
async def ctx_sessions(*db_names: str) -> AsyncGenerator[dict[str, AsyncSession], None]:
    """获取多个数据库会话的异步上下文管理器。

    此函数提供了同时使用多个数据库会话的方式，
    确保所有数据库的一致事务处理，具有正确的提交/回滚语义。

    Args:
        *db_names: 要创建会话的数据库名称。
                  如果为空，则为所有已注册的数据库创建会话。

    Yields:
        dict[str, AsyncSession]: 将数据库名称映射到其会话的字典

    Examples:
        >>> # 使用特定数据库
        >>> async with ctx_sessions("main", "analytics") as sessions:
        ...     # 在主数据库中创建用户
        ...     user = await User.objects.create(name="John", session=sessions["main"])
        ...     # 在分析数据库中记录事件
        ...     await Event.objects.create(user_id=user.id, action="signup", session=sessions["analytics"])
        ...     # 两个会话一起提交
        >>> # 使用所有数据库
        >>> async with ctx_sessions() as sessions:
        ...     for db_name, session in sessions.items():
        ...         print(f"Working with {db_name} database")
        ...         # 对每个会话执行操作
        >>> # 异常处理 - 所有会话回滚
        >>> try:
        ...     async with ctx_sessions("main", "logs") as sessions:
        ...         await User.objects.create(name="Jane", session=sessions["main"])
        ...         await Log.objects.create(message="User created", session=sessions["logs"])
        ...         raise ValueError("Something went wrong")
        ... except ValueError:
        ...     # 两个会话都自动回滚
        ...     pass
    """
    if not db_names:
        db_names = tuple(SessionContextManager._session_factories.keys())  # noqa

    sessions = {}
    token = None

    try:
        for name in db_names:
            if name not in SessionContextManager._session_factories:  # noqa
                raise RuntimeError(f"Database '{name}' is not initialized")
            sessions[name] = SessionContextManager._session_factories[name]()  # noqa

        current_sessions = _explicit_sessions.get({}) if _explicit_sessions else {}
        new_sessions = current_sessions.copy()
        new_sessions.update(sessions)
        token = _explicit_sessions.set(new_sessions)

        yield sessions

        for session in sessions.values():
            await session.commit()

    except Exception:
        for session in sessions.values():
            try:
                await session.rollback()
            except Exception:  # noqa
                pass
        raise
    finally:
        if token:
            _explicit_sessions.reset(token)
        for session in sessions.values():
            try:
                await session.close()
            except Exception:  # noqa
                pass

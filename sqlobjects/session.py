import contextvars
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import CursorResult
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncResult

from .database.manager import get_database, get_default
from .exceptions import convert_sqlalchemy_error


__all__ = ["AsyncSession", "ctx_session", "ctx_sessions", "get_session"]


# Explicit session management (highest priority)
_explicit_sessions: contextvars.ContextVar[dict[str, "AsyncSession"]] = contextvars.ContextVar("explicit_sessions")


class AsyncSession:
    """Async database session with smart connection and transaction management.

    Two main usage patterns:
    - Explicit sessions (ctx_session): auto_commit=False, manual transaction control
    - Implicit sessions (get_session): auto_commit=True, automatic transaction commit
    """

    def __init__(self, db_name: str, readonly: bool = True, auto_commit: bool = True):
        """Initialize AsyncSession with lazy connection.

        Args:
            db_name: Database name
            readonly: True for readonly (no transaction), False for transactional
            auto_commit: True to auto-commit transactions (ignored if readonly=True)
        """
        self._db_name = db_name
        self.readonly = readonly
        self.auto_commit = auto_commit and not readonly  # readonly sessions never auto-commit
        self._conn: AsyncConnection | None = None
        self._trans = None

    @property
    def db_name(self) -> str:
        """Database name for this session."""
        return self._db_name

    @property
    def is_active(self) -> bool:
        """Check if session has an active connection."""
        return self._conn is not None and not self._conn.closed

    @property
    def in_transaction(self) -> bool:
        """Check if session is currently in a transaction."""
        return self._trans is not None and self._trans.is_active

    @property
    def bind(self):
        """Get the engine/connection bind for dialect access."""
        if self._conn:
            return self._conn
        # Return engine if no connection yet
        return get_database(self._db_name).engine

    async def execute(self, statement: Any, parameters: Any = None) -> CursorResult[Any]:
        """Execute statement with automatic transaction management."""
        await self._ensure_connection()

        # Auto-begin transaction for non-readonly sessions
        if not self.readonly and self._trans is None:
            self._trans = await self._conn.begin()  # type: ignore

        try:
            result = await self._conn.execute(statement, parameters)  # type: ignore

            # Auto-commit for implicit sessions
            if self.auto_commit:
                await self.commit()

            return result
        except Exception as e:
            await self._handle_exception(e)
        finally:
            # Auto-close connection for implicit sessions to prevent resource leaks
            if self.auto_commit:
                await self.close()

    async def stream(self, statement: Any, parameters: Any = None) -> AsyncResult[Any]:
        """Execute statement and return streaming result.

        Note: stream() is not supported with auto_commit=True sessions.
        Use explicit sessions (ctx_session) for streaming operations.
        """
        if self.auto_commit:
            raise ValueError(
                "stream() not supported with auto_commit=True. Use ctx_session() or explicit session management."
            )

        await self._ensure_connection()

        # Auto-begin transaction for non-readonly sessions
        if not self.readonly and self._trans is None:
            self._trans = await self._conn.begin()  # type: ignore

        try:
            return await self._conn.stream(statement, parameters)  # type: ignore
        except Exception as e:
            await self._handle_exception(e)

    async def commit(self):
        """Commit transaction if exists and not readonly."""
        if self._trans and not self.readonly:
            await self._trans.commit()
            self._trans = None

    async def rollback(self):
        """Rollback transaction if exists and not readonly."""
        if self._trans and not self.readonly:
            await self._trans.rollback()
            self._trans = None

    async def close(self):
        """Close session and cleanup resources."""
        if self._trans:
            try:
                await self._trans.rollback()
            except Exception:  # noqa
                pass
            finally:
                self._trans = None

        if self._conn:
            try:
                await self._conn.close()
            except Exception:  # noqa
                pass
            finally:
                self._conn = None

    async def begin_nested(self):
        """Begin nested transaction (savepoint)."""
        await self._ensure_connection()
        if not self._trans:
            self._trans = await self._conn.begin()  # type: ignore
        return await self._conn.begin_nested()  # type: ignore

    async def _ensure_connection(self):
        """Ensure connection is available with health check."""
        if self._conn is None or self._conn.closed:
            engine = get_database(self._db_name).engine
            self._conn = await engine.connect()
        elif self._conn.invalidated:
            await self._conn.close()
            engine = get_database(self._db_name).engine
            self._conn = await engine.connect()

    async def _handle_exception(self, exc: Exception):
        """Handle exceptions with unified error processing."""
        await self.rollback()
        if isinstance(exc, SQLAlchemyError):
            raise convert_sqlalchemy_error(exc) from exc
        raise

    async def __aenter__(self) -> "AsyncSession":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit with safe cleanup."""
        try:
            await self.close()
        except Exception:  # noqa
            if exc_type is None:
                raise
            # Ignore cleanup exceptions when original exception exists

    def __getattr__(self, name: str) -> Any:
        """Proxy AsyncConnection methods."""
        if self._conn and hasattr(self._conn, name):
            return getattr(self._conn, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class _SessionContextManager:
    """Internal multi-database session context manager.

    Provides automatic session management based on SQLAlchemy Core,
    supporting both readonly and transactional modes with intelligent session reuse.

    Examples:
        >>> # Get readonly session (optimized for SELECT)
        >>> async with SessionContextManager.get_session(readonly=True) as session:
        ...     result = await session.execute(text("SELECT 1"))
        >>> # Get transactional session with auto-commit
        >>> async with SessionContextManager.get_session(readonly=False) as session:
        ...     await session.execute(text("UPDATE users SET status='active'"))
    """

    @classmethod
    def get_session(cls, db_name: str | None = None, readonly: bool = True, auto_commit: bool = True) -> AsyncSession:
        """Get database session with readonly optimization.

        Args:
            db_name: Database name (uses default database if None)
            readonly: True for readonly (no transaction), False for transactional
            auto_commit: True to auto-commit after each operation (ignored if readonly=True)

        Returns:
            AsyncSession instance

        Priority:
            - First try use explicitly set session (ctx_session, ctx_sessions)
            - Create a new AsyncSession with specified parameters if no explicit session
        """
        name = db_name or get_default()

        # Try use explicitly set session first
        try:
            explicit_sessions = _explicit_sessions.get({})
            if name in explicit_sessions:
                return explicit_sessions[name]
        except LookupError:
            pass

        # Create new session as fallback
        return AsyncSession(name, readonly, auto_commit)

    @classmethod
    def set_session(cls, session: AsyncSession, db_name: str | None = None) -> None:
        """Set active session in current context."""
        name = db_name or get_default()
        try:
            current_sessions = _explicit_sessions.get({})
        except LookupError:
            current_sessions = {}
        new_sessions = current_sessions.copy()
        new_sessions[name] = session
        _explicit_sessions.set(new_sessions)

    @classmethod
    def clear_session(cls, db_name: str | None = None) -> None:
        """Clear active session from current context."""
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
    """Get async context manager for single database transactional session.

    Creates a transactional session with manual commit control (auto_commit=False).
    Transaction is automatically committed on successful exit or rolled back on exception.

    Args:
        db_name: Database name (uses default database if None)

    Yields:
        AsyncSession: Transactional session with manual commit control
    """
    name = db_name or get_default()
    session = AsyncSession(name, readonly=False, auto_commit=False)

    # Set as explicit session in context
    _SessionContextManager.set_session(session, name)

    try:
        yield session
        # Auto-commit on successful exit
        await session.commit()
    except Exception:
        # Auto-rollback on exception
        await session.rollback()
        raise
    finally:
        # Cleanup
        await session.close()
        _SessionContextManager.clear_session(name)


@asynccontextmanager
async def ctx_sessions(*db_names: str) -> AsyncGenerator[dict[str, AsyncSession], None]:
    """Get async context manager for multiple database transactional sessions.

    Creates transactional sessions for multiple databases with manual commit control.
    All transactions are automatically committed on successful exit or rolled back on exception.

    Args:
        *db_names: Database names

    Yields:
        dict[str, AsyncSession]: Dictionary mapping database names to sessions
    """
    if not db_names:
        raise ValueError("At least one database name must be provided")

    sessions: dict[str, AsyncSession] = {}

    try:
        # Create sessions for all
        for db_name in db_names:
            session = AsyncSession(db_name, readonly=False, auto_commit=False)
            sessions[db_name] = session
            _SessionContextManager.set_session(session, db_name)

        yield sessions

        # Auto-commit all sessions on successful exit
        for session in sessions.values():
            await session.commit()

    except Exception:
        # Auto-rollback all sessions on exception
        for session in sessions.values():
            await session.rollback()
        raise

    finally:
        # Cleanup all sessions
        for db_name, session in sessions.items():
            await session.close()
            _SessionContextManager.clear_session(db_name)


def get_session(db_name: str | None = None, readonly: bool = True, auto_commit: bool = True) -> AsyncSession:
    """Get database session with readonly optimization.

    Args:
        db_name: Database name (uses default database if None)
        readonly: True for readonly (no transaction), False for transactional
        auto_commit: True to auto-commit transactions (ignored if readonly=True)

    Returns:
        AsyncSession instance

    Priority:
        - First try use explicitly set session (ctx_session, ctx_sessions)
        - Create a new AsyncSession with specified parameters if no explicit session
    """
    return _SessionContextManager.get_session(db_name, readonly, auto_commit)

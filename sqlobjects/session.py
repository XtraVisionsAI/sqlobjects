from __future__ import annotations

import asyncio
import contextvars
import inspect
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncResult, AsyncTransaction

from .database.manager import get_database, get_default
from .exceptions import TransactionError, convert_sqlalchemy_error


__all__ = ["AsyncSession", "ctx_session", "ctx_sessions", "get_session", "has_session", "on_commit"]

logger = logging.getLogger("sqlobjects.session")

# Explicit session management (highest priority)
_explicit_sessions: contextvars.ContextVar[dict[str, AsyncSession]] = contextvars.ContextVar("explicit_sessions")


def _current_task() -> asyncio.Task[Any] | None:
    """Allow session construction and context inspection outside an event loop."""
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


@dataclass
class _CommitHook:
    callback: Callable[[], Any]
    robust: bool
    savepoints: tuple[_SessionSavepoint, ...] = ()


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
        self._rollback_only = False
        self._owner_task = _current_task()
        self._closed = False
        self._commit_hooks: list[_CommitHook] = []
        self._savepoints: list[_SessionSavepoint] = []
        self._running_commit_hooks = False

    def _usable_in_current_task(self) -> bool:
        return not self._closed and (
            self._owner_task is None or self._owner_task is _current_task() or self._owner_task.done()
        )

    def _check_owner(self) -> None:
        """Reject concurrent sharing before touching a connection or transaction."""
        if self._closed:
            raise TransactionError("Session is closed; open a new ctx_session()")
        task = _current_task()
        if self._owner_task is None or self._owner_task.done():
            # Sequential handoff is safe once the previous task has finished.
            self._owner_task = task
        elif self._owner_task is not task:
            raise TransactionError(
                "Session belongs to another asyncio task; open a separate ctx_session() in each task"
            )

    def _check_database_operation(self) -> None:
        self._check_owner()
        if self._running_commit_hooks:
            raise TransactionError("An on_commit callback must use a new session for database operations")

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
        """Execute statement with automatic transaction management.

        Supports both SQLAlchemy statement objects and raw SQL strings.
        Raw SQL strings are automatically wrapped with text().
        """
        self._check_database_operation()
        if self._rollback_only:
            raise TransactionError("Transaction failed; roll it back before executing more statements")
        if self.readonly and getattr(statement, "is_dml", False):
            raise TransactionError("Cannot execute a write using a readonly session")
        await self._ensure_connection()
        assert self._conn is not None

        # Auto-wrap string SQL with text()
        if isinstance(statement, str):
            statement = text(statement)

        # Auto-begin transaction for non-readonly sessions
        if not self.readonly and self._trans is None:
            self._trans = await self._conn.begin()

        try:
            try:
                result = await self._conn.execute(statement, parameters)
            except Exception as e:
                await self._handle_exception(e)
                raise

            # Auto-commit for implicit sessions
            if self.auto_commit and not self._conn.in_nested_transaction():
                await self.commit()

            # Buffer rows before closing so the connection can be returned to the pool.
            # Readonly sessions only run SELECT queries, so freeze()() is safe.
            # Write sessions with auto_commit need rowcount/inserted_primary_key which
            # are already captured in the CursorResult before close() is called.
            if self.readonly:
                result = result.freeze()()

            return result  # type: ignore[return-value]
        finally:
            # Auto-close connection for implicit sessions to prevent resource leaks
            # This covers both auto_commit write sessions and readonly sessions
            if (self.auto_commit or self.readonly) and self._conn and not self._conn.in_nested_transaction():
                await self._release_connection()

    async def stream(self, statement: Any, parameters: Any = None) -> AsyncResult[Any]:
        """Execute statement and return streaming result.

        Supports both SQLAlchemy statement objects and raw SQL strings.
        Raw SQL strings are automatically wrapped with text().

        Note: stream() is not supported with auto_commit=True sessions.
        Use explicit sessions (ctx_session) for streaming operations.
        """
        self._check_database_operation()
        if self._rollback_only:
            raise TransactionError("Transaction failed; roll it back before executing more statements")
        if self.auto_commit:
            raise ValueError(
                "stream() not supported with auto_commit=True. Use ctx_session() or explicit session management."
            )

        await self._ensure_connection()

        # Auto-wrap string SQL with text()
        if isinstance(statement, str):
            statement = text(statement)

        # Auto-begin transaction for non-readonly sessions
        if not self.readonly and self._trans is None:
            self._trans = await self._conn.begin()  # type: ignore

        try:
            return await self._conn.stream(statement, parameters)  # type: ignore
        except Exception as e:
            await self._handle_exception(e)

    async def commit(self):
        """Commit transaction if exists and not readonly."""
        self._check_database_operation()
        if self._rollback_only:
            raise TransactionError("Cannot commit a failed transaction; roll it back")
        try:
            if self._trans and not self.readonly:
                await self._trans.commit()
                self._trans = None
        except BaseException:
            self._commit_hooks.clear()
            self._rollback_only = True
            raise
        self._savepoints.clear()
        if self._commit_hooks:
            hooks, self._commit_hooks = self._commit_hooks, []
            # Return the connection first, including for pools with only one slot.
            await self._release_connection()
            await self._run_commit_hooks(hooks)

    async def on_commit(self, callback: Callable[[], Any], *, robust: bool = False) -> None:
        """Await a callback after commit, or immediately outside a write transaction.

        Explicit writable sessions queue callbacks even before the first SQL
        statement. Pass a callable, not an already-created coroutine. Rollback
        discards callbacks; robust=True logs ordinary errors and continues.
        """
        self._check_owner()
        if not callable(callback):
            raise TypeError("on_commit requires a callable")
        if self.readonly or self._rollback_only:
            raise TransactionError("on_commit requires a writable, non-failed session")
        hook = _CommitHook(callback, robust, tuple(self._savepoints))
        if self._running_commit_hooks or (self.auto_commit and not self.in_transaction):
            await self._run_commit_hook(hook)
        else:
            self._commit_hooks.append(hook)

    @staticmethod
    async def _run_commit_hook(hook: _CommitHook) -> None:
        try:
            result = hook.callback()
            if inspect.isawaitable(result):
                await result
        except Exception:
            if not hook.robust:
                raise
            name = getattr(hook.callback, "__qualname__", type(hook.callback).__name__)
            logger.exception("Error in on_commit callback %s", name)

    async def _run_commit_hooks(self, hooks: list[_CommitHook]) -> None:
        # ORM calls in a callback must not join a transaction that has just ended.
        sessions = _explicit_sessions.get({}).copy()
        sessions.pop(self.db_name, None)
        token = _explicit_sessions.set(sessions)
        self._running_commit_hooks = True
        try:
            for hook in hooks:
                await self._run_commit_hook(hook)
        finally:
            self._running_commit_hooks = False
            _explicit_sessions.reset(token)

    async def rollback(self):
        """Rollback transaction if exists and not readonly."""
        self._check_database_operation()
        self._commit_hooks.clear()
        self._savepoints.clear()
        if self._trans and not self.readonly:
            await self._trans.rollback()
            self._trans = None
        self._rollback_only = False

    @asynccontextmanager
    async def transaction(self):
        """Join an explicit transaction, or own a transaction for a compound operation."""
        self._check_database_operation()
        if self.readonly:
            raise TransactionError("A write transaction requires a writable session")
        if self.auto_commit:
            async with ctx_session(self.db_name) as session:
                yield session
        else:
            yield self

    async def close(self):
        """Close session and cleanup resources."""
        if self._closed:
            return
        self._check_database_operation()
        try:
            await self._release_connection()
        finally:
            self._closed = True
            self._owner_task = None

    async def _release_connection(self):
        """Release resources without ending a reusable implicit session's lifetime."""
        self._commit_hooks.clear()
        self._savepoints.clear()
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
        self._check_database_operation()
        if self._rollback_only or self.readonly:
            raise TransactionError("Cannot create a savepoint in a failed or readonly session")
        await self._ensure_connection()
        if not self._trans:
            self._trans = await self._conn.begin()  # type: ignore
        assert self._conn is not None
        # SQLite legacy mode may have a logical transaction but no physical BEGIN yet.
        if self._conn.dialect.name == "sqlite":
            sync_connection = self._conn.sync_connection
            assert sync_connection is not None
            driver = cast(Any, sync_connection.connection.driver_connection)
            if not driver.in_transaction:
                await self._conn.exec_driver_sql("BEGIN")
        savepoint = _SessionSavepoint(self, await self._conn.begin_nested())
        self._savepoints.append(savepoint)
        return savepoint

    def _finish_savepoint(self, savepoint: _SessionSavepoint, *, rolled_back: bool) -> None:
        if rolled_back:
            self._commit_hooks = [hook for hook in self._commit_hooks if savepoint not in hook.savepoints]
        if savepoint in self._savepoints:
            del self._savepoints[self._savepoints.index(savepoint) :]

    async def _ensure_connection(self):
        """Ensure connection is available with health check."""
        self._check_database_operation()
        if self._conn is None or self._conn.closed:
            engine = get_database(self._db_name).engine
            self._conn = await engine.connect()
        elif self._conn.invalidated:
            await self._conn.close()
            engine = get_database(self._db_name).engine
            self._conn = await engine.connect()

    async def _handle_exception(self, exc: Exception):
        """Handle exceptions with unified error processing."""
        if self.auto_commit and not (self._conn and self._conn.in_nested_transaction()):
            await self.rollback()
        elif not (self._conn and self._conn.in_nested_transaction()):
            self._rollback_only = True

        # Log detailed error for debugging when echo is enabled
        if hasattr(self.bind, "echo") and getattr(self.bind, "echo", False):
            print(f"SQLObjects Session Error: {exc}")
            if hasattr(exc, "statement"):
                print(f"Statement: {exc.statement}")  # type: ignore[reportAttributeAccessIssue]
            if hasattr(exc, "params"):
                print(f"Parameters: {exc.params}")  # type: ignore[reportAttributeAccessIssue]

        if isinstance(exc, SQLAlchemyError):
            raise convert_sqlalchemy_error(exc) from exc
        raise exc

    async def __aenter__(self) -> AsyncSession:
        """Async context manager entry."""
        self._check_owner()
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
            self._check_owner()
            attribute = getattr(self._conn, name)
            if inspect.iscoroutinefunction(attribute):

                async def guarded(*args, **kwargs):
                    self._check_database_operation()
                    return await attribute(*args, **kwargs)

                return guarded
            return attribute
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class _SessionSavepoint:
    """A started savepoint that also tracks callback scope and task ownership."""

    def __init__(self, session: AsyncSession, transaction: AsyncTransaction):
        self._session = session
        self._transaction = transaction

    @property
    def is_active(self) -> bool:
        return self._transaction.is_active

    @property
    def is_valid(self) -> bool:
        return self._transaction.is_valid

    @property
    def connection(self) -> AsyncConnection:
        self._session._check_database_operation()
        return self._transaction.connection

    def _check_scope(self) -> None:
        self._session._check_database_operation()
        if self.is_active and (not self._session._savepoints or self._session._savepoints[-1] is not self):
            raise TransactionError("Savepoints must be finished in reverse creation order")

    async def commit(self) -> None:
        self._check_scope()
        try:
            await self._transaction.commit()
        except BaseException:
            self._session._finish_savepoint(self, rolled_back=True)
            self._session._rollback_only = True
            raise
        self._session._finish_savepoint(self, rolled_back=False)

    async def rollback(self) -> None:
        self._check_scope()
        if not self.is_active:
            return
        try:
            await self._transaction.rollback()
        except BaseException:
            self._session._rollback_only = True
            raise
        finally:
            self._session._finish_savepoint(self, rolled_back=True)

    async def close(self) -> None:
        await self.rollback()

    async def __aenter__(self) -> _SessionSavepoint:
        self._session._check_database_operation()
        if not self.is_active:
            raise TransactionError("Savepoint is no longer active")
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if self.is_active:
            if exc_type is None:
                await self.commit()
            else:
                await self.rollback()


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
                session = explicit_sessions[name]
                session._check_owner()
                return session
        except LookupError:
            pass

        # Create new session as fallback
        return AsyncSession(name, readonly, auto_commit)

    @classmethod
    def set_session(
        cls, session: AsyncSession, db_name: str | None = None
    ) -> contextvars.Token[dict[str, AsyncSession]]:
        """Set active session in current context.

        Returns a Token that can be used with reset_session() to restore the
        previous ContextVar state, enabling correct nested ctx_session() behavior.
        """
        name = db_name or get_default()
        try:
            current_sessions = _explicit_sessions.get({})
        except LookupError:
            current_sessions = {}
        new_sessions = current_sessions.copy()
        new_sessions[name] = session
        return _explicit_sessions.set(new_sessions)

    @classmethod
    def reset_session(cls, token: contextvars.Token[dict[str, AsyncSession]]) -> None:
        """Restore ContextVar to a previous state using a token from set_session()."""
        _explicit_sessions.reset(token)

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
async def ctx_session(db_name: str | None = None, *, join_ambient: bool = False) -> AsyncGenerator[AsyncSession, None]:
    """Get async context manager for single database transactional session.

    Creates a transactional session with manual commit control (auto_commit=False).
    Transaction is automatically committed on successful exit or rolled back on exception.

    Args:
        db_name: Database name (uses default database if None)
        join_ambient: If True and an explicit session already exists in the current
            context, reuse it instead of creating a new one. The ambient session's
            lifecycle (commit/rollback/close) stays with its outer owner; exceptions
            propagate to the owner for rollback. This avoids a second physical
            connection whose row locks would deadlock against the outer transaction
            in a way the database deadlock detector cannot see.

    Yields:
        AsyncSession: Transactional session with manual commit control
    """
    name = db_name or get_default()

    if join_ambient and name in _explicit_sessions.get({}):
        yield get_session(name, readonly=False)
        return

    if has_session(name):
        logger.warning(
            "ctx_session(%r) is creating a new session while an ambient session already exists "
            "in this context. The two sessions use separate physical connections; writes to rows "
            "locked by the outer transaction will block undetectably. "
            "Pass join_ambient=True to reuse the ambient session.",
            name,
        )

    session = AsyncSession(name, readonly=False, auto_commit=False)

    # Set as explicit session in context, save token for nested restore
    token = _SessionContextManager.set_session(session, name)

    try:
        yield session
        # Auto-commit on successful exit
        await session.commit()
    except BaseException:
        # Auto-rollback on exception
        await session.rollback()
        raise
    finally:
        # Cleanup
        try:
            await session.close()
        finally:
            _SessionContextManager.reset_session(token)


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
    tokens: list[contextvars.Token[dict[str, AsyncSession]]] = []

    try:
        # Create sessions for all
        for db_name in db_names:
            session = AsyncSession(db_name, readonly=False, auto_commit=False)
            sessions[db_name] = session
            tokens.append(_SessionContextManager.set_session(session, db_name))

        yield sessions

        # Auto-commit all sessions on successful exit
        for session in sessions.values():
            await session.commit()

    except BaseException:
        # Auto-rollback all sessions on exception
        for session in sessions.values():
            await session.rollback()
        raise

    finally:
        # Cleanup all sessions
        try:
            async with AsyncExitStack() as cleanup:
                for session in sessions.values():
                    cleanup.push_async_callback(session.close)
        finally:
            # Reset tokens even if closing a connection fails.
            for token in reversed(tokens):
                _SessionContextManager.reset_session(token)


def get_session(
    db_or_name: str | AsyncSession | None = None, readonly: bool = True, auto_commit: bool = True
) -> AsyncSession:
    """Get database session with readonly optimization.

    Args:
        db_or_name: Database name, existing AsyncSession, or None for default database
        readonly: True for readonly (no transaction), False for transactional
        auto_commit: True to auto-commit transactions (ignored if readonly=True)

    Returns:
        AsyncSession instance

    Priority:
        - If db_or_name is an AsyncSession, return it directly
        - First try use explicitly set session (ctx_session, ctx_sessions)
        - Create a new AsyncSession with specified parameters if no explicit session
    """
    if isinstance(db_or_name, AsyncSession):
        db_or_name._check_owner()
        return db_or_name
    return _SessionContextManager.get_session(db_or_name, readonly, auto_commit)


def has_session(db_name: str | None = None) -> bool:
    """Check if an explicit session exists in current context.

    Args:
        db_name: Database name (uses default database if None)

    Returns:
        True if explicit session exists, False otherwise
    """
    name = db_name or get_default()
    try:
        explicit_sessions = _explicit_sessions.get({})
        return name in explicit_sessions and explicit_sessions[name]._usable_in_current_task()
    except LookupError:
        return False


async def on_commit(
    callback: Callable[[], Any], db_or_session: str | AsyncSession | None = None, *, robust: bool = False
) -> None:
    """Register a callback on the selected writable session, or run it immediately."""
    await get_session(db_or_session, readonly=False).on_commit(callback, robust=robust)

"""ASGI middleware for request-scoped SQLObjects session management."""

from __future__ import annotations

from typing import Any

from ..database.manager import get_default
from ..session import AsyncSession, _SessionContextManager


class SessionMiddleware:
    """ASGI middleware that provides a request-scoped database session.

    Automatically creates an AsyncSession for each HTTP/WebSocket request,
    sets it in the ContextVar so that model operations use it, and commits
    on success or rolls back on failure.

    Usage with FastAPI::

        from fastapi import FastAPI
        from sqlobjects.contrib.asgi import SessionMiddleware

        app = FastAPI()
        app.add_middleware(SessionMiddleware)

    Usage with Starlette::

        from starlette.applications import Starlette
        from sqlobjects.contrib.asgi import SessionMiddleware

        app = Starlette()
        app.add_middleware(SessionMiddleware)
    """

    def __init__(
        self,
        app: Any,
        db_name: str | None = None,
        readonly: bool = False,
    ) -> None:
        self.app = app
        self.db_name = db_name
        self.readonly = readonly

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        name = self.db_name or get_default()
        session = AsyncSession(name, readonly=self.readonly, auto_commit=False)
        token = _SessionContextManager.set_session(session, name)
        try:
            await self.app(scope, receive, send)
            if not self.readonly:
                await session.commit()
        except Exception:
            if not self.readonly:
                await session.rollback()
            raise
        finally:
            await session.close()
            _SessionContextManager.reset_session(token)

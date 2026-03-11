"""FastAPI dependency for SQLObjects session management."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from ..session import AsyncSession, ctx_session


async def get_db_session(db_name: str | None = None) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a transactional session.

    Usage::

        from fastapi import Depends
        from sqlobjects.contrib.fastapi import get_db_session
        from sqlobjects.session import AsyncSession


        @app.post("/users")
        async def create_user(session: AsyncSession = Depends(get_db_session)):
            user = await User.objects.using(session).create(name="Alice")
            return {"id": user.id}
    """
    async with ctx_session(db_name) as session:
        yield session

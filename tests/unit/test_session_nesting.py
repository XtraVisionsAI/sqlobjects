"""Tests for nested ctx_session() ContextVar token-based restore."""

import contextvars
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sqlobjects.session import (
    AsyncSession,
    _explicit_sessions,
    _SessionContextManager,
    ctx_session,
    has_session,
)


@pytest.fixture(autouse=True)
def _reset_contextvar():
    """Ensure _explicit_sessions is clean before/after each test."""
    token = _explicit_sessions.set({})
    yield
    _explicit_sessions.reset(token)


def _make_session_stub(db_name: str = "default") -> AsyncSession:
    """Create a minimal AsyncSession stub that won't touch a real DB."""
    session = MagicMock(spec=AsyncSession)
    session._db_name = db_name
    session.db_name = db_name
    session.readonly = False
    session.auto_commit = False
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


class TestSetResetSession:
    """Test Token-based set_session / reset_session."""

    def test_set_session_returns_token(self):
        session = _make_session_stub()
        token = _SessionContextManager.set_session(session, "default")
        assert isinstance(token, contextvars.Token)

    def test_reset_session_restores_state(self):
        session1 = _make_session_stub()
        session2 = _make_session_stub()

        token1 = _SessionContextManager.set_session(session1, "default")
        assert _explicit_sessions.get({}).get("default") is session1

        token2 = _SessionContextManager.set_session(session2, "default")
        assert _explicit_sessions.get({}).get("default") is session2

        _SessionContextManager.reset_session(token2)
        assert _explicit_sessions.get({}).get("default") is session1

        _SessionContextManager.reset_session(token1)
        assert _explicit_sessions.get({}).get("default") is None


class TestNestedCtxSession:
    """Test that nested ctx_session() correctly restores the outer session."""

    @pytest.mark.asyncio
    async def test_nested_ctx_session_outer_survives(self):
        """Inner ctx_session exit must not clear the outer session."""
        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            outer = _make_session_stub()
            token = _SessionContextManager.set_session(outer, "default")

            try:
                # Simulate inner ctx_session lifecycle
                inner = _make_session_stub()
                inner_token = _SessionContextManager.set_session(inner, "default")

                # During inner, the active session is inner
                assert _explicit_sessions.get({}).get("default") is inner

                # Inner exits — reset
                _SessionContextManager.reset_session(inner_token)

                # Outer session is restored
                active = _explicit_sessions.get({}).get("default")
                assert active is outer
            finally:
                _SessionContextManager.reset_session(token)

    @pytest.mark.asyncio
    async def test_nested_ctx_session_inner_rollback_no_affect_outer(self):
        """Inner rollback must not affect the outer session."""
        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            outer = _make_session_stub()
            outer_token = _SessionContextManager.set_session(outer, "default")

            inner = _make_session_stub()
            inner_token = _SessionContextManager.set_session(inner, "default")

            # Inner rolls back
            await inner.rollback()
            await inner.close()
            _SessionContextManager.reset_session(inner_token)

            # Outer is untouched
            assert _explicit_sessions.get({}).get("default") is outer
            assert not outer.rollback.called  # type: ignore[union-attr]

            _SessionContextManager.reset_session(outer_token)

    @pytest.mark.asyncio
    async def test_contextvar_auto_routing_after_nesting(self):
        """After inner ctx_session exits, get_session() must route to outer."""
        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            outer = _make_session_stub()
            outer_token = _SessionContextManager.set_session(outer, "default")

            inner = _make_session_stub()
            inner_token = _SessionContextManager.set_session(inner, "default")

            # During inner
            result = _SessionContextManager.get_session("default")
            assert result is inner

            # After inner reset
            _SessionContextManager.reset_session(inner_token)
            result = _SessionContextManager.get_session("default")
            assert result is outer

            _SessionContextManager.reset_session(outer_token)

    @pytest.mark.asyncio
    async def test_triple_nesting(self):
        """Three levels of nesting must all restore correctly."""
        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            s1 = _make_session_stub()
            s2 = _make_session_stub()
            s3 = _make_session_stub()

            t1 = _SessionContextManager.set_session(s1, "default")
            t2 = _SessionContextManager.set_session(s2, "default")
            t3 = _SessionContextManager.set_session(s3, "default")

            assert _explicit_sessions.get({}).get("default") is s3

            _SessionContextManager.reset_session(t3)
            assert _explicit_sessions.get({}).get("default") is s2

            _SessionContextManager.reset_session(t2)
            assert _explicit_sessions.get({}).get("default") is s1

            _SessionContextManager.reset_session(t1)
            assert _explicit_sessions.get({}).get("default") is None


class TestCtxSessionsWithToken:
    """Test that ctx_sessions() multi-db version uses tokens correctly."""

    @pytest.mark.asyncio
    async def test_ctx_sessions_restores_previous_state(self):
        """ctx_sessions() must restore whatever was in the ContextVar before."""
        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            # Pre-existing session for db "alpha"
            pre = _make_session_stub("alpha")
            pre_token = _SessionContextManager.set_session(pre, "alpha")

            # Simulate ctx_sessions("alpha", "beta") lifecycle
            s_alpha = _make_session_stub("alpha")
            s_beta = _make_session_stub("beta")

            t1 = _SessionContextManager.set_session(s_alpha, "alpha")
            t2 = _SessionContextManager.set_session(s_beta, "beta")

            # During ctx_sessions
            assert _explicit_sessions.get({}).get("alpha") is s_alpha
            assert _explicit_sessions.get({}).get("beta") is s_beta

            # Exit ctx_sessions — reverse order reset
            _SessionContextManager.reset_session(t2)
            _SessionContextManager.reset_session(t1)

            # Pre-existing "alpha" session is restored
            assert _explicit_sessions.get({}).get("alpha") is pre
            # "beta" is gone (wasn't there before)
            assert _explicit_sessions.get({}).get("beta") is None

            _SessionContextManager.reset_session(pre_token)

    @pytest.mark.asyncio
    async def test_has_session_reflects_nesting(self):
        """has_session() must reflect the current nesting level."""
        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            assert not has_session("default")

            s1 = _make_session_stub()
            t1 = _SessionContextManager.set_session(s1, "default")
            assert has_session("default")

            s2 = _make_session_stub()
            t2 = _SessionContextManager.set_session(s2, "default")
            assert has_session("default")

            _SessionContextManager.reset_session(t2)
            assert has_session("default")

            _SessionContextManager.reset_session(t1)
            assert not has_session("default")


class TestJoinAmbient:
    """Test ctx_session(join_ambient=True) reuse of the ambient session."""

    @pytest.mark.asyncio
    async def test_join_ambient_reuses_outer_session(self):
        """join_ambient=True must yield the ambient session, not create a new one."""
        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            outer = _make_session_stub()
            token = _SessionContextManager.set_session(outer, "default")
            try:
                async with ctx_session(join_ambient=True) as session:
                    assert session is outer
            finally:
                _SessionContextManager.reset_session(token)

    @pytest.mark.asyncio
    async def test_join_ambient_does_not_manage_lifecycle(self):
        """Joining must not commit/rollback/close the ambient session."""
        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            outer = _make_session_stub()
            token = _SessionContextManager.set_session(outer, "default")
            try:
                async with ctx_session(join_ambient=True):
                    pass
                assert not outer.commit.called  # type: ignore[union-attr]
                assert not outer.rollback.called  # type: ignore[union-attr]
                assert not outer.close.called  # type: ignore[union-attr]
            finally:
                _SessionContextManager.reset_session(token)

    @pytest.mark.asyncio
    async def test_join_ambient_propagates_exception_without_rollback(self):
        """Exceptions must propagate to the owner; the join must not roll back."""
        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            outer = _make_session_stub()
            token = _SessionContextManager.set_session(outer, "default")
            try:
                with pytest.raises(ValueError, match="boom"):
                    async with ctx_session(join_ambient=True):
                        raise ValueError("boom")
                assert not outer.rollback.called  # type: ignore[union-attr]
                assert not outer.close.called  # type: ignore[union-attr]
            finally:
                _SessionContextManager.reset_session(token)

    @pytest.mark.asyncio
    async def test_join_ambient_without_ambient_creates_new(self):
        """join_ambient=True with no ambient session falls back to creating one."""
        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            created = _make_session_stub()
            with patch("sqlobjects.session.AsyncSession", return_value=created):
                async with ctx_session(join_ambient=True) as session:
                    assert session is created
                assert created.commit.called  # type: ignore[union-attr]
                assert created.close.called  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_default_nesting_warns(self, caplog):
        """Nesting without join_ambient must emit a WARNING log."""
        import logging

        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            outer = _make_session_stub()
            token = _SessionContextManager.set_session(outer, "default")
            try:
                created = _make_session_stub()
                with (
                    patch("sqlobjects.session.AsyncSession", return_value=created),
                    caplog.at_level(logging.WARNING, logger="sqlobjects.session"),
                ):
                    async with ctx_session() as session:
                        assert session is created
                assert any("join_ambient" in r.message for r in caplog.records)
            finally:
                _SessionContextManager.reset_session(token)

    @pytest.mark.asyncio
    async def test_no_warning_without_ambient(self, caplog):
        """Top-level ctx_session must not warn."""
        import logging

        with patch("sqlobjects.session.get_default", return_value="default"), patch("sqlobjects.session.get_database"):
            created = _make_session_stub()
            with (
                patch("sqlobjects.session.AsyncSession", return_value=created),
                caplog.at_level(logging.WARNING, logger="sqlobjects.session"),
            ):
                async with ctx_session():
                    pass
            assert not caplog.records

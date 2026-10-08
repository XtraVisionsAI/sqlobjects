"""Commit callbacks must follow physical transaction outcomes on every backend."""

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncTransaction
from sqlalchemy.pool import QueuePool

from sqlobjects.contrib.asgi import SessionMiddleware
from sqlobjects.database import close_db, init_db
from sqlobjects.exceptions import IntegrityError, TransactionError
from sqlobjects.session import AsyncSession, ctx_session, get_session, has_session, on_commit
from tests.integration.test_orm_contracts import ContractRecord
from tests.integration.test_orm_contracts import clean_db as _clean_db
from tests.integration.test_orm_contracts import contract_db as _contract_db


clean_db = _clean_db
contract_db = _contract_db


@pytest.mark.usefixtures("contract_db")
class TestCommitCallbacks:
    async def test_sync_and_async_callbacks_wait_for_commit_in_order(self):
        calls = []
        async with ctx_session() as session:
            await on_commit(lambda: calls.append("first"))

            async def callback():
                assert not session.in_transaction
                assert not has_session()
                assert await ContractRecord.objects.count() == 1
                calls.append("second")

            await session.on_commit(callback)
            await ContractRecord.objects.create(name="stored")
            assert calls == []
        assert calls == ["first", "second"]

    async def test_no_sql_transaction_still_runs_callbacks(self):
        calls = []
        async with ctx_session() as session:
            await session.on_commit(lambda: calls.append("committed"))
            assert calls == []
        assert calls == ["committed"]

    async def test_outside_transaction_runs_and_awaits_immediately(self):
        calls = []

        async def callback():
            calls.append("async")

        await on_commit(lambda: calls.append("sync"))
        await on_commit(lambda: callback())
        assert calls == ["sync", "async"]

    @pytest.mark.parametrize("action", ["rollback", "close"])
    async def test_abandoned_transaction_discards_callbacks(self, action):
        calls = []
        session = AsyncSession("default", readonly=False, auto_commit=False)
        try:
            await ContractRecord.objects.using(session).create(name="abandoned")
            await session.on_commit(lambda: calls.append("unexpected"))
            await getattr(session, action)()
            if action == "rollback":
                await session.commit()
        finally:
            await session.close()
        assert calls == []
        assert await ContractRecord.objects.count() == 0

    async def test_root_rollback_discards_released_savepoint_callbacks(self):
        calls = []
        with pytest.raises(ValueError, match="rollback"):
            async with ctx_session() as session:
                await session.on_commit(lambda: calls.append("root"))
                async with await session.begin_nested():
                    await ContractRecord.objects.create(name="nested")
                    await session.on_commit(lambda: calls.append("nested"))
                assert calls == []
                raise ValueError("rollback")
        assert calls == []
        assert await ContractRecord.objects.count() == 0

    async def test_savepoint_rollback_preserves_only_surviving_callbacks(self):
        calls = []
        async with ctx_session() as session:
            await session.on_commit(lambda: calls.append("root"))
            with pytest.raises(ValueError):
                async with await session.begin_nested():
                    await session.on_commit(lambda: calls.append("discard outer"))
                    async with await session.begin_nested():
                        await session.on_commit(lambda: calls.append("discard inner"))
                    raise ValueError("rollback outer savepoint")
            async with await session.begin_nested():
                await session.on_commit(lambda: calls.append("survivor"))
            assert calls == []
        assert calls == ["root", "survivor"]

    @pytest.mark.parametrize("action", ["commit", "rollback", "close"])
    async def test_manual_savepoint_outcome_controls_callbacks(self, action):
        calls = []
        async with ctx_session() as session:
            savepoint = await session.begin_nested()
            await session.on_commit(lambda: calls.append("nested"))
            await getattr(savepoint, action)()
            assert calls == []
        assert calls == (["nested"] if action == "commit" else [])

    async def test_cleanup_of_released_savepoint_preserves_callbacks(self):
        calls = []
        async with ctx_session() as session:
            savepoint = await session.begin_nested()
            await session.on_commit(lambda: calls.append("committed"))
            await savepoint.commit()
            await savepoint.rollback()
            await savepoint.close()
        assert calls == ["committed"]

    async def test_context_entry_creates_exactly_one_savepoint(self, contract_db):
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.upper())

        event.listen(contract_db.engine.sync_engine, "before_cursor_execute", record)
        try:
            async with ctx_session() as session:
                async with await session.begin_nested():
                    await ContractRecord.objects.create(name="nested")
            assert sum(sql.startswith("SAVEPOINT ") for sql in statements) == 1
            assert sum(sql.startswith("RELEASE SAVEPOINT ") for sql in statements) == 1
        finally:
            event.remove(contract_db.engine.sync_engine, "before_cursor_execute", record)

    async def test_savepoints_reject_out_of_order_completion(self):
        calls = []
        async with ctx_session() as session:
            outer = await session.begin_nested()
            inner = await session.begin_nested()
            await session.on_commit(lambda: calls.append("inner"))
            with pytest.raises(TransactionError, match="reverse creation order"):
                await outer.rollback()
            await inner.commit()
            await outer.rollback()
            await session.on_commit(lambda: calls.append("root"))
        assert calls == ["root"]

    async def test_constraint_error_discards_failed_savepoint_callback(self):
        calls = []
        async with ctx_session() as session:
            await ContractRecord.objects.create(name="existing")
            await session.on_commit(lambda: calls.append("root"))
            with pytest.raises(IntegrityError):
                async with await session.begin_nested():
                    await session.on_commit(lambda: calls.append("failed"))
                    await ContractRecord.objects.create(name="existing")
            await session.on_commit(lambda: calls.append("after"))
        assert calls == ["root", "after"]

    async def test_commit_failure_never_dispatches_old_callbacks(self):
        calls = []
        async with ctx_session() as session:
            await ContractRecord.objects.create(name="not-committed")
            await session.on_commit(lambda: calls.append("old"))
            with patch.object(AsyncTransaction, "commit", AsyncMock(side_effect=RuntimeError("commit failed"))):
                with pytest.raises(RuntimeError, match="commit failed"):
                    await session.commit()
            await session.rollback()
            await ContractRecord.objects.create(name="committed")
            await session.on_commit(lambda: calls.append("new"))
        assert calls == ["new"]
        assert set(await ContractRecord.objects.values_list("name", flat=True)) == {"committed"}

    @pytest.mark.parametrize("robust", [False, True])
    async def test_callback_failure_cannot_undo_commit(self, robust, caplog):
        calls = []

        def fail():
            calls.append("failure")
            raise RuntimeError("callback failed")

        async def transaction():
            async with ctx_session() as session:
                await ContractRecord.objects.create(name="committed")
                await session.on_commit(lambda: calls.append("first"))
                await session.on_commit(fail, robust=robust)
                await session.on_commit(lambda: calls.append("last"))

        if robust:
            await transaction()
            assert calls == ["first", "failure", "last"]
            assert "Error in on_commit callback" in caplog.text
        else:
            with pytest.raises(RuntimeError, match="callback failed"):
                await transaction()
            assert calls == ["first", "failure"]
        assert await ContractRecord.objects.count() == 1
        assert not has_session()

    async def test_cancellation_before_commit_discards_callbacks(self):
        calls = []
        with pytest.raises(asyncio.CancelledError):
            async with ctx_session() as session:
                await ContractRecord.objects.create(name="cancelled")
                await session.on_commit(lambda: calls.append("unexpected"))
                raise asyncio.CancelledError
        assert calls == []
        assert await ContractRecord.objects.count() == 0

    async def test_robust_does_not_swallow_callback_cancellation(self):
        calls = []

        async def cancel():
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            async with ctx_session() as session:
                await ContractRecord.objects.create(name="committed")
                await session.on_commit(cancel, robust=True)
                await session.on_commit(lambda: calls.append("unexpected"))
        assert calls == []
        assert await ContractRecord.objects.count() == 1
        assert not has_session()

    async def test_callback_can_write_with_one_connection_pool(self, contract_db):
        db = await init_db(
            contract_db.engine.url.render_as_string(hide_password=False),
            name="callbacks",
            is_default=False,
            pool_size=1,
            max_overflow=0,
            pool_timeout=1,
        )
        pool = db.engine.pool
        assert isinstance(pool, QueuePool)
        try:
            async with ctx_session("callbacks"):
                await ContractRecord.objects.using("callbacks").create(name="parent")

                async def callback():
                    assert not has_session("callbacks")
                    assert pool.checkedout() == 0
                    await ContractRecord.objects.using("callbacks").create(name="callback")

                await on_commit(callback, "callbacks")
            assert pool.checkedout() == 0
            assert await ContractRecord.objects.count() == 2
        finally:
            await close_db("callbacks")

    async def test_callback_cannot_silently_reuse_committing_session(self):
        async with ctx_session() as session:
            await ContractRecord.objects.create(name="committed")

            async def callback():
                with pytest.raises(TransactionError, match="new session"):
                    await ContractRecord.objects.using(session).create(name="unexpected")

            await session.on_commit(callback)
        assert await ContractRecord.objects.count() == 1

    async def test_reentrant_registration_runs_immediately(self):
        calls = []
        async with ctx_session() as session:

            async def first():
                calls.append("first")
                await session.on_commit(lambda: calls.append("reentrant"))

            await session.on_commit(first)
            await session.on_commit(lambda: calls.append("last"))
        assert calls == ["first", "reentrant", "last"]

    async def test_each_commit_consumes_callbacks_once(self):
        calls = []
        async with ctx_session() as session:
            for index in range(2):
                await ContractRecord.objects.create(name=f"row-{index}")
                await session.on_commit(lambda index=index: calls.append(index))
                await session.commit()
                assert get_session() is session
                await session.commit()
        assert calls == [0, 1]

    async def test_registration_rejects_invalid_session_and_callback(self):
        with pytest.raises(TypeError, match="callable"):
            await on_commit(cast(Any, 42))
        readonly = get_session()
        with pytest.raises(TransactionError, match="writable"):
            await readonly.on_commit(lambda: None)
        await readonly.close()
        with pytest.raises(TransactionError, match="closed"):
            await readonly.on_commit(lambda: None)
        async with ctx_session() as session:
            await ContractRecord.objects.create(name="existing")
            with pytest.raises(IntegrityError):
                await ContractRecord.objects.create(name="existing")
            with pytest.raises(TransactionError, match="non-failed"):
                await session.on_commit(lambda: None)
            await session.rollback()

    async def test_child_cannot_register_or_rollback_parent_savepoint(self):
        async with ctx_session() as session:
            async with await session.begin_nested() as savepoint:

                async def child():
                    with pytest.raises(TransactionError, match="another asyncio task"):
                        await session.on_commit(lambda: None)
                    with pytest.raises(TransactionError, match="another asyncio task"):
                        await savepoint.rollback()

                await asyncio.create_task(child())
                assert savepoint.is_active

    @pytest.mark.parametrize("binding", ["instance", "keyword", "positional"])
    async def test_signal_callback_uses_explicit_instance_session(self, binding):
        calls = []
        session = AsyncSession("default", readonly=False, auto_commit=False)
        try:
            obj = ContractRecord(name="signal")

            async def after_save(context):
                assert context.session is session
                await context.on_commit(lambda: calls.append(obj.id))

            object.__setattr__(obj, "after_save", after_save)
            if binding == "instance":
                await obj.using(session).save(cascade=False)
            elif binding == "keyword":
                await obj.save(cascade=False, session=session)
            else:
                await obj.save(True, False, session)
            assert calls == []
            await session.commit()
            assert calls == [obj.id]
        finally:
            await session.close()

    @pytest.mark.parametrize("fail", [False, True])
    async def test_middleware_follows_request_transaction_outcome(self, fail):
        calls = []

        async def app(scope, receive, send):
            await ContractRecord.objects.create(name="request")
            await on_commit(lambda: calls.append("committed"))
            if fail:
                raise ValueError("request failed")
            assert calls == []

        middleware = SessionMiddleware(app)
        if fail:
            with pytest.raises(ValueError, match="request failed"):
                await middleware({"type": "http"}, None, None)
        else:
            await middleware({"type": "http"}, None, None)
        assert calls == ([] if fail else ["committed"])
        assert await ContractRecord.objects.count() == (0 if fail else 1)

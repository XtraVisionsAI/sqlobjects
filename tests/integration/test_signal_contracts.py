"""Signals must describe the real operation and participate in its transaction."""

from dataclasses import replace

import pytest

from sqlobjects import ErrorHandling, TransactionMode
from sqlobjects.database import close_db, init_db
from sqlobjects.exceptions import IntegrityError, QueryError
from sqlobjects.fields import Column, IntegerColumn, StringColumn, identity
from sqlobjects.metadata import ModelRegistry
from sqlobjects.model import ObjectModel
from sqlobjects.session import ctx_session
from sqlobjects.signals import Operation
from tests.test_config import TestDatabaseConfig


class SignalBase(ObjectModel):
    __abstract__ = True
    __registry__ = ModelRegistry()


class SignalRecord(SignalBase):
    id: Column[int] = identity()
    name: Column[str] = StringColumn(length=60, unique=True, nullable=False)
    value: Column[int] = IntegerColumn(default=0)


@pytest.fixture(autouse=True)
def clean_db():
    """These tests own schema and commit boundaries."""


@pytest.fixture
async def signal_db(db_type, tmp_path):
    config = TestDatabaseConfig.get_config(db_type)
    url = f"sqlite+aiosqlite:///{tmp_path / 'signals.db'}" if db_type == "sqlite" else config["url"]
    db = await init_db(url)
    await db.create_tables(SignalBase)
    try:
        yield db
    finally:
        await db.drop_tables(SignalBase)
        await close_db()


@pytest.fixture
def events(signal_db, monkeypatch):
    calls = []

    def handler(name):
        async def record(self_or_cls, context):
            calls.append((name, replace(context)))

        return record

    for prefix in ["", "bulk_"]:
        for operation in ["save", "create", "update", "delete"]:
            for timing in ["before", "after"]:
                name = f"{timing}_{prefix}{operation}"
                callback = handler(name)
                if prefix:
                    callback = classmethod(callback)
                monkeypatch.setattr(SignalRecord, name, callback, raising=False)
    return calls


async def seed_records():
    async with ctx_session() as session:
        await session.execute(SignalRecord.__table__.insert(), [{"name": "first"}, {"name": "second"}])
    return await SignalRecord.objects.order_by("id").all()


async def test_manager_create_emits_instance_signals_with_insert_semantics(events):
    obj = await SignalRecord.objects.create(id=100, name="new")
    assert [name for name, _ in events] == ["before_save", "before_create", "after_save", "after_create"]
    assert obj.id == 100
    assert await SignalRecord.objects.count() == 1
    for _, context in events:
        assert context.instance is obj
        assert context.model_class is SignalRecord
        assert context.operation == Operation.SAVE
        assert context.actual_operation == Operation.CREATE


async def test_create_before_hook_mutates_saved_values(events, monkeypatch):
    async def before_create(self, context):
        self.name = "changed"

    monkeypatch.setattr(SignalRecord, "before_create", before_create)
    obj = await SignalRecord.objects.create(name="initial")
    assert obj.name == "changed"
    assert (await SignalRecord.objects.get(id=obj.id)).name == "changed"


async def test_sync_hook_returning_awaitable_is_awaited(events, monkeypatch):
    def before_create(self, context):
        async def apply_name():
            self.name = "awaited"

        return apply_name()

    monkeypatch.setattr(SignalRecord, "before_create", before_create)
    obj = await SignalRecord.objects.create(name="initial")
    assert (await SignalRecord.objects.get(id=obj.id)).name == "awaited"


async def test_create_signal_failure_rolls_back_and_discards_commit_callbacks(events, monkeypatch):
    effects = []

    async def before_create(self, context):
        await context.on_commit(lambda: effects.append("unexpected"))

    async def after_create(self, context):
        assert self.id is not None
        raise RuntimeError("signal failed")

    monkeypatch.setattr(SignalRecord, "before_create", before_create)
    monkeypatch.setattr(SignalRecord, "after_create", after_create)
    with pytest.raises(RuntimeError, match="signal failed"):
        await SignalRecord.objects.create(name="rolled back")
    assert effects == []
    assert await SignalRecord.objects.count() == 0


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
@pytest.mark.parametrize("return_objects", [False, True])
async def test_bulk_signals_have_correct_operation_and_result_count(events, operation, return_objects):
    first, _ = await seed_records()
    if operation == "create":
        result = await SignalRecord.objects.bulk_create(
            [{"name": "third"}, {"name": "fourth"}], return_objects=return_objects
        )
        expected_count = 2
    elif operation == "update":
        result = await SignalRecord.objects.bulk_update(
            [{"id": first.id, "value": 9}, {"id": first.id + 10000, "value": 9}], return_objects=return_objects
        )
        expected_count = 1
    else:
        result = await SignalRecord.objects.bulk_delete([first.id, first.id + 10000], return_objects=return_objects)
        expected_count = 1
    names = [name for name, _ in events]
    expected = [f"before_bulk_{operation}", f"after_bulk_{operation}"]
    if operation != "delete":
        expected = ["before_bulk_save", expected[0], "after_bulk_save", expected[1]]
    assert names == expected
    for name, context in events:
        assert context.model_class is SignalRecord
        assert context.is_bulk
        assert context.actual_operation == Operation(operation)
        assert context.affected_count == (2 if name.startswith("before") else expected_count)
    assert (result.success_count if return_objects else result) == expected_count


@pytest.mark.parametrize("operation", ["update", "delete"])
async def test_queryset_signals_use_bound_alias_and_expose_updates(events, signal_db, monkeypatch, operation):
    effects = []
    await seed_records()
    await init_db(signal_db.engine.url.render_as_string(hide_password=False), name="other", is_default=False)

    async def after(cls, context):
        assert context.session.db_name == "other"
        assert context.affected_count == 1
        if operation == "update":
            assert context.update_data == {"value": 8}
        await context.on_commit(lambda: effects.append("committed"))

    monkeypatch.setattr(SignalRecord, f"after_bulk_{operation}", classmethod(after))
    try:
        async with ctx_session("other") as session:
            query = SignalRecord.objects.using(session).filter(name="first")
            if operation == "update":
                assert await query.update(value=8) == 1
            else:
                assert await query.delete(cascade="none") == 1
            assert effects == []
        assert effects == ["committed"]
    finally:
        await close_db("other")


async def test_invalid_queryset_write_emits_no_signals(events):
    with pytest.raises(QueryError):
        await SignalRecord.objects.distinct().update(value=9)
    assert events == []


@pytest.mark.parametrize("operation", ["update", "delete"])
async def test_queryset_after_signal_failure_rolls_back_implicit_write(events, monkeypatch, operation):
    first, _ = await seed_records()
    effects = []

    async def after(cls, context):
        await context.on_commit(lambda: effects.append("unexpected"))
        raise RuntimeError("queryset hook failed")

    monkeypatch.setattr(SignalRecord, f"after_bulk_{operation}", classmethod(after))
    with pytest.raises(RuntimeError, match="queryset hook failed"):
        query = SignalRecord.objects.filter(id=first.id)
        if operation == "update":
            await query.update(value=9)
        else:
            await query.delete(cascade="none")
    assert effects == []
    assert (await SignalRecord.objects.get(id=first.id)).value == 0


@pytest.mark.parametrize("mode", list(TransactionMode))
async def test_bulk_callbacks_follow_each_actual_transaction(events, monkeypatch, mode):
    effects = []

    async def after_create(cls, context):
        assert context.session.in_transaction
        await context.on_commit(lambda: effects.append(context.affected_count))

    monkeypatch.setattr(SignalRecord, "after_bulk_create", classmethod(after_create))
    independent = mode in {TransactionMode.INDEPENDENT, TransactionMode.BATCH}
    with pytest.raises(RuntimeError, match="outer abort"):
        async with ctx_session():
            await SignalRecord.objects.bulk_create(
                [{"name": "one"}, {"name": "two"}], batch_size=1, transaction_mode=mode
            )
            assert effects == ([1, 1] if independent else [])
            raise RuntimeError("outer abort")
    assert effects == ([1, 1] if independent else [])
    assert await SignalRecord.objects.count() == (2 if independent else 0)


@pytest.mark.parametrize("mode", [TransactionMode.INHERIT, TransactionMode.BATCH])
async def test_failed_bulk_batch_does_not_dispatch_rolled_back_callbacks(events, monkeypatch, mode):
    effects = []

    async def before_create(cls, context):
        await context.on_commit(lambda: effects.append("committed"))

    monkeypatch.setattr(SignalRecord, "before_bulk_create", classmethod(before_create))
    with pytest.raises(IntegrityError):
        await SignalRecord.objects.bulk_create(
            [{"name": "duplicate"}, {"name": "duplicate"}], batch_size=1, transaction_mode=mode
        )
    assert effects == (["committed"] if mode == TransactionMode.BATCH else [])
    assert await SignalRecord.objects.count() == (1 if mode == TransactionMode.BATCH else 0)


@pytest.mark.parametrize("on_error", [ErrorHandling.IGNORE, ErrorHandling.COLLECT])
@pytest.mark.parametrize("timing", ["before", "after"])
async def test_signal_errors_are_not_silently_collected(events, monkeypatch, on_error, timing):
    async def fail(cls, context):
        raise RuntimeError("hook failure")

    monkeypatch.setattr(SignalRecord, f"{timing}_bulk_create", classmethod(fail))
    with pytest.raises(RuntimeError, match="hook failure"):
        await SignalRecord.objects.bulk_create(
            [{"name": "not stored"}], transaction_mode=TransactionMode.BATCH, on_error=on_error
        )
    assert await SignalRecord.objects.count() == 0


async def test_after_commit_error_propagates_without_reclassifying_committed_batch(events, monkeypatch):
    def fail():
        raise RuntimeError("commit callback failed")

    async def after_create(cls, context):
        await context.on_commit(fail)

    monkeypatch.setattr(SignalRecord, "after_bulk_create", classmethod(after_create))
    with pytest.raises(RuntimeError, match="commit callback failed"):
        await SignalRecord.objects.bulk_create(
            [{"name": "stored"}], transaction_mode=TransactionMode.BATCH, on_error=ErrorHandling.COLLECT
        )
    assert await SignalRecord.objects.count() == 1


async def test_collected_row_errors_report_successful_count_to_after_signal(events):
    await seed_records()
    result = await SignalRecord.objects.bulk_create(
        [{"name": "first"}, {"name": "new"}], on_error=ErrorHandling.COLLECT, return_objects=True
    )
    assert result.success_count == 1
    assert result.error_count == 1
    assert events[-1][0] == "after_bulk_create"
    assert events[-1][1].affected_count == 1

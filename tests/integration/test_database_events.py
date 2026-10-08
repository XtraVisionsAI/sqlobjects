"""Database decorators expose synchronous SQLAlchemy Core event contracts."""

from functools import partial

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.exc import InvalidRequestError, SQLAlchemyError

from sqlobjects.database import close_db, init_db
from sqlobjects.session import ctx_session
from tests.test_config import TestDatabaseConfig


@pytest.fixture(autouse=True)
def clean_db():
    """These tests own their connection and transaction lifecycle."""


@pytest.fixture
async def event_db(db_type, tmp_path):
    config = TestDatabaseConfig.get_config(db_type)
    url = f"sqlite+aiosqlite:///{tmp_path / 'events.db'}" if db_type == "sqlite" else config["url"]
    db = await init_db(url, **config["pool_config"])
    try:
        yield db
    finally:
        await close_db()


@pytest.mark.parametrize(
    ("name", "hint"),
    [
        ("before_commit", "commit"),
        ("before_rollback", "rollback"),
        ("after_commit", "on_commit"),
        ("after_rollback", "rollback"),
    ],
)
async def test_non_engine_transaction_events_have_actionable_errors(event_db, name, hint):
    with pytest.raises(ValueError, match=hint):
        event_db.on(name)(lambda *args: None)


@pytest.mark.parametrize("kind", ["function", "partial", "callable", "async_generator"])
async def test_async_listeners_are_rejected_before_registration(event_db, kind):
    async def listener(conn):
        pass

    class AsyncListener:
        async def __call__(self, conn):
            pass

    async def generator(conn):
        yield conn

    callback = {
        "function": listener,
        "partial": partial(listener),
        "callable": AsyncListener(),
        "async_generator": generator,
    }[kind]
    with pytest.raises(TypeError, match="synchronous"):
        event_db.on("commit")(callback)
    assert not event.contains(event_db.engine.sync_engine, "commit", callback)


async def test_unknown_event_keeps_sqlalchemy_validation(event_db):
    with pytest.raises(InvalidRequestError, match="No such event"):
        event_db.on("not_a_real_event")(lambda *args: None)


async def test_pool_events_use_adapted_connections_and_current_signatures(event_db):
    calls = []
    records = []

    @event_db.on("first_connect")
    def first_connect(dbapi_connection, connection_record):
        calls.append("first_connect")

    @event_db.on("connect")
    def connect(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1
        finally:
            cursor.close()
        calls.append("connect")
        records.append(connection_record)

    @event_db.on("checkout")
    def checkout(dbapi_connection, connection_record, connection_proxy):
        calls.append("checkout")
        assert connection_record is records[0]

    @event_db.on("reset")
    def reset(dbapi_connection, connection_record, reset_state):
        calls.append("reset")
        assert reset_state.asyncio_safe

    @event_db.on("checkin")
    def checkin(dbapi_connection, connection_record):
        calls.append("checkin")

    @event_db.on("close")
    def close(dbapi_connection, connection_record):
        calls.append("close")

    async with ctx_session() as session:
        await session.execute("SELECT 1")
    await event_db.disconnect()
    assert calls == ["first_connect", "connect", "checkout", "reset", "checkin", "close"]


async def test_listener_options_identity_and_native_removal(event_db):
    calls = []

    def rewrite(statement, parameters, **kwargs):
        assert isinstance(kwargs["conn"], Connection)
        calls.append(statement)
        return "SELECT 2", parameters

    decorated = event_db.on("before_cursor_execute", named=True, retval=True)(rewrite)
    assert decorated is rewrite
    async with ctx_session() as session:
        assert (await session.execute("SELECT 1")).scalar_one() == 2
    event.remove(event_db.engine.sync_engine, "before_cursor_execute", rewrite)
    async with ctx_session() as session:
        assert (await session.execute("SELECT 1")).scalar_one() == 1
    assert calls == ["SELECT 1"]


async def test_dialect_error_event_receives_original_error(event_db):
    errors = []
    statement = "SELECT * FROM missing_database_event_test_table"

    @event_db.on("handle_error")
    def handle_error(context):
        errors.append(context)

    with pytest.raises(SQLAlchemyError):
        async with event_db.engine.connect() as connection:
            await connection.exec_driver_sql(statement)
    assert len(errors) == 1
    assert errors[0].statement == statement
    assert errors[0].original_exception is not None
    assert errors[0].engine is event_db.engine.sync_engine


@pytest.mark.parametrize("failure", [None, "event", "driver"])
async def test_commit_event_precedes_driver_commit_and_success_callbacks(event_db, monkeypatch, failure):
    calls = []

    @event_db.on("commit")
    def committing(connection):
        assert isinstance(connection, Connection)
        calls.append("event")
        if failure == "event":
            raise RuntimeError("event failed")

    dialect = event_db.engine.sync_engine.dialect
    original_commit = dialect.do_commit

    def do_commit(connection):
        calls.append("driver")
        if failure == "driver":
            raise RuntimeError("driver failed")
        original_commit(connection)

    async def run():
        async with ctx_session() as session:
            await session.execute("SELECT 1")
            monkeypatch.setattr(dialect, "do_commit", do_commit)
            await session.on_commit(lambda: calls.append("callback"))

    if failure:
        with pytest.raises(RuntimeError, match=f"{failure} failed"):
            await run()
        assert calls == (["event"] if failure == "event" else ["event", "driver"])
    else:
        await run()
        assert calls == ["event", "driver", "callback"]


async def test_savepoint_and_rollback_events_are_distinct_from_commit(event_db):
    calls = []

    @event_db.on("begin")
    def begin(connection):
        calls.append("begin")

    @event_db.on("savepoint")
    def savepoint(connection, name):
        calls.append("savepoint")

    @event_db.on("release_savepoint")
    def release(connection, name, context):
        calls.append("release")

    @event_db.on("rollback_savepoint")
    def rollback_savepoint(connection, name, context):
        calls.append("rollback_savepoint")

    @event_db.on("rollback")
    def rollback(connection):
        calls.append("rollback")

    with pytest.raises(RuntimeError, match="outer rollback"):
        async with ctx_session() as session:
            await session.execute("SELECT 1")
            async with await session.begin_nested():
                await session.execute("SELECT 2")
            with pytest.raises(ValueError, match="nested rollback"):
                async with await session.begin_nested():
                    raise ValueError("nested rollback")
            raise RuntimeError("outer rollback")
    assert calls == ["begin", "savepoint", "release", "savepoint", "rollback_savepoint", "rollback"]


async def test_listeners_remain_scoped_to_one_database_engine(event_db):
    calls = []

    @event_db.on("commit")
    def commit(connection):
        calls.append(connection.engine)

    await init_db(event_db.engine.url.render_as_string(hide_password=False), name="other", is_default=False)
    try:
        async with ctx_session("other") as session:
            await session.execute("SELECT 1")
        assert calls == []
        async with ctx_session() as session:
            await session.execute("SELECT 1")
        assert calls == [event_db.engine.sync_engine]
    finally:
        await close_db("other")

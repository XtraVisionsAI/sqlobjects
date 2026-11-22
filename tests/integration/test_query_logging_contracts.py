"""SQL logging follows driver execution across every ORM entry point."""

import asyncio
import inspect
import logging
from unittest.mock import patch

import pytest
from sqlalchemy import event, insert

from sqlobjects.database import close_db, init_db
from sqlobjects.exceptions import IntegrityError
from sqlobjects.session import ctx_session
from tests.integration.test_orm_contracts import ContractRecord
from tests.integration.test_orm_contracts import clean_db as _clean_db
from tests.integration.test_orm_contracts import contract_db as _contract_db


clean_db = _clean_db
contract_db = _contract_db


@pytest.fixture
def query_records(contract_db):
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Capture()
    logger = logging.getLogger("sqlobjects.sql")
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


@pytest.mark.usefixtures("contract_db")
class TestQueryLogging:
    @pytest.mark.parametrize("operation", ["save", "bulk", "raw", "session", "driver", "stream", "count"])
    async def test_entry_points_log_each_driver_execution_once(self, operation, query_records, contract_db):
        statements = []

        def executed(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(contract_db.engine.sync_engine, "after_cursor_execute", executed)
        try:
            if operation == "save":
                obj = ContractRecord(name="saved")
                await obj.save(cascade=False)
                obj.value = 4
                await obj.save(cascade=False)
                await obj.delete(cascade=False)
            elif operation == "bulk":
                await ContractRecord.objects.bulk_create([{"name": "first"}, {"name": "second"}])
            elif operation == "raw":
                await ContractRecord.objects.raw("SELECT id, name, value FROM contract_records")
            elif operation == "session":
                async with ctx_session() as session:
                    await session.execute("SELECT 1")
            elif operation == "driver":
                async with contract_db.engine.connect() as connection:
                    await connection.exec_driver_sql("SELECT 1")
            elif operation == "stream":
                assert [row async for row in ContractRecord.objects.iterator(chunk_size=1)] == []
            else:
                assert await ContractRecord.objects.count() == 0
        finally:
            event.remove(contract_db.engine.sync_engine, "after_cursor_execute", executed)
        assert statements
        assert [record.sql for record in query_records] == statements
        for record in query_records:
            assert record.db_name == "default"
            assert record.dialect == contract_db.engine.dialect.name
            assert record.success is True
            assert record.error_type is None
            assert isinstance(record.duration_ms, float)
            assert record.duration_ms >= 0
            assert isinstance(record.rowcount, int)

    async def test_caller_survives_async_engine_greenlet(self, query_records):
        frame = inspect.currentframe()
        assert frame is not None
        line = frame.f_lineno + 1
        await ContractRecord.objects.count()
        del frame
        assert len(query_records) == 1
        assert query_records[0].pathname == __file__
        assert query_records[0].funcName == "test_caller_survives_async_engine_greenlet"
        assert query_records[0].lineno == line

    async def test_expanded_parameters_match_actual_sql(self, query_records):
        await ContractRecord.objects.filter(ContractRecord.name.in_(["one", "two"])).all()
        assert len(query_records) == 1
        record = query_records[0]
        assert "POSTCOMPILE" not in record.sql
        values = record.params.values() if isinstance(record.params, dict) else record.params
        assert list(values) == ["one", "two"]

    async def test_driver_sql_uses_rewritten_statement_without_parameters(self, query_records, contract_db):
        def rewrite(conn, cursor, statement, parameters, context, executemany):
            return statement + " /* rewritten */", parameters

        event.listen(contract_db.engine.sync_engine, "before_cursor_execute", rewrite, retval=True)
        try:
            async with contract_db.engine.connect() as connection:
                await connection.exec_driver_sql("SELECT 1", execution_options={"no_parameters": True})
        finally:
            event.remove(contract_db.engine.sync_engine, "before_cursor_execute", rewrite)
        assert len(query_records) == 1
        assert query_records[0].sql == "SELECT 1 /* rewritten */"
        assert query_records[0].params is None
        assert query_records[0].executemany is False

    async def test_executemany_is_logged_as_one_driver_call(self, query_records):
        async with ctx_session() as session:
            await session.execute(insert(ContractRecord.__table__), [{"name": "one"}, {"name": "two"}])
        assert len(query_records) == 1
        assert query_records[0].executemany is True
        assert len(query_records[0].params) == 2

    async def test_returning_batches_have_separate_records(self, query_records, contract_db):
        if not contract_db.engine.dialect.insert_executemany_returning:
            pytest.skip("Backend does not support executemany RETURNING")
        statement = (
            insert(ContractRecord.__table__)
            .returning(ContractRecord.__table__.c.id)
            .execution_options(insertmanyvalues_page_size=1)
        )
        async with ctx_session() as session:
            result = await session.execute(statement, [{"name": "one"}, {"name": "two"}])
            assert len(result.all()) == 2
        assert len(query_records) == 2
        assert all(record.success and record.duration_ms >= 0 for record in query_records)
        assert query_records[0].params != query_records[1].params

    async def test_concurrent_database_aliases_do_not_mix_records(self, query_records, contract_db):
        await init_db(contract_db.engine.url.render_as_string(hide_password=False), name="other", is_default=False)
        try:

            async def read(alias):
                assert await ContractRecord.objects.using(alias).count() == 0

            await asyncio.gather(*(read(alias) for alias in ["default", "other"] * 3))
            assert len(query_records) == 6
            assert sum(record.db_name == "default" for record in query_records) == 3
            assert sum(record.db_name == "other" for record in query_records) == 3
        finally:
            await close_db("other")

    async def test_failure_is_logged_once_and_recovery_has_new_timing(self, query_records):
        await ContractRecord.objects.create(name="duplicate")
        query_records.clear()
        async with ctx_session() as session:
            with pytest.raises(IntegrityError):
                await ContractRecord.objects.create(name="duplicate")
            assert len(query_records) == 1
            failed = query_records[0]
            assert failed.success is False
            assert failed.error_type == "IntegrityError"
            # Driver class names vary (asyncpg on SQLAlchemy 2.1: UniqueViolationError).
            assert failed.driver_error_type in {"IntegrityError", "UniqueViolationError"}
            assert failed.rowcount is None
            assert failed.duration_ms >= 0
            await session.rollback()
            await session.execute("SELECT 1")
        assert len(query_records) == 2
        assert query_records[1].success is True
        assert query_records[1].error_type is None
        assert query_records[1].driver_error_type is None

    async def test_hidden_parameters_stay_hidden_on_success_and_error(self, query_records, contract_db):
        await init_db(
            contract_db.engine.url.render_as_string(hide_password=False),
            name="hidden",
            is_default=False,
            hide_parameters=True,
        )
        try:
            await ContractRecord.objects.using("hidden").create(name="private-value")
            with pytest.raises(IntegrityError):
                await ContractRecord.objects.using("hidden").create(name="private-value")
            records = [record for record in query_records if record.db_name == "hidden"]
            assert len(records) == 2
            assert [record.success for record in records] == [True, False]
            for record in records:
                assert record.params is None
                assert "private-value" not in str(record.__dict__)
        finally:
            await close_db("hidden")

    async def test_disabled_logging_skips_timing_and_stack_inspection(self, query_records):
        logging.getLogger("sqlobjects.sql").setLevel(logging.WARNING)
        with (
            patch("sqlobjects.sql_logging.perf_counter", side_effect=AssertionError("unexpected timing")),
            patch("sqlobjects.sql_logging._find_user_frame", side_effect=AssertionError("unexpected stack walk")),
        ):
            await ContractRecord.objects.create(name="quiet")
            with pytest.raises(IntegrityError):
                await ContractRecord.objects.create(name="quiet")
            await ContractRecord.objects.count()
        assert query_records == []

    async def test_handler_error_cannot_rollback_or_mask_database_error(self, query_records):
        class BrokenHandler(logging.Handler):
            def emit(self, record):
                raise RuntimeError("logging failed")

        logger = logging.getLogger("sqlobjects.sql")
        handler = BrokenHandler()
        logger.addHandler(handler)
        try:
            await ContractRecord.objects.create(name="stored")
            with pytest.raises(IntegrityError):
                await ContractRecord.objects.create(name="stored")
        finally:
            logger.removeHandler(handler)
        assert await ContractRecord.objects.count() == 1

    async def test_cancelled_execution_keeps_original_exception(self, query_records, contract_db):
        def cancel(cursor, statement, parameters, context):
            raise asyncio.CancelledError

        event.listen(contract_db.engine.sync_engine, "do_execute", cancel)
        try:
            with pytest.raises(asyncio.CancelledError):
                async with ctx_session() as session:
                    await session.execute("SELECT 1")
        finally:
            event.remove(contract_db.engine.sync_engine, "do_execute", cancel)
        assert len(query_records) == 1
        assert query_records[0].success is False
        assert query_records[0].error_type == "CancelledError"

# tests/integration/test_sql_logging_integration.py
"""Integration tests: QueryExecutor emits SQL log records."""

import logging

import pytest

from sqlobjects.session import ctx_session
from sqlobjects.sql_logging import SQLCallerFilter
from tests.conftest import User


@pytest.fixture
def sql_records(test_db):
    """Capture log records from sqlobjects.sql logger."""
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Capture()
    handler.addFilter(SQLCallerFilter())
    sql_logger = logging.getLogger("sqlobjects.sql")
    original_level = sql_logger.level  # save original level
    sql_logger.setLevel(logging.DEBUG)
    sql_logger.addHandler(handler)
    yield records
    sql_logger.removeHandler(handler)
    sql_logger.setLevel(original_level)  # restore exactly


@pytest.mark.asyncio
async def test_executor_emits_log_on_query(sql_records, test_db):
    """QueryExecutor emits a log record for each executed query."""
    async with ctx_session() as session:
        await User.objects.using(session).all()

    assert len(sql_records) >= 1


@pytest.mark.asyncio
async def test_log_record_has_sql_field(sql_records, test_db):
    """Log record carries sql field in extra."""
    async with ctx_session() as session:
        await User.objects.using(session).all()

    record = sql_records[0]
    assert hasattr(record, "sql")
    assert "SELECT" in record.sql.upper()


@pytest.mark.asyncio
async def test_log_record_has_duration_ms(sql_records, test_db):
    """Log record carries duration_ms field."""
    async with ctx_session() as session:
        await User.objects.using(session).all()

    record = sql_records[0]
    assert hasattr(record, "duration_ms")
    assert isinstance(record.duration_ms, float)
    assert record.duration_ms >= 0


@pytest.mark.asyncio
async def test_caller_points_to_user_code(sql_records, test_db):
    """After SQLCallerFilter, record.filename points to user code, not executor."""
    async with ctx_session() as session:
        await User.objects.using(session).all()

    record = sql_records[0]
    # executor.py is an internal sqlobjects file — filter should have replaced it
    assert "executor" not in record.filename
    assert "site-packages" not in record.pathname


@pytest.mark.asyncio
async def test_no_log_when_logger_disabled(test_db):
    """When sqlobjects.sql logger level is above DEBUG, no records are emitted."""
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Capture()
    sql_logger = logging.getLogger("sqlobjects.sql")
    original_level = sql_logger.level
    sql_logger.setLevel(logging.WARNING)  # above DEBUG
    sql_logger.addHandler(handler)

    try:
        async with ctx_session() as session:
            await User.objects.using(session).all()
        assert len(records) == 0
    finally:
        sql_logger.removeHandler(handler)
        sql_logger.setLevel(original_level)

"""Isolated databases and descriptive measurements for performance workloads."""

import json
import platform
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass

import psutil
import pytest
import sqlalchemy
from sqlalchemy import event

from sqlobjects.database import close_db, create_tables, drop_tables, get_database, init_db
from sqlobjects.session import ctx_session
from tests.conftest import Post, PostTag, Profile, Tag, TestModel, User
from tests.test_config import TestDatabaseConfig


@pytest.fixture
async def test_db(db_type, tmp_path):
    # A file gives concurrent SQLite sessions separate physical connections.
    # Only create these models: unrelated integration models have dialect-specific DDL.
    from tests.performance.test_deferred_performance import PerformanceTestUser

    models = [User, Post, Tag, Profile, PostTag, PerformanceTestUser]
    config = TestDatabaseConfig.get_config(db_type)
    url = f"sqlite+aiosqlite:///{tmp_path / 'performance.db'}" if db_type == "sqlite" else config["url"]
    await init_db(url, **config["pool_config"])
    try:
        await create_tables(TestModel, tables=models)
        yield db_type
    finally:
        try:
            await drop_tables(TestModel, tables=models)
        finally:
            await close_db()


@pytest.fixture(autouse=True)
def clean_db(test_db):
    """The local test_db fixture owns schema cleanup, including committed writes."""


@pytest.fixture
async def large_dataset(test_db):
    # Do not hydrate or retain a second copy of every model before measuring reads.
    # Commit before workers open their own sessions.
    async with ctx_session() as seed_session:
        await User.objects.using(seed_session).bulk_create(
            [
                {"username": f"user{i}", "email": f"user{i}@example.com", "age": 20 + i % 50, "bio": "x" * 256}
                for i in range(10000)
            ]
        )


@dataclass
class Measurement:
    name: str
    seconds: float = 0.0
    cpu_seconds: float = 0.0
    rss_delta_mib: float = 0.0
    statements: int = 0


class Benchmark:
    """Record observations; correctness and SQL counts determine pass/fail."""

    def __init__(self):
        self.samples: list[Measurement] = []
        self.statements: list[str] = []
        self.process = psutil.Process()

    def before_execute(self, connection, cursor, statement, parameters, context, executemany):
        self.statements.append(statement)

    @contextmanager
    def measure(self, name):
        sample = Measurement(name)
        queries_before = len(self.statements)
        rss_before = self.process.memory_info().rss
        cpu_before = time.process_time()
        start = time.perf_counter()
        try:
            yield sample
        finally:
            sample.seconds = time.perf_counter() - start
            sample.cpu_seconds = time.process_time() - cpu_before
            sample.rss_delta_mib = (self.process.memory_info().rss - rss_before) / 1024**2
            sample.statements = len(self.statements) - queries_before
            self.samples.append(sample)


@pytest.fixture
async def benchmark(test_db, record_property):
    engine = get_database().engine.sync_engine
    result = Benchmark()
    event.listen(engine, "before_cursor_execute", result.before_execute)
    record_property(
        "environment",
        json.dumps(
            {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "sqlalchemy": sqlalchemy.__version__,
                "database": engine.dialect.name,
                "driver": engine.dialect.driver,
                "server_version": engine.dialect.server_version_info,
            }
        ),
    )
    try:
        yield result
    finally:
        event.remove(engine, "before_cursor_execute", result.before_execute)
        for sample in result.samples:
            data = json.dumps(asdict(sample), sort_keys=True)
            record_property("measurement", data)
            print(data)

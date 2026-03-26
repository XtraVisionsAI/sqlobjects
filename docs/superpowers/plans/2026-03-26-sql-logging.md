# SQL Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 sqlobjects 提供 SQL 日志功能，日志 caller 显示用户代码的真实调用位置，兼容标准 logging 和 loguru。

**Architecture:** 在 `QueryExecutor._execute_query()` 执行前后用标准 `logging.getLogger("sqlobjects.sql")` 发出日志；提供 `SQLCallerFilter`（标准 `logging.Filter` 子类），在 `filter()` 中 inspect 调用栈、过滤第三方库帧，并覆盖 `LogRecord` 的 `filename`/`funcName`/`lineno`/`pathname` 字段，使任何 handler 无需额外配置即可显示正确 caller；同时提供 `get_caller_frame()` helper 供调用端自定义场景复用。

**Tech Stack:** Python `logging`, `inspect`, SQLAlchemy async, pytest, pytest-asyncio

---

## 文件结构

| 文件 | 动作 | 职责 |
|------|------|------|
| `sqlobjects/sql_logging.py` | 新建 | `SQLCallerFilter` + `get_caller_frame()` |
| `sqlobjects/queries/executor.py` | 修改 | `_execute_query` 增加发日志逻辑 |
| `sqlobjects/__init__.py` | 修改 | 导出 `SQLCallerFilter`, `get_caller_frame` |
| `tests/unit/test_sql_logging.py` | 新建 | `SQLCallerFilter` 和 `get_caller_frame` 单元测试 |
| `tests/integration/test_sql_logging_integration.py` | 新建 | executor 发日志的集成测试 |

> **注意：** 模块命名为 `sql_logging.py` 而非 `logging.py`，避免与标准库 `logging` 模块名称冲突。
>
> **editable install 说明：** 过滤逻辑同时跳过 `site-packages` 帧（pip install）和所有 `sqlobjects.*` 模块名的帧（editable install / pip install -e .），确保在两种安装方式下均能正确定位用户代码。

---

## Task 1: `get_caller_frame()` helper

**Files:**
- Create: `sqlobjects/sql_logging.py`
- Test: `tests/unit/test_sql_logging.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_sql_logging.py
import logging

from sqlobjects.sql_logging import get_caller_frame


def test_get_caller_frame_returns_string():
    """get_caller_frame 默认返回一个字符串"""
    result = get_caller_frame()
    assert isinstance(result, str)


def test_get_caller_frame_contains_this_file():
    """默认 max_frames=1 时，返回的帧应指向调用者（本测试文件）"""
    result = get_caller_frame()
    # 结果形如 "tests/unit/test_sql_logging.py:15 in test_get_caller_frame_contains_this_file"
    assert "test_sql_logging" in result


def test_get_caller_frame_max_frames_list():
    """max_frames > 1 时返回列表"""
    result = get_caller_frame(max_frames=3)
    assert isinstance(result, list)
    assert len(result) >= 1  # 至少有一帧


def test_get_caller_frame_skips_site_packages():
    """不应返回 site-packages 中的帧"""
    result = get_caller_frame(max_frames=5)
    frames = result if isinstance(result, list) else [result]
    for frame in frames:
        assert "site-packages" not in frame


def test_get_caller_frame_skips_sqlobjects_frames():
    """不应返回 sqlobjects 内部帧（editable install 兼容）"""
    result = get_caller_frame(max_frames=5)
    frames = result if isinstance(result, list) else [result]
    for frame in frames:
        # 每一帧都不应该是 sqlobjects 内部代码（除非是测试文件本身）
        assert not ("sqlobjects" in frame and "test" not in frame)


def test_get_caller_frame_extra_skip_packages():
    """extra_skip_packages 可以跳过指定模块名前缀的帧"""
    # 跳过本测试模块自身（使用完整模块名前缀）
    result = get_caller_frame(
        max_frames=3,
        extra_skip_packages=["tests.unit.test_sql_logging"],
    )
    frames = result if isinstance(result, list) else [result]
    for frame in frames:
        assert "test_sql_logging" not in frame
```

- [ ] **Step 2: 确认测试失败**

```bash
pytest tests/unit/test_sql_logging.py -v
```

Expected: `ModuleNotFoundError: No module named 'sqlobjects.sql_logging'`

- [ ] **Step 3: 实现 `get_caller_frame()`**

```python
# sqlobjects/sql_logging.py
"""SQL logging utilities for sqlobjects.

Provides SQLCallerFilter and get_caller_frame() to surface user-code caller
information in SQL log records, compatible with standard logging and loguru.

Filter strategy:
- Skips frames from site-packages (covers pip-installed sqlobjects/sqlalchemy)
- Skips frames whose module name starts with "sqlobjects." or "sqlalchemy."
  (covers editable installs via `pip install -e .`)
- Skips frames from extra_skip_packages specified by the caller
"""
from __future__ import annotations

import inspect
import logging
import os
from typing import Union


# Module name prefixes that are always considered internal
_INTERNAL_PREFIXES = ("sqlobjects.", "sqlalchemy.", "sqlobjects", "sqlalchemy")


def get_caller_frame(
    extra_skip_packages: list[str] | None = None,
    max_frames: int = 1,
) -> Union[str, list[str]]:
    """Inspect the call stack and return the first user-code frame(s).

    Skips frames from:
    - site-packages (pip install)
    - sqlobjects.* and sqlalchemy.* modules (editable install)
    - extra_skip_packages prefixes provided by the caller

    Args:
        extra_skip_packages: Additional module name prefixes to skip
            (e.g. ["myapp.middleware"]). Matched against frame's __name__.
        max_frames: How many user-code frames to return.
            1 returns a str; >1 returns a list[str].

    Returns:
        Frame string "path/to/file.py:lineno in funcname", or a list of such
        strings when max_frames > 1.
    """
    skip_prefixes = _INTERNAL_PREFIXES
    if extra_skip_packages:
        skip_prefixes = skip_prefixes + tuple(extra_skip_packages)

    frames: list[str] = []

    for frame_info in inspect.stack():
        filepath = frame_info.filename
        module = frame_info.frame.f_globals.get("__name__", "")

        # Skip site-packages frames (pip-installed third-party libs)
        if "site-packages" in filepath:
            continue

        # Skip sqlobjects/sqlalchemy frames (editable install)
        if module.startswith(skip_prefixes):
            continue

        # Skip this helper file itself
        if os.path.basename(filepath) == "sql_logging.py":
            continue

        rel_path = _relative_path(filepath)
        frames.append(f"{rel_path}:{frame_info.lineno} in {frame_info.function}")

        if len(frames) >= max_frames:
            break

    if not frames:
        return "<unknown>" if max_frames == 1 else ["<unknown>"]

    return frames[0] if max_frames == 1 else frames


def _relative_path(filepath: str) -> str:
    """Return path relative to cwd, or absolute if outside cwd."""
    try:
        return os.path.relpath(filepath)
    except ValueError:
        return filepath
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/unit/test_sql_logging.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add sqlobjects/sql_logging.py tests/unit/test_sql_logging.py
git commit -m "feat(logging): add get_caller_frame() helper"
```

---

## Task 2: `SQLCallerFilter`

**Files:**
- Modify: `sqlobjects/sql_logging.py`
- Test: `tests/unit/test_sql_logging.py`

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_sql_logging.py` 末尾追加：

```python
def _make_record(extra: dict | None = None) -> logging.LogRecord:
    """Helper: create a LogRecord with given extra fields."""
    base_extra = {"sql": "SELECT 1", "params": {}, "duration_ms": 1.5}
    if extra:
        base_extra.update(extra)
    logger = logging.getLogger("sqlobjects.sql.test")
    record = logger.makeRecord(
        name="sqlobjects.sql",
        level=logging.DEBUG,
        fn="executor.py",   # will be overwritten by filter
        lno=99,             # will be overwritten
        msg="SELECT 1",
        args=(),
        exc_info=None,
        extra=base_extra,
    )
    return record


def test_sql_caller_filter_overwrites_caller_fields():
    """SQLCallerFilter 覆盖 record 的 filename/funcName/lineno/pathname"""
    from sqlobjects.sql_logging import SQLCallerFilter

    f = SQLCallerFilter()
    record = _make_record()
    f.filter(record)

    # After filter, caller should point to this test file, not executor.py
    assert "executor" not in record.filename
    assert "test_sql_logging" in record.filename
    assert isinstance(record.lineno, int)
    assert record.lineno != 99


def test_sql_caller_filter_injects_duration_ms():
    """SQLCallerFilter 将 duration_ms 保留在 record 上"""
    from sqlobjects.sql_logging import SQLCallerFilter

    f = SQLCallerFilter()
    record = _make_record()
    f.filter(record)

    assert hasattr(record, "duration_ms")
    assert record.duration_ms == 1.5


def test_sql_caller_filter_max_frames_one_sets_string_caller():
    """max_frames=1 时 record.caller 是字符串"""
    from sqlobjects.sql_logging import SQLCallerFilter

    f = SQLCallerFilter(max_frames=1)
    record = _make_record()
    f.filter(record)

    assert isinstance(record.caller, str)
    assert "test_sql_logging" in record.caller


def test_sql_caller_filter_max_frames_multiple_sets_list():
    """max_frames=3 时 record.caller 是列表"""
    from sqlobjects.sql_logging import SQLCallerFilter

    f = SQLCallerFilter(max_frames=3)
    record = _make_record()
    f.filter(record)

    assert isinstance(record.caller, list)


def test_sql_caller_filter_returns_true():
    """filter() 始终返回 True（不丢弃任何记录）"""
    from sqlobjects.sql_logging import SQLCallerFilter

    f = SQLCallerFilter()
    record = _make_record()
    result = f.filter(record)

    assert result is True
```

- [ ] **Step 2: 确认测试失败**

```bash
pytest tests/unit/test_sql_logging.py -v -k "filter"
```

Expected: `ImportError` 或 `AttributeError: type object 'SQLCallerFilter' has no attribute`

- [ ] **Step 3: 实现 `SQLCallerFilter`**

在 `sqlobjects/sql_logging.py` 末尾追加：

```python
class SQLCallerFilter(logging.Filter):
    """logging.Filter that rewrites LogRecord caller fields to user-code location.

    Inspects the call stack at filter time, skips library frames (site-packages
    and sqlobjects.*/sqlalchemy.* modules for editable installs), and overwrites
    record.filename / record.funcName / record.lineno / record.pathname so that
    any handler (including loguru interception) displays the real user-code
    call site.

    Also exposes record.caller (str or list[str]) for use in custom Formatters.

    Args:
        max_frames: Number of user-code frames to capture (default 1).
            When 1, record.caller is a str and record location fields point
            to that single frame.
            When > 1, record.caller is a list[str] and record location fields
            are set from the first (most recent) frame.
        extra_skip_packages: Additional module name prefixes to skip
            (matched against frame's __name__).
    """

    def __init__(
        self,
        max_frames: int = 1,
        extra_skip_packages: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.max_frames = max_frames
        self.extra_skip_packages = list(extra_skip_packages) if extra_skip_packages else []

    def filter(self, record: logging.LogRecord) -> bool:
        caller = get_caller_frame(
            extra_skip_packages=self.extra_skip_packages or None,
            max_frames=self.max_frames,
        )
        record.caller = caller  # type: ignore[attr-defined]

        # Overwrite standard location fields from the first user frame
        first = caller if isinstance(caller, str) else (caller[0] if caller else "<unknown>")
        self._overwrite_record_location(record, first)

        return True

    @staticmethod
    def _overwrite_record_location(record: logging.LogRecord, frame_str: str) -> None:
        """Parse 'path/to/file.py:lineno in funcname' and overwrite record fields.

        Frame string format: "relative/path/to/file.py:42 in func_name"
        Uses rsplit to handle edge cases where function name could have spaces.
        """
        try:
            # Split off the function name part (rightmost " in ")
            path_part, func_part = frame_str.rsplit(" in ", 1)
            # Split off the line number (rightmost ":")
            filepath, lineno_str = path_part.rsplit(":", 1)
            record.pathname = os.path.abspath(filepath)
            record.filename = os.path.basename(filepath)
            record.module = os.path.splitext(record.filename)[0]
            record.funcName = func_part.strip()
            record.lineno = int(lineno_str)
        except (ValueError, AttributeError):
            pass  # Keep original fields if parsing fails
```

- [ ] **Step 4: 运行所有 sql_logging 单元测试**

```bash
pytest tests/unit/test_sql_logging.py -v
```

Expected: 全部通过（11 passed）

- [ ] **Step 5: Commit**

```bash
git add sqlobjects/sql_logging.py tests/unit/test_sql_logging.py
git commit -m "feat(logging): add SQLCallerFilter"
```

---

## Task 3: `QueryExecutor` 发出 SQL 日志

**Files:**
- Modify: `sqlobjects/queries/executor.py`
- Test: `tests/integration/test_sql_logging_integration.py`

- [ ] **Step 1: 写失败测试**

注意：集成测试使用 `test_db` fixture（来自 `tests/conftest.py`）和 `ctx_session()`，与项目现有模式一致。

```python
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
    original_level = sql_logger.level   # save original level
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
    sql_logger.setLevel(logging.WARNING)  # above DEBUG
    sql_logger.addHandler(handler)

    try:
        async with ctx_session() as session:
            await User.objects.using(session).all()
        assert len(records) == 0
    finally:
        sql_logger.removeHandler(handler)
```

- [ ] **Step 2: 确认测试失败**

```bash
pytest tests/integration/test_sql_logging_integration.py -v
```

Expected: FAIL（`sqlobjects.sql` logger 未发出任何记录）

- [ ] **Step 3: 修改 `QueryExecutor._execute_query`**

在 `sqlobjects/queries/executor.py` 顶部 import 区（`import asyncio` 之后）追加：

```python
import logging
import time

_sql_logger = logging.getLogger("sqlobjects.sql")
```

将 `_execute_query` 方法中的 `result = await session.execute(query)` 这一行替换为：

```python
        # Compile SQL for logging only when the logger is active (avoids overhead)
        if _sql_logger.isEnabledFor(logging.DEBUG):
            try:
                compiled = query.compile(
                    dialect=session.bind.dialect,
                    compile_kwargs={"literal_binds": False},
                )
                sql_str = str(compiled)
                params = dict(compiled.params) if compiled.params else {}
            except Exception:
                sql_str = str(query)
                params = {}
        else:
            sql_str = ""
            params = {}

        t0 = time.perf_counter()
        result = await session.execute(query)
        duration_ms = (time.perf_counter() - t0) * 1000

        if _sql_logger.isEnabledFor(logging.DEBUG):
            _sql_logger.debug(
                sql_str,
                extra={"sql": sql_str, "params": params, "duration_ms": duration_ms},
            )
```

- [ ] **Step 4: 运行集成测试**

```bash
pytest tests/integration/test_sql_logging_integration.py -v
```

Expected: 5 passed

- [ ] **Step 5: 确认原有测试不受影响**

```bash
pytest tests/ -v --ignore=tests/performance -x -q
```

Expected: 全部通过

- [ ] **Step 6: Commit**

```bash
git add sqlobjects/queries/executor.py tests/integration/test_sql_logging_integration.py
git commit -m "feat(logging): emit SQL log records in QueryExecutor"
```

---

## Task 4: 导出公共 API

**Files:**
- Modify: `sqlobjects/__init__.py`

- [ ] **Step 1: 确认导入目前不存在**

```bash
python -c "from sqlobjects import SQLCallerFilter" 2>&1
```

Expected: `ImportError: cannot import name 'SQLCallerFilter'`

- [ ] **Step 2: 在 `sqlobjects/__init__.py` 中追加导入和 `__all__` 条目**

在现有 import 区末尾追加：

```python
from .sql_logging import SQLCallerFilter, get_caller_frame
```

在 `__all__` 列表末尾追加：

```python
    # SQL logging
    "SQLCallerFilter",
    "get_caller_frame",
```

- [ ] **Step 3: 验证导入可用**

```bash
python -c "from sqlobjects import SQLCallerFilter, get_caller_frame; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: 运行全量测试**

```bash
pytest tests/ -v --ignore=tests/performance -x -q
```

Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add sqlobjects/__init__.py
git commit -m "feat(logging): export SQLCallerFilter and get_caller_frame in public API"
```

---

## 验收标准

1. `from sqlobjects import SQLCallerFilter, get_caller_frame` 可用
2. 配置 `SQLCallerFilter` 后，日志中 `filename`/`funcName`/`lineno` 指向用户代码
3. 不配置任何 handler 时，`sqlobjects.sql` logger 默认静默（不影响现有行为）
4. pip install 和 editable install 两种安装方式下，caller 过滤均正确
5. 全量单元 + 集成测试通过

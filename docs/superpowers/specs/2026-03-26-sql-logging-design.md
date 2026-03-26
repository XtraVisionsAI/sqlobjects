# SQL 日志功能设计文档

**日期**：2026-03-26
**状态**：已实现

---

## 背景

sqlobjects 目前支持通过 `DatabaseConfig(echo=True)` 开启 SQL 日志，但该方式底层由 SQLAlchemy engine 输出，日志的 caller 显示为 SQLAlchemy 内部位置，无法反映真实的用户代码调用位置，调试价值有限。

---

## 目标

在 sqlobjects 中实现 SQL 日志功能，满足以下要求：

1. 日志 caller 显示用户代码的真实调用位置（文件、函数名、行号）
2. 兼容标准 `logging` 模块和 loguru 等第三方日志库
3. 调用端配置简单，开箱即用

---

## 设计

### 核心机制

**sqlobjects 内部**（`QueryExecutor._execute_query`）在执行每条 SQL 前后，使用标准 `logging.getLogger("sqlobjects.sql")` 发出日志，`LogRecord.extra` 携带结构化数据：

- `sql`：原始 SQL 字符串（保留占位符，如 `WHERE id = :id_1`）
- `params`：绑定参数字典
- `duration_ms`：执行耗时（毫秒）

**`SQLCallerFilter`**（`sqlobjects.sql_logging` 模块）是一个标准 `logging.Filter` 子类，负责：

1. 在 `filter()` 中调用 `inspect.stack()` 获取当前调用栈
2. 过滤掉所有来自 `site-packages` 的帧（涵盖 sqlobjects、sqlalchemy 及其他第三方库）
3. 取第一个（或多个）用户代码帧
4. **覆盖** `LogRecord` 的标准字段：`record.filename`、`record.funcName`、`record.lineno`、`record.pathname`
5. 同时将 `duration_ms` 注入到 `record` 上

覆盖标准字段而非写入自定义字段，是为了让 loguru、标准 logging Formatter 等任何 handler 无需额外配置即可直接显示正确的 caller。

### `SQLCallerFilter` 接口

```python
class SQLCallerFilter(logging.Filter):
    def __init__(
        self,
        max_frames: int = 1,
        extra_skip_packages: list[str] | None = None,
    ): ...
```

参数说明：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_frames` | `int` | `1` | 展示的用户代码帧数量，默认只显示最近一帧 |
| `extra_skip_packages` | `list[str]` | `None` | 额外跳过的包名前缀（如调用端自己的中间件层） |

### 堆栈过滤逻辑

过滤规则：跳过 `pathname` 中包含 `site-packages` 的帧。这一规则覆盖所有通过 pip 安装的第三方库（包括 sqlobjects 自身和 sqlalchemy），无需维护包名列表。

`extra_skip_packages` 用于跳过调用端项目内部不希望出现在日志中的帧（如通用中间件），通过匹配 `frame.f_globals.get("__name__", "")` 的前缀实现。

### `get_caller_frame()` helper

同时提供一个独立的 helper 函数，供需要在自定义逻辑中复用的场景：

```python
def get_caller_frame(
    extra_skip_packages: list[str] | None = None,
    max_frames: int = 1,
) -> str | list[str]: ...
```

---

## 使用示例

### 日志级别控制原则

`sqlobjects.sql` logger 默认级别为 `NOTSET`，会**委托给父 logger（最终到 root）判断级别**。这意味着 SQL 日志天然跟随调用端的 logging 环境配置：

- prod 环境 root 是 `ERROR` → SQL 日志静默
- debug 环境 root 是 `DEBUG` → SQL 日志输出

**不要在 sqlobjects 配置中调用 `setLevel`**，否则会绕过 root 的环境控制逻辑，破坏"仅在 debug 模式输出 SQL 日志"等需求。

如果需要在特定环境独立开启 SQL 日志（如 prod 的 INFO 环境下单独开 SQL debug），由调用端主动设置：

```python
# 调用端主动选择，不是 sqlobjects 默认行为
logging.getLogger("sqlobjects.sql").setLevel(logging.DEBUG)
```

### 标准 logging

```python
import logging
from sqlobjects import SQLCallerFilter

handler = logging.StreamHandler()
handler.addFilter(SQLCallerFilter())
handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(filename)s:%(funcName)s:%(lineno)d - %(message)s | duration=%(duration_ms).1fms"
))

logging.getLogger("sqlobjects.sql").addHandler(handler)
# 不设置 setLevel，跟随 root logger 的环境配置
```

### loguru 拦截

```python
import logging
from loguru import logger
from sqlobjects import SQLCallerFilter

class InterceptHandler(logging.Handler):
    def emit(self, record):
        logger.opt(depth=0).log(record.levelname, record.getMessage())

handler = InterceptHandler()
handler.addFilter(SQLCallerFilter())
logging.getLogger("sqlobjects.sql").addHandler(handler)
# 不设置 setLevel，跟随 root logger 的环境配置
```

输出效果（loguru 格式）：

```
2026-03-26 08:57:32 | DEBUG    | app.services.user_service:get_user:42 - SELECT users.id, users.name FROM users WHERE users.id = :id_1 | duration=0.8ms
```

### `max_frames=3` 时的输出

```
2026-03-26 08:57:32 | DEBUG    | app.services.user_service:get_user:42 - SELECT users.id, users.name FROM users WHERE users.id = :id_1
  app/services/user_service.py:42 in get_user
  app/api/views.py:18 in user_detail
  app/middleware/auth.py:55 in dispatch
  duration=0.8ms
```

---

## 文件结构

```
sqlobjects/
  sql_logging.py      # SQLCallerFilter + get_caller_frame()
  queries/
    executor.py       # 修改：_execute_query 增加日志发出逻辑
  __init__.py         # 导出 SQLCallerFilter, get_caller_frame
```

---

## 不在此次范围内

- 慢查询阈值告警
- SQL 参数内联展示（保留占位符输出）
- 异步上下文追踪（request id 注入）

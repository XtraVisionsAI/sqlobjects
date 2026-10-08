# 数据库设置和配置

## 概述

SQLObjects 提供灵活的数据库配置，支持单数据库和多数据库，具有自动连接管理、会话处理和事务控制功能。

## 快速开始

### 单数据库设置

```python
from sqlobjects.database import init_db, create_tables
from sqlobjects.model import ObjectModel

# 初始化数据库
db = await init_db("sqlite+aiosqlite:///app.db")

# 创建表
await create_tables(ObjectModel)

# 准备使用
user = await User.objects.create(username="john")
```

### 多数据库设置

```python
from sqlobjects.database import init_dbs

# 初始化多个数据库 - 返回 Database 实例元组
main_db, analytics_db = await init_dbs({
    "main": {"url": "postgresql+asyncpg://user:pass@localhost/main"},
    "analytics": {"url": "sqlite+aiosqlite:///analytics.db"}
}, default="main")

# 按名称使用特定数据库
user = await User.objects.using("analytics").create(username="john")

# 或直接使用 Database 实例
user = await User.objects.using(analytics_db).create(username="jane")
```

## 数据库配置

### 连接参数

```python
from sqlobjects.database import DatabaseConfig

# 高级配置
config = DatabaseConfig(
    "postgresql://user:pass@localhost/db",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,
    echo=False  # 设置为 True 启用 SQL 日志
)

db = await init_db(config.url, **config.engine_kwargs)
```

### 基于环境的配置

```python
import os

# 开发环境
if os.getenv("ENV") == "development":
    db_url = "sqlite+aiosqlite:///dev.db"
    echo = True
# 生产环境
else:
    db_url = os.getenv("DATABASE_URL")
    echo = False

db = await init_db(db_url, echo=echo)
```

## 会话管理

### 上下文管理器

```python
from sqlobjects.session import ctx_session, ctx_sessions

# 单数据库会话（推荐）
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="alice")
    posts = await user.load_relation("posts")
    # 成功时自动提交，错误时回滚

# 特定数据库会话
async with ctx_session("analytics") as session:
    logs = await Log.objects.using(session).all()

# 多数据库会话
async with ctx_sessions("main", "analytics") as sessions:
    user = await User.objects.using(sessions["main"]).create(username="bob")
    await Log.objects.using(sessions["analytics"]).create(message="User created")

# 使用特定数据库的会话
async with ctx_session("analytics") as session:
    users = await User.objects.using(session).all()

# 在可能已持有事务的调用链内：复用外层会话，而不是新开第二条物理连接
# （第二条连接对外层事务锁定行的写入会永久阻塞，且数据库死锁检测器发现不了）
async with ctx_session(join_ambient=True) as session:
    # 存在外层会话时直接复用；只有最外层才会新建会话。
    # 提交/回滚/关闭由最外层所有者负责。
    await User.objects.using(session).create(username="carol")
```

### 检查会话可用性

```python
from sqlobjects.session import has_session

# 检查当前上下文中是否存在显式会话
if has_session():
    # 在 ctx_session() 块内
    pass

# 检查特定数据库的会话
if has_session("analytics"):
    # 在 ctx_session("analytics") 块内
    pass
```

`has_session()` 只报告当前 asyncio task 可用的会话；从父 task 继承下来、
但属于另一个仍在运行的 task 的会话不会被视为可用。

### 默认会话使用

```python
# 自动使用默认数据库
user = await User.objects.create(username="charlie")
users = await User.objects.filter(User.is_active == True).all()
```

## 事务模式

### 统一事务

```python
# 所有操作在单个事务中
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="david")
    profile = await Profile.objects.using(session).create(user_id=user.id)
    # 成功时自动提交，错误时回滚
```

### 显式事务中的失败处理

在显式事务里，一条 SQL 语句失败后（且不在 savepoint 内），该事务在回滚前不可再用：
仅捕获异常并不能恢复它，后续语句会抛出 `TransactionError`。要么调用 `rollback()`，
要么把可能失败的语句包在 `async with await session.begin_nested():` 中，让失败只回滚
到 savepoint：

```python
from sqlalchemy.exc import IntegrityError

async with ctx_session() as session:
    try:
        async with await session.begin_nested():
            await User.objects.create(username="duplicate")
    except IntegrityError:
        pass
    await User.objects.create(username="next")  # 事务仍可用
```

只读会话不持有事务，每条语句执行后即释放连接，因此只读会话中某次查询失败不会影响
后续查询。在隐式（自动提交）会话上调用 `begin_nested()` 会只为 savepoint 打开一个
事务：最外层 savepoint 释放或回滚后，该事务自动提交并归还连接，savepoint 内已释放的
写入会像普通自动提交语句一样被持久化。

### 独立事务

每个并发 worker 必须自己打开会话。复制 context（`contextvars.copy_context()`）
不会复制其中的会话或连接；从父 task 继承下来的会话不能在另一个仍在运行的
asyncio task 中使用或加入，SQLObjects 会在发出 SQL 之前抛出 `TransactionError`。

```python
import asyncio

async def process_user(user_id):
    async with ctx_session():
        user = await User.objects.get(id=user_id)
        user.is_active = True
        await user.save()

await asyncio.gather(*(process_user(user_id) for user_id in user_ids))
```

各 worker 独立提交，这些事务不会随父事务一起回滚。若要把多个操作放在同一个事务中，
请在拥有该事务的 task 内顺序 `await` 它们。事务内需要超时控制时使用
`asyncio.timeout()`；`asyncio.wait_for()` 会把协程调度到另一个 task 中执行。

会话在 `close()` 或上下文管理器退出后不能重新打开。后台任务即使继承了请求的
context，也必须新建 `ctx_session()`。隐式会话按语句自动释放连接时不会关闭会话对象，
因此在同一 task 内对它的顺序调用仍受支持。显式管理的会话只能在前一个拥有它的 task
结束之后交接给另一个 task。

### 提交后的动作

当某些副作用只应在事务成功提交后执行时，使用 `await session.on_commit(callback)`
或模块级 `on_commit()` 辅助函数。传入一个可调用对象，同步函数和返回 awaitable 的
函数都受支持。

```python
from functools import partial
from sqlobjects.session import ctx_session, on_commit

async with ctx_session() as session:
    user = await User.objects.create(username="alice")
    await session.on_commit(partial(invalidate_user_cache, user.id))
    await on_commit(partial(notify_user_created, user.id), robust=True)
    # 两个回调都会等到当前上下文成功提交后才执行。
```

回调按注册顺序执行，并在提交后被同步 `await`。根事务回滚、提交前被取消以及会话关闭
都会丢弃尚未执行的回调。savepoint 回滚会丢弃在该 savepoint 及其后代中注册的回调；
释放 savepoint 则让回调继续等待根事务提交。请使用
`async with await session.begin_nested()`，或返回的 savepoint 对象的
`commit()` / `rollback()` 方法，嵌套的 savepoint 需按相反顺序结束。

显式可写会话在执行第一条 SQL 之前就可以排队回调。不在事务中时，辅助函数会立即执行
回调。可以通过 `on_commit(callback, db_or_session)` 指定具名数据库或显式会话。
只读会话、已失败、已关闭以及属于其他 task 的会话会拒绝注册。

回调失败无法撤销已完成的提交。默认情况下异常会向上传播并中止后续回调；
`robust=True` 时普通异常只记录日志并继续执行后续回调，但取消（cancellation）
始终传播。分发回调前连接已归还连接池，回调中的 ORM 调用会为已提交的数据库使用新的
会话。在回调中显式复用正在提交的会话会抛出 `TransactionError`；若回调需要事务，
请新开一个 `ctx_session()`。

回调归属于单个数据库事务。`ctx_sessions()` 按顺序提交各数据库，它不是分布式事务，
某个数据库的回调可能在另一个数据库提交之前就已执行。这些进程内回调也不是持久化的
投递队列；若要求在提交后进程崩溃时仍能送达，请使用事务性 outbox 模式。

## 数据库事件

`db.on(name, **options)` 将同步处理器注册到当前数据库的 `engine.sync_engine`。
事件名称、参数和注册选项遵循 SQLAlchemy 的
[Engine、Pool 和 Dialect 事件接口](https://docs.sqlalchemy.org/en/20/core/events.html)。
应在建立需要监听的连接之前注册处理器。

### 连接与事务事件

```python
@db.on("connect")
def on_connect(dbapi_connection, connection_record):
    print("数据库已连接")

@db.on("commit")
def committing(connection):
    print("即将提交事务")

@db.on("rollback")
def rolling_back(connection):
    print("即将回滚事务")

@db.on("reset")
def resetting(dbapi_connection, connection_record, reset_state):
    # SQLAlchemy 2.x 的连接池 reset 事件包含 reset_state 参数。
    pass
```

`commit` 等连接事件接收 SQLAlchemy 同步 `Connection`；`connect` 等连接池事件
接收适配后的 DBAPI 连接，都不是 SQLObjects session。处理器在 SQLAlchemy 的异步
适配层中同步执行；注册协程函数、异步可调用对象或异步生成器函数时会抛出 `TypeError`。
同步处理器也不能返回协程。需要异步驱动初始化时，可参考
[SQLAlchemy 异步事件文档](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-events-with-the-asyncio-extension)
中的适配连接 `run_async()`。

`commit`、`rollback` 在驱动完成操作之前触发，不能证明事务已经提交或回滚。
`before_commit`、`after_commit`、`before_rollback`、`after_rollback` 不是 Engine
事件，旧示例中的这些用法无效，现在会给出明确错误提示。成功提交后的操作请使用：

```python
from sqlobjects.session import ctx_session

async with ctx_session() as session:
    await User.objects.using(session).create(username="alice")
    await session.on_commit(lambda: print("事务已提交"))
```

### 注册选项与移除监听器

```python
from sqlalchemy import event

@db.on("before_cursor_execute", named=True, retval=True)
def annotate_statement(statement, parameters, **kwargs):
    return statement + " /* application */", parameters

# 装饰器保留原函数，可使用 SQLAlchemy 原生接口移除。
event.remove(db.engine.sync_engine, "before_cursor_execute", annotate_statement)
```

选项直接传给 `sqlalchemy.event.listen`，支持范围和返回值约定取决于具体事件。
未知事件与无效选项由 SQLAlchemy 校验。处理器异常遵循原生事件规则传播，不适用
SQL 日志处理器的异常隔离策略。监听器仅绑定当前 engine，不会监听其他数据库别名。
也可以直接使用 `event.listens_for(db.engine.sync_engine, name)` 注册事件。

## 连接生命周期

### 优雅关闭

```python
from sqlobjects.database import close_db, close_dbs

# 按名称关闭特定数据库
await close_db("analytics")

# 关闭并自动重新分配默认数据库
await close_db("main", auto_default=True)

# 关闭多个特定数据库
await close_dbs(["analytics", "backup"])

# 关闭所有数据库（不带参数调用）
await close_dbs()

# 直接关闭 Database 实例
await analytics_db.disconnect()
```

### 健康检查

```python
# 检查数据库连接性
try:
    count = await User.objects.count()
    print(f"数据库健康: {count} 个用户")
except Exception as e:
    print(f"数据库错误: {e}")
```

## SQL 日志

SQLObjects 通过标准 `logging` 模块以日志器名 `sqlobjects.sql` 发出已执行的语句。每个已配置的 engine 都会在 `DEBUG` 级别记录驱动层的游标执行，覆盖 QuerySet 查询、模型实例写入、批量操作、raw SQL、流式查询以及直接使用 `db.engine` 的执行。失败和被取消的驱动执行使用同一个日志器。日志记录不会重新编译 SQL；`DEBUG` 未启用时，事件处理器会跳过计时与调用方帧检查，因此关闭日志几乎没有开销。

### 启用 SQL 日志

```python
import logging

# 在 DEBUG 级别将 SQL 输出到控制台
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("sqlobjects.sql").setLevel(logging.DEBUG)

# 现在任何查询都会记录其 SQL
users = await User.objects.filter(User.is_active == True).all()
```

每条 SQL 日志记录在 `record.__dict__` 中携带结构化数据，可从自定义处理器中消费：

| 字段 | 含义 |
| --- | --- |
| `sql` | 传给驱动的 SQL 字符串，占位符已展开。 |
| `params` | 驱动格式的参数：字典、元组或参数集序列；缺省或被隐藏时为 `None`。 |
| `duration_ms` | 驱动执行耗时（毫秒）。 |
| `db_name`、`dialect` | 配置的数据库别名与 SQL 方言。 |
| `executemany` | 本次驱动调用是否使用 `executemany()`。 |
| `rowcount` | 驱动返回的行数，未知时通常为 `-1`；失败时为 `None`。 |
| `success`、`error_type` | 游标执行结果与异常类名，不包含异常消息或堆栈。 |

一条记录对应一次驱动调用。带 RETURNING 的分批 INSERT 可能产生多条记录；一次驱动 `executemany()` 调用则只为其所有参数集产生一条记录。计时不包含连接池获取、SQL 编译、后续结果读取、模型水合以及事务提交。特别地，流式查询执行成功并不代表后续读取成功。连接、编译和提交阶段的错误不在此游标执行日志的范围内。

初始化数据库时设置 `hide_parameters=True`，可在成功与失败记录中都省略绑定值：

```python
await init_db(database_url, hide_parameters=True)
```

该选项不会脱敏已经内嵌在 raw SQL 中的字面量，请使用绑定参数。自定义日志处理器抛出的普通异常会被抑制，因此它们不会回滚一次成功的写入，也不会替换掉原始的数据库异常。

与之前仅在 QueryExecutor 层记录的日志相比：`params` 现在使用驱动的格式而不再总是字典；`duration_ms` 度量的是游标执行时间，而不是外层会话操作的耗时。

```python
class SQLHandler(logging.Handler):
    def emit(self, record):
        print(f"[{record.duration_ms:.1f}ms] {record.sql}")
        print(f"    params: {record.params}")

sql_logger = logging.getLogger("sqlobjects.sql")
sql_logger.setLevel(logging.DEBUG)
sql_logger.addHandler(SQLHandler())
```

### 调用者位置重写

`sqlobjects.sql` 是一个 `ObjectLogger` 实例（`sqlobjects/sql_logging.py`）。它重写 `makeRecord()`，将每条记录的调用者字段（`pathname`、`filename`、`module`、`funcName`、`lineno`）重写为第一个**用户代码**帧，跳过来自 `sqlobjects.*`、`sqlalchemy.*`、标准 `logging` 包以及任何 `site-packages` 的帧。这意味着日志输出指向应用中发起查询的那一行，而不是库的内部代码，即使调用经过了 SQLAlchemy 的异步 greenlet 桥也能正确定位，并且它对任何处理器（包括 loguru 的 `InterceptHandler`）都有效，无需额外的过滤器配置。

对于自定义场景，你也可以直接解析调用者帧：

```python
from sqlobjects import get_caller_frame

frame = get_caller_frame()                       # "app/service.py:42 in list_users"
frames = get_caller_frame(max_frames=3)          # 帧字符串列表
frame = get_caller_frame(extra_skip_packages=["myapp.middleware"])
```

## 最佳实践

### 连接池

```python
# 为您的工作负载优化
config = DatabaseConfig(
    database_url,
    pool_size=10,      # 基本连接数
    max_overflow=20,   # 突发容量
    pool_timeout=30,   # 连接等待时间
    pool_recycle=3600  # 每小时刷新连接
)
```

### 错误处理

```python
from sqlobjects.exceptions import DatabaseError

try:
    async with ctx_session() as session:
        # 数据库操作
        pass
except DatabaseError as e:
    # 处理数据库特定错误
    logger.error(f"数据库错误: {e}")
except Exception as e:
    # 处理一般错误
    logger.error(f"意外错误: {e}")
```

### 测试设置

```python
import pytest

@pytest.fixture
async def test_db():
    # 隔离的测试数据库
    db = await init_db(
        "sqlite+aiosqlite:///:memory:",
        name="test",
        is_default=False
    )
    await create_tables(ObjectModel, "test")
    yield db
    await close_db("test")
```

## Web 框架集成

### ASGI 中间件（Starlette / FastAPI）

`SessionMiddleware` 为任何 ASGI 框架提供自动的请求级会话管理：

```python
from fastapi import FastAPI
from sqlobjects.contrib.asgi import SessionMiddleware

app = FastAPI()
app.add_middleware(SessionMiddleware)
# 每个请求自动获得托管会话（成功时提交，错误时回滚）

# 可选：指定数据库名称和只读模式
app.add_middleware(SessionMiddleware, db_name="analytics", readonly=True)
```

### FastAPI 依赖注入

`get_db_session` 是一个 FastAPI 依赖项，提供事务性会话：

```python
from fastapi import Depends
from sqlobjects.contrib.fastapi import get_db_session
from sqlobjects.session import AsyncSession

@app.post("/users")
async def create_user(session: AsyncSession = Depends(get_db_session)):
    user = await User.objects.using(session).create(name="Alice")
    return {"id": user.id}
```

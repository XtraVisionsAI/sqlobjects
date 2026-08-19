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
    posts = await user.posts.all()
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

### 独立事务

```python
import asyncio
import contextvars

# 每个任务都有独立的事务
tasks = [
    asyncio.create_task(process_user(user_id), context=contextvars.copy_context())
    for user_id in user_ids
]
await asyncio.gather(*tasks, return_exceptions=True)
```

## 数据库事件

### 连接事件

```python
# 注册数据库事件
@db.on("connect")
def on_connect(conn, record):
    print("数据库已连接")

@db.on("before_commit")
def before_commit(session):
    print("即将提交事务")

@db.on("after_commit")
def after_commit(session):
    print("事务已提交")
```

### SQLAlchemy 事件

```python
from sqlalchemy import event

# 直接注册 SQLAlchemy 事件
@event.listens_for(db.engine.sync_engine, "connect")
def setup_connection(dbapi_connection, connection_record):
    # 配置连接设置
    pass
```

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

SQLObjects 通过标准 `logging` 模块以日志器名 `sqlobjects.sql` 发出已执行的语句。日志是零配置的：查询执行器仅在该日志器确实对 `DEBUG` 启用时才编译 SQL 以供记录，因此关闭日志时没有开销。

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

- `sql` - 编译后的 SQL 字符串（未内联绑定参数）
- `params` - 绑定参数的字典
- `duration_ms` - 执行时间（毫秒）

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

`sqlobjects.sql` 是一个 `ObjectLogger` 实例（`sqlobjects/sql_logging.py`）。它重写 `makeRecord()`，将每条记录的调用者字段（`pathname`、`filename`、`module`、`funcName`、`lineno`）重写为第一个**用户代码**帧，跳过来自 `sqlobjects.*`、`sqlalchemy.*`、标准 `logging` 包以及任何 `site-packages` 的帧。这意味着日志输出指向应用中发起查询的那一行，而不是库的内部代码，并且它对任何处理器（包括 loguru 的 `InterceptHandler`）都有效，无需额外的过滤器配置。

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
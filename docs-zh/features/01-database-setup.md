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
from sqlobjects.database import close_db, close_dbs, close_all_dbs

# 按名称关闭特定数据库
await close_db("analytics")

# 关闭并自动重新分配默认数据库
await close_db("main", auto_default=True)

# 关闭多个特定数据库
await close_dbs(["analytics", "backup"])

# 关闭所有数据库
await close_all_dbs()

# 直接关闭 Database 实例
await analytics_db.close()
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
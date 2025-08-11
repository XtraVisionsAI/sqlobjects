# SQLObjects Database 设计说明文档

## 概述

SQLObjects Database 模块提供多数据库连接管理能力，支持异步数据库操作、统一事件处理和观察者模式解耦。使用 DatabaseManager
进行全局配置管理，通过观察者模式实现组件间的松耦合设计。

## 核心特性

### 1. 配置管理

DatabaseConfig 使用 @dataclass(init=False) 禁用自动生成的 __init__ 方法，然后提供自定义 __init__ 方法来支持 **kwargs
传递额外引擎参数。这种设计允许在保持 dataclass 便利性的同时，实现灵活的参数处理：

```python
@dataclass(init=False)
class DatabaseConfig:
    url: str
    echo: bool
    pool_size: int
    max_overflow: int
    pool_timeout: int
    pool_recycle: int
    engine_kwargs: dict[str, Any]
    
    def __init__(self, url: str, echo: bool = False, pool_size: int = 5, 
                 max_overflow: int = 10, pool_timeout: int = 30, 
                 pool_recycle: int = 3600, **kwargs: Any) -> None:
        # 所有额外参数收集到 engine_kwargs
        self.engine_kwargs = kwargs

# 配置创建 - 支持额外参数
config = DatabaseConfig(
    "postgresql://...", 
    pool_size=10, 
    echo=True,
    isolation_level="READ_COMMITTED",  # 额外引擎参数
    connect_args={"sslmode": "require"}
)
```

### 2. 事件系统

提供统一的事件注册接口，支持所有 SQLAlchemy 事件类型：

```python
# 引擎级事件
@db.on("connect")
def on_connect(conn, record):
    print("数据库已连接")

@db.on("before_cursor_execute")
def log_sql(conn, cursor, stmt, params, ctx, many):
    print(f"执行 SQL: {stmt}")

# 会话级事件
@db.on("before_commit")
def before_commit(session):
    print("即将提交事务")

@db.on("after_flush")
def after_flush(session, flush_context):
    print("数据已刷新到数据库")
```

### 3. 观察者模式解耦

使用观察者模式实现 DatabaseManager 与 SessionContextManager 的解耦集成：

```python
class DatabaseObserver(Protocol):
    def on_database_added(self, name: str, database: Database, is_default: bool) -> None: ...
    def on_database_removed(self, name: str) -> None: ...
    def on_default_changed(self, old_default: str | None, new_default: str | None) -> None: ...

# SessionContextManager 作为观察者
_manager.add_observer(SessionContextManager())
```

### 4. 直接表操作

Database 类直接提供表操作方法，支持在实例级别进行表管理：

```python
# 直接在 Database 实例上操作
from sqlobjects.base import ObjectModel

await db.create_tables(ObjectModel.metadata)
await db.drop_tables(ObjectModel.metadata)

# 或通过 DatabaseManager
await create_tables(ObjectModel, "main")  # 在指定数据库实例上创建
await create_tables(ObjectModel)          # 在所有数据库实例上创建
```

## 模块架构

### 核心组件

- **DatabaseConfig**: 基于 @dataclass 的数据库配置类
- **Database**: 单个数据库连接，提供事件处理和表操作
- **DatabaseManager**: 多数据库管理器，使用观察者模式
- **DatabaseObserver**: 观察者协议，定义数据库事件接口

### 事件系统

Database 类的 `on()` 方法自动选择正确的事件目标：

```python
def on(self, event_name: str, target=None):
    # 自动选择事件目标
    if target is None:
        if event_name in ("before_commit", "after_commit", "before_rollback", "after_rollback"):
            target = Session  # 会话级事件
        else:
            target = self.engine.sync_engine  # 引擎级事件
    
    return event.listens_for(target, event_name)
```

#### 支持的事件类型

**引擎级事件**：

- `connect` - 数据库连接建立
- `before_cursor_execute` - SQL 执行前
- `after_cursor_execute` - SQL 执行后
- `begin` - 事务开始
- `commit` - 事务提交
- `rollback` - 事务回滚

**会话级事件**：

- `before_commit` - 事务提交前
- `after_commit` - 事务提交后
- `before_rollback` - 事务回滚前
- `after_rollback` - 事务回滚后
- `before_flush` - 数据刷新前
- `after_flush` - 数据刷新后

**连接池事件**：

- `checkout` - 连接检出
- `checkin` - 连接检入
- `invalidate` - 连接无效

### 与其他模块的集成

#### SessionContextManager 集成

通过观察者模式实现解耦集成：

```python
class SessionContextManager(DatabaseObserver):
    def on_database_added(self, name: str, database: Database, is_default: bool) -> None:
        self.set_session_factory(database.session_factory, name, is_default)
    
    def on_database_removed(self, name: str) -> None:
        if name in self._session_factories:
            del self._session_factories[name]
    
    def on_default_changed(self, old_default: str | None, new_default: str | None) -> None:
        self._default_db = new_default
```

#### 模块职责分离

- **database.py**: 负责数据库连接管理、事件处理、表操作、观察者模式实现
- **集成点**: 通过 DatabaseObserver 协议与 SessionContextManager 解耦集成

## API 参考

### DatabaseConfig

```python
@dataclass(init=False)
class DatabaseConfig:
    url: str                    # 数据库连接 URL
    echo: bool                  # 是否打印 SQL 语句
    pool_size: int              # 连接池大小
    max_overflow: int           # 连接池最大溢出数量
    pool_timeout: int           # 获取连接超时时间
    pool_recycle: int           # 连接回收时间
    engine_kwargs: dict[str, Any]  # 其他引擎参数
    
    def __init__(self, url: str, echo: bool = False, pool_size: int = 5,
                 max_overflow: int = 10, pool_timeout: int = 30,
                 pool_recycle: int = 3600, **kwargs: Any) -> None:
        # 禁用自动生成的 __init__，使用自定义实现支持 **kwargs 传递额外引擎参数
```

### Database 类

```python
# 事件注册
db.on(event_name: str, target=None)

# 表操作
await db.create_tables(metadata)
await db.drop_tables(metadata)

# 连接管理
await db.disconnect()
```

### DatabaseManager 类

```python
# 观察者管理
manager.add_observer(observer: DatabaseObserver)
manager.remove_observer(observer: DatabaseObserver)

# 数据库管理
await manager.add_database(name: str, config: DatabaseConfig, is_default: bool = False)
manager.get_database(db_name: str | None = None)

# 表操作
await manager.create_tables(base_class, db_name: str | None = None)
await manager.drop_tables(base_class, db_name: str | None = None)

# 连接生命周期
await manager.close(db_name: str | None = None, auto_default: bool = False)  # 关闭指定数据库或默认数据库
await manager.close_all()  # 关闭所有数据库
manager.set_default_db(db_name: str)
```

### 公共 API

```python
# 数据库初始化
await init_db(url: str, name: str | None = None, **kwargs)
await init_dbs(databases: Mapping, default: str | None = None)

# 表操作
await create_tables(base_class, db_name: str | None = None)
await drop_tables(base_class, db_name: str | None = None)

# 连接管理
await close_db(db_name: str | None = None, auto_default: bool = False)  # 关闭指定数据库或默认数据库
await close_dbs(db_names: list[str], auto_default: bool = False)  # 关闭多个指定数据库
await close_all_dbs()  # 关闭所有数据库
set_default_db(db_name: str)
```

## 使用指南

### 基础用法

```python
# 配置创建 - 支持额外参数
config = DatabaseConfig(
    "postgresql://...", 
    pool_size=10, 
    echo=True,
    isolation_level="READ_COMMITTED",  # 额外引擎参数
    pool_pre_ping=True
)

# 初始化数据库
db = await init_db("sqlite+aiosqlite:///test.db")

# 事件注册
@db.on("connect")
def on_connect(conn, record):
    print("数据库已连接")

# 表操作
from sqlobjects.base import ObjectModel

await db.create_tables(ObjectModel.metadata)
```

### 高级用法

#### 多数据库管理

```python
# 初始化多个数据库
main_db, analytics_db = await init_dbs({
    "main": {"url": "postgresql://..."},
    "analytics": {"url": "sqlite:///analytics.db"}
}, default="main")

# 为不同数据库注册事件
@main_db.on("connect")
def main_db_connect(conn, record):
    print("主数据库已连接")

@analytics_db.on("connect")
def analytics_db_connect(conn, record):
    print("分析数据库已连接")
```

#### 观察者模式扩展

```python
class DatabaseLogger(DatabaseObserver):
    def on_database_added(self, name: str, database: Database, is_default: bool) -> None:
        logger.info(f"数据库 {name} 已添加，是否默认: {is_default}")
    
    def on_database_removed(self, name: str) -> None:
        logger.info(f"数据库 {name} 已移除")
    
    def on_default_changed(self, old_default: str | None, new_default: str | None) -> None:
        logger.info(f"默认数据库从 {old_default} 变更为 {new_default}")

# 注册自定义观察者
from sqlobjects.database import _manager
_manager.add_observer(DatabaseLogger())
```

#### 高级事件处理

```python
# SQL 执行监控
@db.on("before_cursor_execute")
def log_sql(conn, cursor, statement, parameters, context, executemany):
    print(f"执行 SQL: {statement}")

@db.on("after_cursor_execute")
def log_sql_result(conn, cursor, statement, parameters, context, executemany):
    print(f"SQL 执行完成，影响行数: {cursor.rowcount}")

# 事务管理
@db.on("begin")
def on_transaction_begin(conn):
    print("事务开始")

@db.on("before_commit")
def before_commit(session):
    print("即将提交事务")

@db.on("after_commit")
def after_commit(session):
    print("事务已提交")

# 连接池监控
@db.on("checkout")
def on_connection_checkout(dbapi_conn, conn_record, conn_proxy):
    print(f"连接检出: {id(dbapi_conn)}")

@db.on("checkin")
def on_connection_checkin(dbapi_conn, conn_record):
    print(f"连接检入: {id(dbapi_conn)}")
```

#### 数据库连接管理

```python
# 关闭默认数据库
await close_db()  # 关闭默认数据库

# 关闭指定数据库
await close_db("analytics")  # 关闭 analytics 数据库

# 自动故障转移：关闭故障数据库并自动选择新的默认数据库
await close_db("main", auto_default=True)

# 关闭多个数据库
await close_dbs(["analytics", "logs"])

# 关闭所有数据库
await close_all_dbs()
```

#### 配置高级引擎参数

```python
# 使用 engine_kwargs 传递高级参数
config = DatabaseConfig(
    url="postgresql://...",
    pool_size=20,
    echo=True,
    engine_kwargs={
        "connect_args": {"sslmode": "require"},
        "isolation_level": "READ_COMMITTED",
        "pool_pre_ping": True,
        "pool_reset_on_return": "commit"
    }
)

db = await init_db(config.url, config=config)
```
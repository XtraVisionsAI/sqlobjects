# SQLObjects 核心架构设计文档

## 概述

SQLObjects 核心架构基于 SQLAlchemy Core 构建，采用组合模式设计，提供全局数据库管理、任务级会话上下文和完整的模型基类。通过事件系统实现数据库管理器与会话管理器的解耦，支持多数据库环境和异步操作。

## 核心功能

### 1. 全局数据库管理

DatabaseManager 作为全局单例管理多数据库连接，Database 类提供事件处理能力：

```python
# 数据库初始化 - 返回 Database 实例
db = await init_db("postgresql://user:pass@localhost/db", name="main")
main_db, analytics_db = await init_dbs({
    "main": {"url": "postgresql://...", "pool_size": 20},
    "analytics": {"url": "sqlite:///analytics.db"}
}, default="main")

# 事件注册 - 通过 Database 实例
@db.on("connect")
def on_connect(conn, record):
    print("Database connected")

# DatabaseManager 管理所有数据库实例
# 支持默认数据库和命名数据库访问
```

### 2. 任务级会话上下文

AsyncSession 类提供智能连接管理，SessionContextManager 基于 asyncio.current_task 提供任务级会话：

```python
# 自动会话管理 - 使用默认数据库
user = await User.objects.get(User.id == 1)

# 显式事务控制 - 使用上下文管理器（推荐）
from sqlobjects.session import ctx_session, ctx_sessions

# 单数据库会话
async with ctx_session() as session:
    user = await User.objects.using(session).create(name="John")

# 指定数据库会话
async with ctx_session("analytics") as session:
    data = await Log.objects.using(session).all()

# 多数据库会话
async with ctx_sessions("main", "analytics") as sessions:
    user = await User.objects.using(sessions["main"]).create(name="Alice")
    await Log.objects.using(sessions["analytics"]).create(message="User created")
```

### 3. 组合模式模型基类

ObjectModel 通过 ModelProcessor 元类和 ModelMixin 的组合实现，集成所有功能组件：

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn

class User(ObjectModel):  # 继承 ModelMixin + ModelProcessor 元类
    name: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100, unique=True)
  
    class Config:
        table_name = "users"
        ordering = ["-created_at"]

# ObjectModel 内置功能：
# - SignalMixin: 信号系统
# - HistoryTrackingMixin: 历史跟踪
# - FieldCacheMixin: 字段缓存和代理
# - ValidationMixin: 验证系统
# - DeferredLoadingMixin: 延迟加载
# - SessionMixin: 会话管理

# 实例操作 - 智能检测和信号发射
user = User(name="John", email="john@example.com")
await user.save()  # 自动检测 CREATE，发射 before_save/before_create/after_save/after_create

user.email = "john.new@example.com"
await user.save()  # 自动检测 UPDATE，仅更新脏字段
```

### 4. ModelProcessor 元类系统

ModelProcessor 元类自动处理模型定义，生成 SQLAlchemy 表并设置 objects 管理器：

```python
# 自动表名生成和 objects 管理器设置
class UserProfile(ObjectModel):  # → 表名: "user_profiles"
    pass
# 自动设置: UserProfile.objects = ObjectsDescriptor(UserProfile)

# 配置处理和字段缓存
class Product(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    price: Column[Decimal] = NumericColumn(precision=10, scale=2)
  
    class Config:
        indexes = [index("idx_name", "name")]
        constraints = [constraint("price > 0")]

# ModelProcessor 自动处理：
# - 字段定义转换为 SQLAlchemy Column
# - 生成 __table__ 属性
# - 设置 objects 管理器
# - 初始化字段缓存
# - 处理关系定义
```

## 模块架构

### 核心组件

**全局管理层**

- **DatabaseManager**: 全局数据库管理器，管理多个数据库实例
- **Database**: 数据库实例，提供事件处理和连接管理
- **AsyncSession**: 智能会话类，提供连接管理和事务控制
- **SessionContextManager**: 全局会话上下文管理器，基于 asyncio.current_task 的任务级会话

**模型层**

- **ObjectModel**: 组合模式模型基类，集成 ModelMixin + ModelProcessor 元类
- **ModelProcessor**: 元类处理器，自动生成 SQLAlchemy 表和 objects 管理器
- **ModelMixin**: 通过继承链组合所有功能 Mixins：
  - FieldCacheMixin（字段缓存和属性访问优化）
  - DataConversionMixin（数据转换功能）
  - DeferredLoadingMixin（延迟加载功能）
  - ValidationMixin（验证逻辑）
  - PrimaryKeyMixin（主键操作）
  - SessionMixin（会话管理）
  - BaseMixin（基础功能和状态管理）

**功能 Mixin 层**

- **FieldCacheMixin**: 字段缓存和智能属性访问，集成代理系统
- **SignalMixin**: 信号系统，通过单独继承内置到 ObjectModel
- **HistoryTrackingMixin**: 历史跟踪和脏字段检测
- **ValidationMixin**: 验证系统集成
- **DeferredLoadingMixin**: 延迟加载功能
- **SessionMixin**: 会话管理和 using() 方法

**状态管理层**

- **StateManager**: 统一实例状态管理，支持脏字段、延迟字段、代理缓存
- **DeferredFieldProxy**: 延迟字段代理，支持懒加载和缓存
- **RelationFieldProxy**: 关系字段代理，支持关系懒加载

### 设计理念

**组合模式**: 使用 Mixin 组合而非复杂继承，提高可维护性
**全局管理**: 全局 DatabaseManager 和 SessionContextManager 实例，简化使用
**事件驱动**: Database 类通过事件系统提供扩展点
**智能检测**: 自动检测 CREATE/UPDATE 操作、脏字段跟踪、延迟加载
**元类驱动**: ModelProcessor 元类自动处理模型定义和表生成
**统一状态**: StateManager 统一实例状态管理，支持多种状态类型

### 与其他模块的集成

**数据操作模块**: 通过 SessionContextManager 获取会话
**字段系统模块**: 通过 ModelProcessor 处理字段定义
**关系处理模块**: 通过 ObjectModel 提供关系支持

## API 参考

### 数据库管理

```python
# 数据库初始化
await init_db(url, name=None, **kwargs)
await init_dbs(databases, default=None)

# 表操作
await create_tables(base_class, db_name=None)
await drop_tables(base_class, db_name=None)

# 连接管理
await close_db(db_name=None)
await close_all_dbs()
```

### 会话管理

```python
# 上下文管理器
async with ctx_session(db_name=None) as session:
    pass

async with ctx_sessions(*db_names) as sessions:
    pass

# 推荐使用上下文管理器而非直接获取会话
# SessionContextManager.get_session() 主要用于内部实现
```

### 模型定义

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn

class Model(ObjectModel):
    # 字段定义
    field: Column[str] = StringColumn(...)
  
    # 配置类
    class Config:
        table_name = "custom_name"
        ordering = ["-created_at"]
        indexes = [...]
        constraints = [...]
```

## 使用指南

### 基础使用

```python
# 1. 数据库初始化
await init_db("sqlite+aiosqlite:///app.db")

# 2. 模型定义
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn

class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100, unique=True)

# 3. 创建表
await create_tables(ObjectModel)

# 4. 基本操作
user = User(name="John", email="john@example.com")
await user.save()
```

### 高级使用

```python
# 多数据库配置
await init_dbs({
    "main": {
        "url": "postgresql://localhost/main",
        "pool_size": 20
    },
    "analytics": {
        "url": "sqlite:///analytics.db"
    }
}, default="main")

# 复杂模型配置
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, NumericColumn
from decimal import Decimal

class Product(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    price: Column[Decimal] = NumericColumn(precision=10, scale=2)
  
    class Config:
        table_name = "products"
        ordering = ["name"]
        indexes = [
            index("idx_name", "name"),
            index("idx_price", "price", unique=True)
        ]
        constraints = [
            constraint("price > 0", "ck_positive_price")
        ]

# 事务管理
async with ctx_session() as session:
    # 所有操作在同一事务中
    user = await User.objects.using(session).create(name="Alice")
    product = await Product.objects.using(session).create(
        name="Widget", price=Decimal("19.99")
    )
```

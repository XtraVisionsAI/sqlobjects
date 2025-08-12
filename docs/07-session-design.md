# SQLObjects Session 设计说明文档

## 概述

SQLObjects Session 模块提供了基于 SQLAlchemy `async_scoped_session`
的多数据库会话管理系统。该模块通过分层会话管理策略，实现了自动会话创建、显式事务控制和多数据库支持，为开发者提供零维护成本的会话管理体验。

核心设计理念是通过 `asyncio.current_task` 实现自动会话隔离，同时基于 ContextVar 机制用于显式事务控制，确保在各种并发场景下的会话安全性和事务一致性。

## 核心特性

### 1. 分层会话管理

提供两层会话管理机制，满足不同使用场景的需求：

```python
# 自动会话管理 - 零配置使用
user = await User.objects.get(User.username == "john")  # 自动创建和管理会话

# 显式会话管理 - 事务控制
async with ctx_session() as session:
    await User.objects.using(session).create(username="jane")  # 显式事务边界

# 模型实例的会话绑定
user = User(username="alice")
await user.using(session).save()  # 使用 ModelProxy 绑定会话
```

### 2. 统一事务和独立事务支持

支持三种事务模式，适应不同的业务场景：

```python
# 模式1：统一事务 - 子任务通过 ContextVar 继承父任务会话
async with ctx_session() as session:
    tasks = [asyncio.create_task(process_batch(batch)) for batch in batches]
    await asyncio.gather(*tasks)  # 任意失败则全部回滚

# 模式2：独立事务 - 使用独立上下文隔离
tasks = [
    asyncio.create_task(process_batch_isolated(batch), context=contextvars.copy_context())
    for batch in batches
]
await asyncio.gather(*tasks, return_exceptions=True)  # 失败不影响其他任务

# 模式3：显式传递会话 - 不依赖 ContextVar，完全显式控制
async with ctx_session() as session:
    tasks = [asyncio.create_task(process_batch_explicit(batch, session)) for batch in batches]
    await asyncio.gather(*tasks)  # 显式共享同一会话
```

### 3. 多数据库环境支持

原生支持多数据库环境，每个数据库独立管理会话工厂和作用域：

```python
# 设置多个数据库
SessionContextManager.set_session_factory(main_factory, "main", is_default=True)
SessionContextManager.set_session_factory(analytics_factory, "analytics")

# 跨数据库事务管理
async with ctx_sessions("main", "analytics") as sessions:
    await User.objects.using(sessions["main"]).create(name="John")
    await Event.objects.using(sessions["analytics"]).create(action="signup")

# 模型实例的多数据库支持
user = User(name="Bob")
await user.using(sessions["main"]).save()
event = Event(action="signup", user_id=user.id)
await event.using(sessions["analytics"]).save()
```

## 模块架构

### 核心组件

- **SessionContextManager**: 会话管理器，负责会话工厂注册和会话获取
- **async_scoped_session**: SQLAlchemy 原生的作用域会话，基于 `asyncio.current_task` 自动隔离
- **ContextVar 机制**: 用于显式会话管理和跨任务会话共享
- **ctx_session/ctx_sessions**: 异步上下文管理器，提供事务边界控制

### 会话获取优先级系统

会话获取遵循明确的优先级顺序，确保行为的可预测性：

```python
def get_session(db_name: str | None = None) -> AsyncSession:
    # 第1优先级：显式设置的会话（ctx_session 设置）
    if name in _explicit_sessions.get({}):
        return _explicit_sessions.get({})[name]
    
    # 第2优先级：自动会话（基于 current_task 的 scoped_session）
    return _scoped_sessions[name]()
```

### 与其他模块的集成

#### 与 ObjectsManager 和 ModelProxy 的集成

ObjectsManager 和 ModelProxy 都通过 `using()` 方法支持会话指定：

```python
# ObjectsManager 的会话管理
class ObjectsManager:
    def using(self, db_or_session: str | AsyncSession) -> "ObjectsManager[T]":
        """指定数据库名或会话对象"""
        return ObjectsManager(self._model, db_or_session)
    
    @property
    def _session(self):
        if self._db_or_session is None:
            return SessionContextManager.get_session()
        elif isinstance(self._db_or_session, str):
            return SessionContextManager.get_session(self._db_or_session)
        else:
            return self._db_or_session

# ModelProxy 的会话管理
class ModelProxy(ModelMixin):
    def __init__(self, instance, db_or_session: str | AsyncSession):
        self._instance = instance
        self._db_or_session = db_or_session
    
    def _get_session(self) -> AsyncSession:
        if isinstance(self._db_or_session, str):
            return SessionContextManager.get_session(self._db_or_session)
        return self._db_or_session

# 模型实例的 using() 方法
class ModelMixin:
    def using(self, db_or_session: str | AsyncSession) -> "ModelProxy":
        """返回绑定到特定数据库/会话的代理对象"""
        return ModelProxy(self._get_instance(), db_or_session)
```

#### 模块职责分离

- **session.py**: 负责会话生命周期管理、多数据库支持、事务控制
- **objects.py**: 负责 ORM 操作，通过 session 模块获取会话
- **database.py**: 负责数据库连接和引擎管理
- **集成点**: 通过 SessionContextManager 实现模块间的会话共享

## API 参考

### SessionContextManager 类

```python
# 会话工厂管理
SessionContextManager.set_session_factory(factory, db_name="default", is_default=False)
SessionContextManager.set_default(db_name)

# 会话获取和设置
session = SessionContextManager.get_session(db_name=None)
SessionContextManager.set_session(session, db_name=None)
SessionContextManager.clear_session(db_name=None)
```

### 上下文管理器

```python
# 单数据库会话管理
async with ctx_session(db_name=None) as session:
    # 数据库操作

# 多数据库会话管理
async with ctx_sessions(*db_names) as sessions:
    # 跨数据库操作
```

## 使用指南

### 基础用法

#### 自动会话管理

最简单的使用方式，无需显式管理会话：

```python
# 设置数据库
SessionContextManager.set_session_factory(session_factory, "main", is_default=True)

# 直接使用，会话自动管理
user = await User.objects.get(User.username == "john")
users = await User.objects.filter(User.is_active == True).all()
```

#### 显式会话管理

需要事务控制时使用显式会话：

```python
# 单个操作的事务控制
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="jane")
    # 使用 ModelProxy 绑定会话
    post = Post(title="First Post", author_id=user.id)
    await post.using(session).save()
    # 自动提交或回滚

# 多数据库事务
async with ctx_sessions("main", "logs") as sessions:
    user = await User.objects.using(sessions["main"]).create(username="bob")
    # 使用 ModelProxy 进行跨数据库操作
    log = Log(message="User created", user_id=user.id)
    await log.using(sessions["logs"]).save()
```

### 高级用法

#### 批量任务的事务管理

根据业务需求选择合适的事务模式：

```python
# 模式1：统一事务 - ContextVar 继承（推荐）
async def bulk_insert_unified_transaction():
    async with ctx_session() as session:
        tasks = []
        for batch in batches:
            # 子任务继承父任务的会话
            task = asyncio.create_task(process_batch(batch))
            tasks.append(task)
        await asyncio.gather(*tasks)  # 共享事务

# 模式2：独立事务 - 独立上下文
async def bulk_insert_isolated_transactions():
    tasks = []
    for batch in batches:
        # 使用独立上下文，每个任务创建独立会话
        ctx = contextvars.copy_context()
        task = asyncio.create_task(process_batch_isolated(batch), context=ctx)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 处理部分成功的结果

# 模式3：显式传递会话 - 完全显式控制
async def bulk_insert_explicit_session():
    async with ctx_session() as session:
        tasks = []
        for batch in batches:
            # 显式传递会话，不依赖 ContextVar
            task = asyncio.create_task(process_batch_explicit(batch, session))
            tasks.append(task)
        await asyncio.gather(*tasks)  # 显式共享会话

# 对应的处理函数
async def process_batch(batch_data):
    """模式1：使用 ContextVar 继承的会话"""
    for item in batch_data:
        await User.objects.create(**item)  # 自动使用继承的 session

async def process_batch_isolated(batch_data):
    """模式2：创建独立会话"""
    async with ctx_session() as session:
        for item in batch_data:
            await User.objects.using(session).create(**item)

async def process_batch_explicit(batch_data, session):
    """模式3：使用显式传递的会话"""
    for item in batch_data:
        await User.objects.using(session).create(**item)  # 使用显式传递的 session
```

#### 三种模式的对比

| 模式                | 优势           | 适用场景        | 注意事项             |
|-------------------|--------------|-------------|------------------|
| **ContextVar 继承** | 代码简洁，自动传递    | 统一事务，代码简化   | 依赖 ContextVar 机制 |
| **独立上下文**         | 完全隔离，失败不影响其他 | 独立事务，容错处理   | 需要手动管理上下文        |
| **显式传递**          | 明确可控，不依赖隐式机制 | 复杂事务逻辑，调试友好 | 代码稍显冗长           |

#### FastAPI 集成

在 FastAPI 应用中的典型使用模式：

```python
from fastapi import FastAPI

app = FastAPI()

@app.on_event("startup")
async def startup():
    # 初始化数据库会话工厂
    SessionContextManager.set_session_factory(main_factory, "main", is_default=True)
    SessionContextManager.set_session_factory(analytics_factory, "analytics")

@app.post("/users/")
async def create_user(user_data: UserCreate):
    # 自动会话管理，同一请求内的多个操作共享会话
    user = await User.objects.create(**user_data.dict())
    await Event.objects.create(user_id=user.id, action="user_created")
    return user

@app.post("/users/batch/")
async def create_users_batch(users_data: list[UserCreate]):
    # 显式事务控制，确保批量操作的原子性
    async with ctx_session() as session:
        created_users = []
        for user_data in users_data:
            user = await User.objects.using(session).create(**user_data.dict())
            created_users.append(user)
        return created_users
```

#### 错误处理和恢复

```python
async def robust_batch_operation():
    """健壮的批量操作，支持部分失败恢复"""
    successful_batches = []
    failed_batches = []
    
    tasks = []
    for i, batch in enumerate(batches):
        ctx = contextvars.copy_context()
        task = asyncio.create_task(
            process_batch_with_retry(batch, batch_id=i), 
            context=ctx
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            failed_batches.append((i, result))
        else:
            successful_batches.append(i)
    
    print(f"成功批次: {len(successful_batches)}, 失败批次: {len(failed_batches)}")
    
    # 可选：重试失败的批次
    if failed_batches:
        await retry_failed_batches(failed_batches)

async def process_batch_with_retry(batch_data, batch_id, max_retries=3):
    """带重试机制的批次处理"""
    for attempt in range(max_retries):
        try:
            async with ctx_session() as session:
                for item in batch_data:
                    await User.objects.using(session).create(**item)
                return f"Batch {batch_id} completed successfully"
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # 指数退避

# 显式传递会话的错误处理示例
async def robust_batch_operation_explicit():
    """使用显式会话传递的健壮批量操作"""
    async with ctx_session() as main_session:
        successful_batches = []
        failed_batches = []
        
        # 为每个批次创建独立会话，但可以选择性地共享主会话
        tasks = []
        for i, batch in enumerate(batches):
            if batch.get('requires_isolation'):
                # 需要隔离的批次使用独立会话
                task = asyncio.create_task(process_batch_isolated_explicit(batch, i))
            else:
                # 普通批次共享主会话
                task = asyncio.create_task(process_batch_explicit(batch, main_session))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_batches.append((i, result))
            else:
                successful_batches.append(i)
        
        print(f"成功批次: {len(successful_batches)}, 失败批次: {len(failed_batches)}")

async def process_batch_isolated_explicit(batch_data, batch_id):
    """使用独立会话的批次处理"""
    async with ctx_session() as session:
        for item in batch_data:
            await User.objects.using(session).create(**item)
        return f"Isolated batch {batch_id} completed"
```

#### 选择合适的事务模式

根据具体业务场景选择最适合的事务模式：

```python
# 场景1：需要原子性的批量操作（推荐使用 ContextVar 继承）
async def atomic_bulk_operation():
    async with ctx_session() as session:
        # 所有操作在同一事务中，任意失败则全部回滚
        tasks = [asyncio.create_task(process_batch(batch)) for batch in batches]
        await asyncio.gather(*tasks)

# 场景2：需要容错的批量操作（推荐使用独立上下文）
async def fault_tolerant_bulk_operation():
    tasks = [
        asyncio.create_task(process_batch_isolated(batch), context=contextvars.copy_context())
        for batch in batches
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 处理部分成功的结果

# 场景3：复杂的混合事务逻辑（推荐使用显式传递）
async def complex_mixed_operation():
    async with ctx_session() as main_session:
        # 主要操作使用共享会话
        await User.objects.using(main_session).create(name="admin")
        
        # 某些操作需要独立事务
        async with ctx_session() as isolated_session:
            await Log.objects.using(isolated_session).create(message="Admin created")
        
        # 批量操作显式传递会话
        tasks = [
            asyncio.create_task(process_batch_explicit(batch, main_session))
            for batch in batches
        ]
        await asyncio.gather(*tasks)
```

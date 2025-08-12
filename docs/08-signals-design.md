# SQLObjects 信号系统设计文档

## 概述

SQLObjects 信号系统为数据库操作提供了完整的生命周期钩子机制，支持在数据库操作前后执行自定义逻辑。系统采用智能操作检测和双信号发射机制，能够精确控制不同类型的数据库操作。

## 核心特性

### 1. 智能 SAVE 操作

SAVE 操作具备自动检测能力，能够根据实例状态智能判断是创建还是更新操作：

```python
# 新实例 - 自动识别为 CREATE
user = User(name="john")  # id=None
await user.save()
# 触发：before_save → before_create → 数据库操作 → after_save → after_create

# 已存在实例 - 自动识别为 UPDATE  
user = User(id=123, name="john")
await user.save()
# 触发：before_save → before_update → 数据库操作 → after_save → after_update
```

### 2. 双信号发射机制

SAVE 操作会按顺序触发两个层级的信号：
- **通用信号**：`before_save` / `after_save`（总是触发）
- **具体信号**：`before_create/update` / `after_create/update`（根据检测结果触发）

### 3. 批量操作信号规范

使用 `bulk_` 前缀明确区分批量操作和单实例操作：

```python
class User(ObjectModel, SignalMixin):
    # 实例级信号
    async def before_save(self, context):
        print("单实例保存")
    
    # 批量操作信号
    @classmethod
    async def before_bulk_save(cls, context):
        print(f"批量保存 {context.affected_count} 条记录")
```

### 4. 精确操作控制

支持明确指定操作类型，提供精确的信号控制：

```python
@emit_signals(Operation.CREATE)  # 明确创建操作
async def create(cls, **kwargs):
    pass

@emit_signals(Operation.SAVE)    # 智能保存操作
async def save(self):
    pass
```

## 模块架构

### 核心组件

- **Operation 枚举**：定义数据库操作类型（CREATE、UPDATE、DELETE、SAVE）
- **SignalContext 数据类**：封装信号上下文信息，包含操作类型、会话、实例等
- **SignalMixin 混入类**：提供信号发射能力，支持实例级和批量操作信号
- **emit_signals 装饰器**：自动化信号发射，支持智能操作检测

### 操作检测系统

```python
def _determine_save_operation(self_or_cls) -> Operation:
    """智能检测 SAVE 操作的具体类型"""
    if hasattr(self_or_cls, "__table__"):  # 实例方法
        # 检查实例主键状态
        primary_keys = [col.name for col in self_or_cls.__table__.primary_key.columns]
        if any(getattr(self_or_cls, pk, None) is not None for pk in primary_keys):
            return Operation.UPDATE  # 有主键值 → 更新
        else:
            return Operation.CREATE  # 无主键值 → 创建
    else:
        return Operation.CREATE  # 类方法默认为创建
```

### 信号发射架构

```python
async def _emit_signal_handlers(target, timing: str, context: SignalContext):
    """统一的信号发射逻辑"""
    is_bulk = context.is_bulk
    bulk_prefix = "bulk_" if is_bulk else ""
    
    if context.operation == Operation.SAVE and context.actual_operation:
        # SAVE 操作：双信号发射
        # 1. 通用 SAVE 信号
        save_handler = getattr(target, f"{timing}_{bulk_prefix}save", None)
        if save_handler:
            await save_handler(context)
        
        # 2. 具体操作信号
        specific_handler = getattr(target, f"{timing}_{bulk_prefix}{context.actual_operation.value}", None)
        if specific_handler:
            await specific_handler(context)
    else:
        # 其他操作：单一信号
        handler = getattr(target, f"{timing}_{bulk_prefix}{context.operation.value}", None)
        if handler:
            await handler(context)
```

## API 参考

### Operation 枚举

```python
class Operation(Enum):
    CREATE = "create"  # 创建操作
    UPDATE = "update"  # 更新操作
    DELETE = "delete"  # 删除操作
    SAVE = "save"      # 智能保存操作
```

### SignalContext 上下文

```python
@dataclass
class SignalContext:
    operation: Operation                    # 操作类型
    session: AsyncSession                   # 数据库会话
    model_class: Any                        # 模型类
    instance: Any | None = None             # 实例对象（单实例操作）
    affected_count: int | None = None       # 影响行数（批量操作）
    update_data: dict[str, Any] | None = None  # 更新数据
    actual_operation: Operation | None = None  # SAVE 操作的实际类型
```

### 信号处理器方法

#### 实例级信号（单记录操作）
- `before_create(context)` / `after_create(context)`
- `before_update(context)` / `after_update(context)`
- `before_delete(context)` / `after_delete(context)`
- `before_save(context)` / `after_save(context)`

#### 批量操作信号（多记录操作）
- `before_bulk_create(context)` / `after_bulk_create(context)`
- `before_bulk_update(context)` / `after_bulk_update(context)`
- `before_bulk_delete(context)` / `after_bulk_delete(context)`
- `before_bulk_save(context)` / `after_bulk_save(context)`

### emit_signals 装饰器

```python
@emit_signals(Operation.SAVE)  # 智能检测 + 双信号
async def save(self):
    pass

@emit_signals(Operation.UPDATE, is_bulk=True)  # 批量更新
async def bulk_update(cls, mappings):
    pass
```

## 使用指南

### 基础用法

```python
class User(ObjectModel, SignalMixin):
    name: Column[str] = str_column(length=50)
    email: Column[str] = str_column(length=100)
    
    # 通用保存处理
    async def before_save(self, context):
        print("保存操作开始")
        self.updated_at = datetime.now()
    
    # 具体操作处理
    async def before_create(self, context):
        print("创建新用户")
        self.created_at = datetime.now()
    
    async def before_update(self, context):
        print("更新用户信息")
    
    # 批量操作处理
    @classmethod
    async def before_bulk_update(cls, context):
        print(f"批量更新 {context.affected_count} 个用户")

# 使用装饰器
@emit_signals(Operation.SAVE)
async def save(self):
    # 实现保存逻辑
    pass
```

### 高级用法

```python
class User(ObjectModel, SignalMixin):
    async def before_save(self, context):
        # 访问上下文信息
        if context.actual_operation == Operation.CREATE:
            print("这是一个创建操作")
        elif context.actual_operation == Operation.UPDATE:
            print("这是一个更新操作")
        
        # 访问会话信息
        session = context.session
        
        # 访问实例信息
        if context.instance:
            print(f"操作实例：{context.instance}")
    
    @classmethod
    async def before_bulk_save(cls, context):
        # 批量操作上下文
        print(f"影响行数：{context.affected_count}")
        print(f"更新数据：{context.update_data}")
        
        # 执行批量操作前的准备工作
        if context.affected_count > 1000:
            print("大批量操作，启用优化模式")

# 不同操作类型的装饰器使用
@emit_signals(Operation.CREATE)
async def create_user(cls, **kwargs):
    # 只触发 CREATE 相关信号
    pass

@emit_signals(Operation.SAVE)
async def save_user(self):
    # 智能检测 + 双信号发射
    pass

@emit_signals(Operation.UPDATE, is_bulk=True)
async def bulk_update_users(cls, mappings):
    # 只触发批量 UPDATE 信号
    pass
```

### 信号处理最佳实践

```python
class User(ObjectModel, SignalMixin):
    async def before_save(self, context):
        # 通用逻辑：所有保存操作都需要的处理
        self.validate_data()
        self.normalize_fields()
    
    async def before_create(self, context):
        # 创建特定逻辑：只在创建时需要的处理
        self.set_default_values()
        self.generate_unique_id()
    
    async def before_update(self, context):
        # 更新特定逻辑：只在更新时需要的处理
        self.track_changes()
        self.update_version()
    
    async def after_save(self, context):
        # 保存后通用处理
        await self.clear_cache()
    
    async def after_create(self, context):
        # 创建后特定处理
        await self.send_welcome_email()
    
    async def after_update(self, context):
        # 更新后特定处理
        await self.notify_changes()
```
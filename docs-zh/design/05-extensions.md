# SQLObjects 扩展系统设计文档

## 概述

SQLObjects 扩展系统通过与 ObjectModel 的内置集成提供增强功能，包括信号系统、智能操作检测、性能优化和代理系统。通过 Mixin 组合模式和统一状态管理，为核心功能提供无缝集成能力。

## 核心功能

### 1. 内置信号系统

ObjectModel 默认包含 SignalMixin，通过方法名称约定发现提供完整的模型生命周期信号：

```python
from sqlobjects.model import ObjectModel  # SignalMixin 已内置
from sqlobjects.fields import Column, StringColumn
from sqlobjects.signals import SignalContext, Operation
from datetime import datetime

class User(ObjectModel):  # 自动具有信号功能
    name: Column[str] = StringColumn(length=50)
  
    # 实例级信号 - 通过方法名称约定发现
    async def before_save(self, context: SignalContext):
        # context.actual_operation 显示检测到的操作（CREATE 或 UPDATE）
        self.updated_at = datetime.now()
  
    async def before_create(self, context: SignalContext):
        self.created_at = datetime.now()
  
    async def after_create(self, context: SignalContext):
        await self.send_welcome_email()
  
    # 类级批量信号
    @classmethod
    async def before_bulk_create(cls, context: SignalContext):
        print(f"Creating {context.affected_count} users")

# 信号处理器发现机制：
# - 使用 getattr() 按名称查找方法（before_save、after_create 等）
# - @emit_signals 装饰器调用 _determine_save_operation() 检测 CREATE/UPDATE
# - 为 SAVE 操作发射双重信号（SAVE 和 CREATE/UPDATE）

user = User(name="John")  # 无主键值
await user.save()  # _determine_save_operation() 返回 CREATE
# 发射：before_save → before_create → after_save → after_create

user.name = "John Updated"
await user.save()  # _determine_save_operation() 返回 UPDATE
# 发射：before_save → before_update → after_save → after_update
```

### 2. 异常处理

分层异常系统提供详细的错误信息和统一的错误处理：

```python
# 异常层次结构
try:
    user = await User.objects.get(User.id == 999)
except DoesNotExist:
    print("User does not exist")
except ValidationError as e:
    if e.is_multiple:
        for field, errors in e.field_errors.items():
            print(f"{field}: {', '.join(errors)}")
except SQLObjectsError:
    print("SQLObjects operation error")

# 验证错误收集
collector = ValidationErrorCollector()
collector.add_error("email", "Invalid email format")
collector.add_error("age", "Age must be positive")
collector.raise_if_errors()
```

### 3. 集成性能优化

通过批量操作优化和 FieldCacheMixin 代理系统提升性能：

```python
# QueryCache FIFO 缓存 - 自动管理缓存大小
users = await User.objects.filter(User.is_active == True).all()  # 缓存未命中
users = await User.objects.filter(User.is_active == True).all()  # 缓存命中

# 缓存统计和控制
stats = QuerySet.get_cache_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}")
QuerySet.clear_query_cache()

# 批量操作优化 - 使用 bindparam 和批处理
await User.objects.bulk_create(users_data)  # 自动批处理
affected = await User.objects.bulk_update(update_data, batch_size=500)

# FieldCacheMixin 代理系统 - 自动处理延迟字段
user = await User.objects.only("name").first()  # bio 字段延迟
# user.bio 返回 DeferredFieldProxy
# await user.bio.fetch() 实际加载数据

# 关系代理 - RelationFieldProxy
# user.posts 返回 RelationFieldProxy
# await user.posts.fetch() 加载关系数据
```

### 4. 工具函数

简化常见操作的实用工具函数和辅助类：

```python
# 命名转换工具
from sqlobjects.utils.naming import to_snake_case, to_camel_case
from sqlobjects.utils.pattern import pluralize, singularize

snake_name = to_snake_case("UserProfile")  # "user_profile"
camel_name = to_camel_case("user_profile")  # "UserProfile"
plural = pluralize("user")                  # "users"

# 调试工具
field_stats = User._get_field_cache()
print(f"Field categories: {list(field_stats.keys())}")
```

## 模块架构

### 核心组件

**模型集成层**

- **ObjectModel**: 完整的模型基类，组合所有 Mixins，内置扩展功能
- **ModelMixin**: 组合 FieldCacheMixin + SignalMixin

**信号系统层**

- **SignalMixin**: 信号 Mixin 类，内置到 ObjectModel
- **@emit_signals**: 信号装饰器，自动处理信号发射和操作检测
- **_determine_save_operation()**: 检查 _has_primary_key_values() 以检测 CREATE vs UPDATE 的函数
- **_emit_signal()**: 使用 getattr() 按方法名称发现处理器的函数
- **Operation**: 操作类型枚举，支持 SAVE/CREATE/UPDATE/DELETE
- **SignalContext**: 包含 operation、session、instance 和 actual_operation 的数据类

**代理系统层**

- **DeferredObject**: 延迟字段代理，支持延迟加载和缓存
- **RelatedObject**: 单个关系代理（ForeignKey、OneToOne）
- **RelatedCollection**: 集合关系代理（OneToMany、ManyToMany）
- **FieldCacheMixin**: 将字段缓存和代理系统集成到 __getattribute__

**状态管理层**

- **StateManager**: 统一实例状态管理，支持多种状态类型
- **HistoryTrackingMixin**: 历史跟踪和脏字段检测

**性能工具层**

- **FieldCache**: 字段元数据缓存机制，集成到模型类
- **ValidationError**: 分层异常系统，支持单字段和多字段错误

### 设计理念

**内置集成**: 所有扩展功能内置到 ObjectModel，无需显式配置
**Mixin 组合**: 通过 Mixin 组合避免复杂继承，提高可维护性
**统一状态**: StateManager 统一实例状态管理，支持多种状态类型
**智能代理**: 通过 __getattribute__ 集成代理系统，提供透明的延迟加载
**方法名称发现**: 信号处理器通过方法名称约定使用 getattr() 发现
**操作检测**: _determine_save_operation() 检查 _has_primary_key_values() 以检测 CREATE/UPDATE
**双重信号发射**: SAVE 操作发射 SAVE 和特定的 CREATE/UPDATE 信号
**内置性能**: 字段缓存、批量操作和代理系统内置到核心组件

### 与其他模块的集成

**核心架构模块**: 将信号系统集成到模型生命周期
**数据操作模块**: 提供批量操作优化和字段缓存
**字段系统模块**: 集成验证错误处理和异常系统

## API 参考

### 信号系统

```python
# 信号功能（内置到 ObjectModel）
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext, Operation, emit_signals

class Model(ObjectModel):
    # 实例级信号 - 通过方法名称发现
    async def before_save(self, context: SignalContext): pass
    async def after_save(self, context: SignalContext): pass
    async def before_create(self, context: SignalContext): pass
    async def after_create(self, context: SignalContext): pass
    async def before_update(self, context: SignalContext): pass
    async def after_update(self, context: SignalContext): pass
    async def before_delete(self, context: SignalContext): pass
    async def after_delete(self, context: SignalContext): pass
  
    # 批量操作信号
    @classmethod
    async def before_bulk_create(cls, context: SignalContext): pass
    @classmethod
    async def after_bulk_create(cls, context: SignalContext): pass

# 带操作检测的信号装饰器
@emit_signals(Operation.SAVE)  # 调用 _determine_save_operation() 获取实际操作
async def save(self): pass
```

### 异常处理

```python
# 异常类
SQLObjectsError           # 根异常
├── DoesNotExist         # 查询无结果
├── MultipleObjectsReturned  # 多个结果
├── ValidationError      # 验证错误
├── DatabaseError        # 数据库错误
│   ├── IntegrityError   # 完整性约束
│   └── TransactionError # 事务错误
└── ConfigurationError   # 配置错误

# 错误创建
create_validation_error(code, field=None, params=None)

# 错误收集
collector = ValidationErrorCollector()
collector.add_error(field, message)
collector.raise_if_errors()
```

### 性能工具

```python
# 字段缓存
field_cache = Model._get_field_cache()
deferred_fields = field_cache.get("deferred_fields", set())

# 批量操作
.bulk_create(objects, batch_size=1000)
.bulk_update(mappings, batch_size=500)
.bulk_delete(ids, batch_size=1000)

# 性能分析
await queryset.explain(analyze=True)
```

### 工具函数

```python
# 命名转换
to_snake_case(name)
to_camel_case(name, pascal=True)
pluralize(word)
singularize(word)

# 调试工具
get_field_validators(model_class, field_name)
get_model_metadata(model_class)
```

## 使用指南

### 基础使用

```python
# 基本信号使用
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn
from sqlobjects.signals import SignalContext
from datetime import datetime

class User(ObjectModel):  # 信号功能已内置
    name: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
  
    async def before_save(self, context: SignalContext):
        # 保存前处理
        self.updated_at = datetime.now()
  
    async def after_create(self, context: SignalContext):
        # 创建后处理
        await self.send_welcome_email()

# 异常处理
try:
    user = await User.objects.get(User.email == "test@example.com")
except DoesNotExist:
    user = await User.objects.create(
        name="Test User",
        email="test@example.com"
    )
except ValidationError as e:
    print(f"Validation failed: {e.message}")

# 工具函数使用
table_name = to_snake_case("UserProfile")  # "user_profile"
model_name = to_camel_case(table_name)     # "UserProfile"
```

### 高级使用

```python
# 复杂信号处理
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext, Operation
from datetime import datetime

class User(ObjectModel):
    async def before_save(self, context: SignalContext):
        # 通用保存逻辑
        # context.actual_operation 由 _determine_save_operation() 设置
        if context.actual_operation == Operation.CREATE:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
  
    async def after_create(self, context: SignalContext):
        # 创建后异步任务
        await self.create_user_profile()
        await self.send_welcome_email()
        await self.log_user_creation(context.session)
  
    @classmethod
    async def before_bulk_create(cls, context: SignalContext):
        # 批量创建前处理
        print(f"Creating {context.affected_count} users")

# 高级异常处理
class UserValidator:
    def __init__(self):
        self.collector = ValidationErrorCollector()
  
    def validate_user_data(self, data):
        if not data.get("name"):
            self.collector.add_error("name", "Name is required")
      
        if not data.get("email"):
            self.collector.add_error("email", "Email is required")
        elif "@" not in data["email"]:
            self.collector.add_error("email", "Invalid email format")
      
        self.collector.raise_if_errors()

# 性能优化使用
# 字段缓存统计
field_cache = User._get_field_cache()
print(f"Deferred fields: {len(field_cache.get('deferred_fields', set()))}")
print(f"Relationship fields: {len(field_cache.get('relationship_fields', set()))}")

# 批量操作优化
users_data = [{"name": f"User{i}", "email": f"user{i}@example.com"} 
              for i in range(1000)]
await User.objects.bulk_create(users_data, batch_size=100)

# 智能预取优化
users = await User.objects.prefetch_related(
    active_posts=Post.objects.filter(Post.is_active == True)
                             .order_by("-created_at")
                             .limit(5)
).all()

# 查询性能分析
plan = await User.objects.filter(User.is_active == True).explain(
    analyze=True, 
    output="json"
)
print(f"Query cost: {plan['query_plan'][0].get('Total Cost', 'N/A')}")

# 自定义工具函数
def format_model_name(name: str) -> str:
    """格式化模型名称"""
    return to_camel_case(to_snake_case(name))

def get_table_name(model_class) -> str:
    """获取模型表名"""
    if hasattr(model_class, '__table__'):
        return model_class.__table__.name
    return pluralize(to_snake_case(model_class.__name__))

# 调试和监控
metadata = get_model_metadata(User)
print(f"Model: {metadata['model_name']}")
print(f"Table: {metadata['table_name']}")
print(f"Fields: {list(metadata['fields'].keys())}")
```

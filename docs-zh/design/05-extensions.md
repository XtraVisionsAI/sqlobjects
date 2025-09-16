# SQLObjects 扩展功能设计文档

## 概述

SQLObjects 扩展功能通过 ObjectModel 内置集成，提供信号系统、智能操作检测、性能优化和代理系统等增强功能。通过 Mixin 组合模式和统一状态管理，为核心功能提供无缝集成的扩展能力。

## 核心特性

### 1. 内置信号系统

ObjectModel 内置 SignalMixin，提供完整的模型生命周期信号和智能操作检测：

```python
from sqlobjects.model import ObjectModel  # 已内置 SignalMixin
from sqlobjects.fields import Column, StringColumn
from datetime import datetime

class User(ObjectModel):  # 自动具备信号功能
    name: Column[str] = StringColumn(length=50)
    
    # 实例级信号 - 自动集成
    async def before_save(self, context):
        # context.actual_operation 显示实际操作类型
        self.updated_at = datetime.now()
    
    async def before_create(self, context):
        self.created_at = datetime.now()
    
    async def after_create(self, context):
        await self.send_welcome_email()
    
    # 类级批量信号
    @classmethod
    async def before_bulk_create(cls, context):
        print(f"Creating {context.affected_count} users")

# @emit_signals 装饰器自动处理信号发射
user = User(name="John")  # 无主键值
await user.save()  # 自动检测 CREATE，发射双信号

user.name = "John Updated"
await user.save()  # 自动检测 UPDATE，只更新脏字段
```

### 2. 异常处理

层次化的异常系统，提供详细的错误信息和统一的错误处理：

```python
# 异常层次结构
try:
    user = await User.objects.get(User.id == 999)
except DoesNotExist:
    print("用户不存在")
except ValidationError as e:
    if e.is_multiple:
        for field, errors in e.field_errors.items():
            print(f"{field}: {', '.join(errors)}")
except SQLObjectsError:
    print("SQLObjects 操作错误")

# 验证错误收集
collector = ValidationErrorCollector()
collector.add_error("email", "Invalid email format")
collector.add_error("age", "Age must be positive")
collector.raise_if_errors()
```

### 3. 集成性能优化

通过 QueryCache FIFO 缓存、批量操作优化和 FieldCacheMixin 代理系统提供性能增强：

```python
# QueryCache FIFO 缓存 - 自动管理缓存大小
users = await User.objects.filter(User.is_active == True).all()  # 缓存 miss
users = await User.objects.filter(User.is_active == True).all()  # 缓存 hit

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
# await user.bio.fetch() 才真正加载

# 关系代理 - RelationFieldProxy
# user.posts 返回 RelationFieldProxy
# await user.posts.fetch() 加载关系数据
```

### 4. 工具函数

实用的工具函数和辅助类，简化常见操作：

```python
# 命名转换工具
from sqlobjects.utils.naming import to_snake_case, to_camel_case
from sqlobjects.utils.pattern import pluralize, singularize

snake_name = to_snake_case("UserProfile")  # "user_profile"
camel_name = to_camel_case("user_profile")  # "UserProfile"
plural = pluralize("user")                  # "users"

# 调试工具
query_stats = QuerySet.get_cache_stats()
print(f"Cache hit rate: {query_stats['hit_rate']:.2%}")
```

## 模块架构

### 核心组件

**模型集成层**
- **ObjectModel**: 组合所有 Mixin 的完整模型基类，内置所有扩展功能
- **ModelMixin**: 组合 FieldCacheMixin + SignalMixin + HistoryTrackingMixin

**信号系统层**
- **SignalMixin**: 信号混入类，内置在 ObjectModel 中
- **@emit_signals**: 信号装饰器，自动处理信号发射和操作检测
- **Operation**: 操作类型枚举，支持 SAVE/DELETE 等

**代理系统层**
- **DeferredFieldProxy**: 延迟字段代理，支持懒加载和缓存
- **RelationFieldProxy**: 关系字段代理，支持关系懒加载
- **FieldCacheMixin**: 集成代理系统到 __getattribute__ 中

**状态管理层**
- **StateManager**: 统一实例状态管理，支持多种状态类型
- **HistoryTrackingMixin**: 历史跟踪和脏字段检测

**性能工具层**
- **QueryCache**: FIFO 缓存机制，集成在 QuerySet 中
- **ValidationError**: 分层异常系统，支持单字段和多字段错误

### 设计理念

**内置集成**: 所有扩展功能内置在 ObjectModel 中，无需显式配置
**Mixin 组合**: 通过 Mixin 组合避免复杂继承，提高可维护性
**统一状态**: StateManager 统一管理实例状态，支持多种状态类型
**智能代理**: 通过 __getattribute__ 集成代理系统，提供透明的延迟加载
**装饰器驱动**: @emit_signals 装饰器自动处理信号发射和操作检测
**性能内置**: 缓存、批量操作和代理系统内置在核心组件中

### 与其他模块的集成

**核心架构模块**: 集成信号系统到模型生命周期
**数据操作模块**: 提供批量操作优化和查询缓存
**字段系统模块**: 集成验证错误处理和异常系统

## API 参考

### 信号系统

```python
# 信号功能（ObjectModel 已内置）
class Model(ObjectModel):
    # 实例级信号
    async def before_save(self, context): pass
    async def after_save(self, context): pass
    async def before_create(self, context): pass
    async def after_create(self, context): pass
    async def before_update(self, context): pass
    async def after_update(self, context): pass
    async def before_delete(self, context): pass
    async def after_delete(self, context): pass
    
    # 批量操作信号
    @classmethod
    async def before_bulk_create(cls, context): pass
    @classmethod
    async def after_bulk_create(cls, context): pass

# 信号装饰器
@emit_signals(Operation.SAVE)
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
# 查询缓存
QuerySet.get_cache_stats()
QuerySet.clear_query_cache()

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

### 基础用法

```python
# 基础信号使用
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn

class User(ObjectModel):  # 已内置信号功能
    name: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    
    async def before_save(self, context):
        # 保存前处理
        self.updated_at = datetime.now()
    
    async def after_create(self, context):
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

### 高级用法

```python
# 复杂信号处理
from sqlobjects.model import ObjectModel
from sqlobjects.signals import Operation
from datetime import datetime

class User(ObjectModel):
    async def before_save(self, context):
        # 通用保存逻辑
        if context.actual_operation == Operation.CREATE:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
    
    async def after_create(self, context):
        # 创建后异步任务
        await self.create_user_profile()
        await self.send_welcome_email()
        await self.log_user_creation(context.session)
    
    @classmethod
    async def before_bulk_create(cls, context):
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
# 查询缓存统计
stats = QuerySet.get_cache_stats()
print(f"Cache hits: {stats['hits']}, misses: {stats['misses']}")

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
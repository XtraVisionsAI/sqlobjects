# SQLObjects Objects 设计文档

## 概述

SQLObjects Objects 模块提供 Django 风格的对象管理器，实现模型 CRUD 操作、批量操作和高级查询功能。通过 ObjectsManager
类，为每个模型提供统一的数据库操作接口。

## 核心特性

### 1. Django 风格对象管理器

提供类似 Django ORM 的 objects 接口，支持链式查询和方法调用：

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import str_column, int_column

class User(ObjectModel):
    name: Column[str] = str_column(length=50)
    age: Column[int] = int_column()

# 基础查询操作
users = await User.objects.all()                    # 获取所有用户
user = await User.objects.get(User.name == "John")  # 获取单个用户
first_user = await User.objects.first()             # 获取第一个用户

# 链式查询
active_users = await User.objects.filter(
    User.age >= 18
).order_by("name").limit(10).all()                  # 链式查询操作
```

### 2. 高效批量操作

支持批量创建、更新和删除操作，实现高性能数据库操作：

```python
# 批量创建
users_data = [
    {"name": "Alice", "age": 25},
    {"name": "Bob", "age": 30},
    {"name": "Charlie", "age": 35}
]
await User.objects.bulk_create(users_data)

# 批量更新
update_data = [
    {"id": 1, "age": 26},
    {"id": 2, "age": 31},
    {"id": 3, "age": 36}
]
affected = await User.objects.bulk_update(update_data, match_fields=["id"])

# 批量删除
await User.objects.bulk_delete([1, 2, 3], id_field="id")
```

### 3. 智能获取或创建操作

提供 get_or_create 和 update_or_create 方法，简化常见数据操作模式。这些方法通过调用模型实例的 `save()` 方法来触发信号机制并复用验证逻辑：

```python
# 获取或创建用户 - 自动触发信号和验证
user, created = await User.objects.get_or_create(
    username="john",  # 查找条件
    defaults={"age": 25, "email": "john@example.com"}  # 创建时的默认值
)

# 更新或创建用户 - 使用 save() 方法触发信号
user, created = await User.objects.update_or_create(
    username="john",  # 查找条件
    defaults={"last_login": datetime.now()}  # 更新/创建时的值
)

# 复杂条件查找
user, created = await User.objects.get_or_create(
    username="john",
    is_active=True,  # 多个查找条件
    defaults={"email": "john@example.com"}
)
```

**信号集成特性：**
- `get_or_create` 创建新对象时会触发 `before_save`、`after_save`、`before_create`、`after_create` 信号
- `update_or_create` 更新现有对象时会触发 `before_save`、`after_save`、`before_update`、`after_update` 信号
- 创建新对象时会触发相应的创建信号
- 所有操作都会执行完整的验证流程（如果 `validate=True`）

### 4. 默认排序支持

支持模型级别的默认排序配置，自动应用到查询中：

```python
class User(ObjectModel):
    name: Column[str] = str_column()
    created_at: Column[datetime] = datetime_column()
    
    class Config:
        ordering = ["-created_at", "name"]  # 默认排序

# 自动应用默认排序
users = await User.objects.all()        # 按 -created_at, name 排序
first_user = await User.objects.first() # 使用默认排序
last_user = await User.objects.last()   # 使用默认排序

# 跳过默认排序以提升性能
count = await User.objects.filter().skip_default_ordering().count()
```

## 模块架构

### 核心组件

#### 1. ObjectsDescriptor - 描述符协议

实现描述符协议，为每个模型类提供 objects 属性：

```python
class ObjectsDescriptor(Generic[T]):
    """为模型类提供 Django 风格 objects 属性的描述符"""
    
    def __init__(self, model_class: type[T]) -> None:
        self._model_class = model_class
    
    def __get__(self, obj: Any, owner: type[T]) -> "ObjectsManager[T]":
        """返回模型类的 ObjectsManager 实例"""
        return ObjectsManager(self._model_class)

# 自动附加到模型类
class User(ObjectModel):
    name: Column[str] = str_column()

# User.objects 返回 ObjectsManager[User] 实例
```

#### 2. ObjectsManager - 核心管理器类

提供所有数据库操作方法的核心管理器类：

```python
class ObjectsManager(Generic[T]):
    """提供类似 Django ORM 接口的对象管理器"""
    
    def __init__(self, model_class: type[T], db_or_session: str | AsyncSession | None = None):
        self._model = model_class
        self._db_or_session = db_or_session
    
    @property
    def _session(self) -> AsyncSession:
        """获取有效的会话对象"""
        if self._db_or_session is None:
            return SessionContextManager.get_session()
        elif isinstance(self._db_or_session, str):
            return SessionContextManager.get_session(self._db_or_session)
        else:
            return self._db_or_session
    
    # 会话指定方法
    def using(self, db_or_session: str | AsyncSession) -> "ObjectsManager[T]":
        """指定数据库名称或会话对象"""
        return ObjectsManager(self._model, db_or_session)
    
    # 基础查询方法
    def filter(self, *args) -> QuerySet[T]:
        """过滤对象"""
        return QuerySet(self._model, None, self._session).filter(*args)
```

#### 3. 方法分类

ObjectsManager 方法按功能分类：

```python
# 基础查询方法
async def all(self) -> list[T]                      # 获取所有对象
async def get(self, *args) -> T                     # 获取单个对象
async def first(self) -> T | None                   # 获取第一个对象
async def last(self) -> T | None                    # 获取最后一个对象
async def earliest(self, *fields) -> T | None       # 获取最早的对象
async def latest(self, *fields) -> T | None         # 获取最新的对象
def iterator(self, memory_cleanup_interval=1000)    # 异步迭代器
async def get_item(self, key) -> T | list[T]         # 索引/切片访问
async def dates(self, field, kind, order="ASC") -> list[Any]      # 日期查询
async def datetimes(self, field, kind, order="ASC") -> list[Any]  # 日期时间查询
async def in_bulk(self, id_list=None, field_name="pk") -> dict[Any, T]  # 批量获取

# 创建操作
async def create(self, validate=True, **kwargs) -> T  # 创建单个对象
async def bulk_create(self, objects) -> None          # 批量创建

# 获取或创建操作（集成信号机制）
async def get_or_create(self, defaults=None, validate=True, **lookup) -> tuple[T, bool]
async def update_or_create(self, defaults=None, validate=True, **lookup) -> tuple[T, bool]

# 批量操作
async def bulk_update(self, mappings, match_fields=None, batch_size=1000) -> int
async def bulk_delete(self, ids, id_field="id", batch_size=1000) -> int
async def delete_all(self, fast=False) -> int
async def update_all(self, values) -> int

# 聚合和统计
async def count(self) -> int                         # 计数
async def aggregate(self, **kwargs) -> dict[str, Any]  # 聚合查询
async def values(self, *fields) -> list[dict[str, Any]]  # 获取字典值
async def values_list(self, *fields, flat=False) -> list  # 获取元组值

# 工具方法
async def random(self, count=1) -> list[T]           # 随机采样

# QuerySet 快捷方法
def filter(self, *args) -> QuerySet[T]              # 过滤
def distinct(self, *fields) -> QuerySet[T]           # 去重
def exclude(self, *args) -> QuerySet[T]              # 排除
def order_by(self, *fields) -> QuerySet[T]           # 排序
def limit(self, count) -> QuerySet[T]                # 限制数量
def offset(self, count) -> QuerySet[T]               # 偏移
def only(self, *fields) -> QuerySet[T]               # 仅加载指定字段
def defer(self, *fields) -> QuerySet[T]              # 延迟加载字段
def none(self) -> QuerySet[T]                        # 空查询集
def reverse(self) -> QuerySet[T]                     # 反转排序
def select_for_update(self, nowait=False, skip_locked=False) -> QuerySet[T]  # 行锁
def slice(self, start, stop=None) -> QuerySet[T]     # 切片

# 关系和连接
def select_related(self, *relations) -> QuerySet[T]  # 预加载关系
def prefetch_related(self, *relations) -> QuerySet[T]  # 预取关系
def join(self, target_model, on_condition=None, join_type="inner") -> QuerySet[T]  # 连接
def leftjoin(self, target, onclause=None) -> QuerySet[T]   # 左连接
def outerjoin(self, target, onclause=None) -> QuerySet[T]  # 外连接

# 高级查询方法
def annotate(self, **kwargs) -> QuerySet[T]          # 注解
def group_by(self, *fields) -> QuerySet[T]           # 分组
def having(self, *conditions) -> QuerySet[T]         # Having 条件
def options(self, *options) -> QuerySet[T]           # SQLAlchemy 选项
```

### 默认排序集成

ObjectsManager 与模型的默认排序配置集成：

```python
class User(ObjectModel):
    name: Column[str] = str_column()
    created_at: Column[datetime] = datetime_column()
    
    class Config:
        ordering = ["-created_at", "name"]  # 存储为 _default_ordering

# 自动应用默认排序
users = await User.objects.all()        # 使用默认排序
first_user = await User.objects.first() # 使用默认排序

# QuerySet 方法委托给带有默认排序的 QuerySet
queryset = User.objects.filter(User.is_active == True)  # 包含默认排序
```

### 会话管理集成

#### 统一会话管理模式

所有 ObjectsManager 方法都支持通过 using() 方法指定会话：

```python
# 使用默认会话
users = await User.objects.all()

# 使用指定会话
users = await User.objects.using(session).all()

# 使用数据库名称
users = await User.objects.using("analytics").all()
```

#### 多数据库支持

通过会话参数支持多数据库操作：

```python
# 使用默认数据库
users = await User.objects.all()

# 使用特定数据库会话
users = await User.objects.using(analytics_session).all()

# 跨数据库操作
main_users = await User.objects.using(main_session).filter(User.is_active == True).all()
archived_users = await User.objects.using(archive_session).filter(User.is_active == False).all()
```

### 与其他模块的集成

#### 与 QuerySet 模块的集成

ObjectsManager 将复杂查询操作委托给 QuerySet：

```python
# ObjectsManager 创建 QuerySet 实例
def filter(self, *args) -> QuerySet[T]:
    return QuerySet(self._model, None, self._session).filter(*args)

# QuerySet 处理复杂查询构建
queryset = User.objects.filter(User.age >= 18).order_by("name")
users = await queryset.all()  # 执行查询
```

#### 与验证系统的集成

ObjectsManager 在创建操作中集成验证系统：

```python
# 在创建操作期间应用验证
user = await User.objects.create(
    username="john",
    email="john@example.com",
    validate=True  # 启用验证
)

# 在 get_or_create 操作中验证
user, created = await User.objects.get_or_create(
    User.username == "john",
    defaults={"email": "john@example.com"},
    validate=True
)
```

#### 与信号系统的集成

ObjectsManager 操作触发相应的信号：

```python
# 操作期间触发的信号
user = await User.objects.create(username="john")  # 触发 before_save, after_save
await User.objects.bulk_update(mappings)           # 触发 before_update, after_update
await User.objects.delete_all()                    # 触发 before_delete, after_delete
```

## API 参考

### 基础查询操作

```python
# 获取所有对象
users = await User.objects.all()

# 获取单个对象
user = await User.objects.get(User.username == "john")

# 获取第一个/最后一个对象
first_user = await User.objects.first()
last_user = await User.objects.last()

# 按字段获取最早/最新的对象
earliest = await User.objects.earliest("created_at")
latest = await User.objects.latest("created_at")

# 检查存在性
exists = await User.objects.filter(User.username == "john").exists()

# 计数对象
count = await User.objects.count()
```

### 创建操作

```python
# 创建单个对象
user = await User.objects.create(
    username="john",
    email="john@example.com",
    validate=True
)

# 批量创建
users_data = [
    {"username": "alice", "email": "alice@example.com"},
    {"username": "bob", "email": "bob@example.com"}
]
await User.objects.bulk_create(users_data)

# 获取或创建（使用 save() 方法触发信号）
user, created = await User.objects.get_or_create(
    username="john",  # 查找条件
    defaults={"email": "john@example.com"}  # 创建时的默认值
)

# 更新或创建（使用 save() 方法触发信号）
user, created = await User.objects.update_or_create(
    username="john",  # 查找条件
    defaults={"last_login": datetime.now()}  # 更新/创建时的值
)
```

### 批量操作

```python
# 批量更新
mappings = [
    {"id": 1, "status": "active"},
    {"id": 2, "status": "inactive"}
]
affected = await User.objects.bulk_update(mappings, match_fields=["id"])

# 批量删除
affected = await User.objects.bulk_delete([1, 2, 3], id_field="id")

# 更新所有匹配的对象
affected = await User.objects.filter(User.is_active == False).update(
    values={"status": "archived"}
)

# 删除所有匹配的对象
affected = await User.objects.filter(User.created_at < cutoff_date).delete()
```

### 数据提取

```python
# 获取字典形式的值
user_data = await User.objects.values("id", "username", "email")

# 获取元组形式的值
user_tuples = await User.objects.values_list("username", "email")

# 获取单个字段的扁平列表
usernames = await User.objects.values_list("username", flat=True)

# 按 ID 批量检索
user_dict = await User.objects.in_bulk([1, 2, 3], field_name="id")
```

### 会话管理

```python
# 使用特定会话
users = await User.objects.using(session).all()

# 使用数据库名称
users = await User.objects.using("analytics").all()

# 与会话链式调用
active_users = await User.objects.using(session).filter(
    User.is_active == True
).order_by("username").all()
```

## 使用指南

### 基础用法

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import str_column, int_column, bool_column

class User(ObjectModel):
    username: Column[str] = str_column(length=50, unique=True)
    email: Column[str] = str_column(length=100)
    age: Column[int] = int_column()
    is_active: Column[bool] = bool_column(default=True)

# 基础 CRUD 操作
user = await User.objects.create(
    username="john",
    email="john@example.com",
    age=25
)

user = await User.objects.get(User.username == "john")
users = await User.objects.filter(User.age >= 18).all()
count = await User.objects.count()
```

### 高级用法

```python
from sqlobjects.queries import Q
from sqlobjects.expressions import func

# 使用 Q 对象的复杂查询
users = await User.objects.filter(
    Q(User.age >= 18) & (Q(User.is_active == True) | Q(User.is_staff == True))
).select_related("profile").prefetch_related("posts").all()

# 聚合查询
stats = await User.objects.aggregate(
    total_users=func.count(),
    avg_age=func.avg(User.age),
    max_age=func.max(User.age)
)

# 性能优化的批量操作
update_data = [
    {"id": 1, "last_login": datetime.now()},
    {"id": 2, "last_login": datetime.now()}
]
affected = await User.objects.bulk_update(update_data, match_fields=["id"])

# 多数据库操作
main_users = await User.objects.using("main").filter(User.is_active == True).all()
archive_users = await User.objects.using("archive").filter(User.is_active == False).all()

# 默认排序配置
class Post(ObjectModel):
    title: Column[str] = str_column()
    created_at: Column[datetime] = datetime_column()
    
    class Config:
        ordering = ["-created_at"]  # 最新文章优先

# 自动应用排序
latest_posts = await Post.objects.all()  # 按 -created_at 排序
first_post = await Post.objects.first()  # 最新文章
```
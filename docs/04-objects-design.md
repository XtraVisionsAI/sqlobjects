# SQLObjects Objects 设计说明文档

## 概述

SQLObjects Objects 模块提供 Django 风格的对象管理器，实现模型的 CRUD 操作、批量操作和高级查询功能。通过 ObjectsManager
类为每个模型提供统一的数据库操作接口。

## 核心特性

### 1. Django 风格的对象管理器

提供类似 Django ORM 的 objects 风格接口，支持链式查询和方法调用：

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

### 2. 高效的批量操作

支持批量创建、更新和删除，提供高性能的数据库操作：

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

### 3. 智能的获取或创建操作

提供 get_or_create 和 update_or_create 方法，简化常见的数据操作模式：

```python
# 获取或创建用户
user, created = await User.objects.get_or_create(
    User.name == "John",
    defaults={"age": 25, "email": "john@example.com"}
)

# 更新或创建用户
user, created = await User.objects.update_or_create(
    User.name == "John",
    defaults={"last_login": datetime.now()}
)

# 使用复杂条件
user, created = await User.objects.get_or_create(
    Q(User.name == "John") | Q(User.email == "john@example.com"),
    defaults={"is_active": True}
)
```

## 模块架构

### 核心组件

#### 1. ObjectsDescriptor 描述符

实现描述符协议，为每个模型类提供 objects 属性：

```python
class ObjectsDescriptor(Generic[T]):
    """描述符，为模型类提供 objects 属性"""
    
    def __init__(self, model_class: type[T]):
        self._model_class = model_class
    
    def __get__(self, obj: Any, owner: type[T]) -> "ObjectsManager[T]":
        """返回模型类的 ObjectsManager 实例"""
        return ObjectsManager(self._model_class)

# 自动附加到模型类
class User(ObjectModel):
    name: Column[str] = str_column()

# User.objects 返回 ObjectsManager[User] 实例
```

#### 2. ObjectsManager 管理器

核心管理器类，提供所有数据库操作方法：

```python
class ObjectsManager(Generic[T]):
    """对象管理器，提供 Django ORM 风格接口"""
    
    def __init__(self, model_class: type[T], db_or_session: str | AsyncSession | None = None):
        self._model = model_class
        self._db_or_session = db_or_session
    
    @property
    def _session(self):
        if self._db_or_session is None:
            return SessionContextManager.get_session()
        elif isinstance(self._db_or_session, str):
            return SessionContextManager.get_session(self._db_or_session)
        else:
            return self._db_or_session
    
    # 会话指定方法
    def using(self, db_or_session: str | AsyncSession) -> "ObjectsManager[T]":
        """指定数据库名或会话对象"""
        return ObjectsManager(self._model, db_or_session)
    
    # 基础查询方法
    def filter(self, *args) -> QuerySet[T]:
        """过滤对象"""
        return QuerySet(self._model, db_or_session=self._db_or_session).filter(*args)
    
    async def get(self, *args) -> T:
        """获取单个对象"""
        results = await self.filter(*args).limit(2).all()
        if not results:
            raise DoesNotExist(f"{self._model.__name__} matching query does not exist")
        if len(results) > 1:
            raise MultipleObjectsReturned(f"Multiple {self._model.__name__} objects returned")
        return results[0]
```

#### 3. 方法分类

ObjectsManager 的方法按功能分为几个主要类别：

```python
# 基础查询方法
async def all(self) -> list[T]
async def get(self, *args) -> T
async def first(self) -> T | None
async def last(self) -> T | None
async def earliest(self, *fields) -> T | None
async def latest(self, *fields) -> T | None
def iterator(self, memory_cleanup_interval=1000)
async def get_item(self, key) -> T | list[T]
async def dates(self, field, kind, order="ASC") -> list[Any]
async def datetimes(self, field, kind, order="ASC") -> list[Any]
async def in_bulk(self, id_list=None, field_name="pk") -> dict[Any, T]

# 创建操作
async def create(self, validate=True, **kwargs) -> T
async def bulk_create(self, objects) -> None

# 获取或创建操作
async def get_or_create(self, *filters, defaults=None, validate=True) -> tuple[T, bool]
async def update_or_create(self, *filters, defaults=None, validate=True) -> tuple[T, bool]

# 批量操作
async def bulk_update(self, mappings, match_fields=None, batch_size=1000) -> int
async def bulk_delete(self, ids, id_field="id", batch_size=1000) -> int
async def delete_all(self, fast=False) -> int
async def update_all(self, values) -> int

# 聚合和统计
async def count(self) -> int
async def aggregate(self, **kwargs) -> dict[str, Any]
async def values(self, *fields) -> list[dict[str, Any]]
async def values_list(self, *fields, flat=False) -> list

# 工具方法
async def random(self, count=1) -> list[T]

# QuerySet 快捷方法
def filter(self, *args) -> QuerySet[T]
def distinct(self, *fields) -> QuerySet[T]
def exclude(self, *args) -> QuerySet[T]
def order_by(self, *fields) -> QuerySet[T]
def limit(self, count) -> QuerySet[T]
def offset(self, count) -> QuerySet[T]
def only(self, *fields) -> QuerySet[T]
def defer(self, *fields) -> QuerySet[T]
def none(self) -> QuerySet[T]
def reverse(self) -> QuerySet[T]
def select_for_update(self, nowait=False, skip_locked=False) -> QuerySet[T]
def slice(self, start, stop=None) -> QuerySet[T]

# 关系和连接
def select_related(self, *relations) -> QuerySet[T]
def prefetch_related(self, *relations) -> QuerySet[T]
def join(self, target_model, on_condition=None, join_type="inner") -> QuerySet[T]
def leftjoin(self, target, onclause=None) -> QuerySet[T]
def outerjoin(self, target, onclause=None) -> QuerySet[T]

# 高级查询方法
def annotate(self, **kwargs) -> QuerySet[T]
def group_by(self, *fields) -> QuerySet[T]
def having(self, *conditions) -> QuerySet[T]
def options(self, *options) -> QuerySet[T]
```

### 会话管理集成

#### 统一的会话管理模式

所有 ObjectsManager 方法都通过 using() 方法支持会话指定：

```python
# 使用默认会话
users = await User.objects.all()

# 使用指定会话
users = await User.objects.using(session).all()
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

#### 与 queries 模块的集成

ObjectsManager 大量使用 queries 模块的 QuerySet 类：

```python
# objects.py 中使用 QuerySet
from .queries import QuerySet, T

class ObjectsManager(Generic[T]):
    def filter(self, *args) -> QuerySet[T]:
        """返回 QuerySet 实例进行链式操作"""
        return QuerySet(self._session, self._model).filter(*args)
    
    def order_by(self, *fields) -> QuerySet[T]:
        """委托给 QuerySet 的排序方法"""
        return self.filter().order_by(*fields)
    
    def limit(self, count: int) -> QuerySet[T]:
        """委托给 QuerySet 的限制方法"""
        return self.filter().limit(count)
```

#### 与 model 模块的集成

ObjectsManager 通过 ObjectsDescriptor 自动附加到 ObjectModel：

```python
# model 模块中的集成
class ObjectModel(DeclarativeBase, ModelMixin):
    def __init_subclass__(cls, **kwargs):
        # ... 其他初始化逻辑
        if not is_abstract and not hasattr(cls, "objects"):
            cls.objects = ObjectsDescriptor(cls)

# 使用效果
class User(ObjectModel):
    name: Column[str] = str_column()

# User.objects 自动可用
users = await User.objects.all()
```

#### 与 exceptions 模块的集成

ObjectsManager 使用 exceptions 模块处理查询和操作错误，并提供增强的错误信息和多错误支持：

```python
# objects.py 中使用异常系统
from .exceptions import DoesNotExist, MultipleObjectsReturned, ValidationError

class ObjectsManager:
    async def get(self, *args) -> T:
        """获取单个对象，使用标准异常"""
        results = await self.filter(*args).limit(2).all()
        
        if not results:
            raise DoesNotExist(f"{self._model.__name__} matching query does not exist")
        
        if len(results) > 1:
            raise MultipleObjectsReturned(f"Multiple {self._model.__name__} objects returned")
        
        return results[0]
    
    async def create(self, validate=True, **kwargs) -> T:
        """创建对象，支持单个和多个验证错误的增强处理"""
        try:
            obj = self._model(**kwargs)
            if self._db_or_session:
                await obj.using(self._db_or_session).save(validate=validate)
            else:
                await obj.save(validate=validate)
            return obj
        except ValidationError as e:
            if not e.is_multiple:
                # 单个错误的增强处理
                enhanced_error = ValidationError(
                    f"Failed to create {self._model.__name__}: {e.message}",
                    field=e.field, code=e.code, params=e.params
                )
                enhanced_error.operation = "create"
                enhanced_error.model_class = self._model.__name__
                raise enhanced_error from e
            else:
                # 多个错误的增强处理
                enhanced_message = f"Failed to create {self._model.__name__}: {e.message}"
                enhanced_error = ValidationError(enhanced_message, field_errors=e.field_errors)
                enhanced_error.operation = "create"
                enhanced_error.model_class = self._model.__name__
                raise enhanced_error from e
```

#### 与 signals 模块的集成

ObjectsManager 的操作方法集成信号系统，支持批量操作和实例操作的信号触发：

```python
# 批量操作中的信号触发
async def bulk_create(self, objects):
    session = self._session
    context = SignalContext(
        operation=Operation.SAVE, 
        session=session, 
        model_class=self._model, 
        affected_count=len(objects)
    )
    await self._model._emit_class_signal("before", context)
    
    # 执行数据库操作
    stmt = insert(self._model).values(objects)
    await session.execute(stmt)
    
    # 更新上下文并发送后置信号
    context.affected_count = len(objects)
    await self._model._emit_class_signal("after", context)

# update_or_create 中的实例信号触发
async def update_or_create(self, *filters, defaults=None, validate=True):
    try:
        obj = await self.filter(*filters).get()
        if defaults:
            # 为更新操作发送信号
            session = self._session
            context = SignalContext(
                operation=Operation.SAVE, 
                session=session, 
                model_class=obj.__class__, 
                instance=obj
            )
            await obj._emit_signal("before", context)
            
            # 执行更新操作
            for key, value in defaults.items():
                setattr(obj, key, value)
            
            await obj._emit_signal("after", context)
        return obj, False
    except DoesNotExist:
        # 创建新对象时会通过 create() 方法自动触发信号
        return await self.create(validate=validate, **defaults), True
```

#### 模块职责分离

- **objects.py**: 负责对象管理器、批量操作、CRUD 接口
- **queries.py**: 负责查询构建、链式操作、查询执行
- **model.py**: 负责模型基类、实例方法、配置处理
- **exceptions.py**: 负责异常定义、错误处理
- **集成点**: 通过 ObjectsDescriptor 和 QuerySet 实现模块协作

## API 参考

### 基础查询方法

```python
# 获取所有对象
users = await User.objects.all()
users = await User.objects.using(custom_session).all()

# 获取单个对象
user = await User.objects.get(User.id == 1)
user = await User.objects.get(User.name == "John", User.is_active == True)

# 获取第一个/最后一个对象
first_user = await User.objects.first()
last_user = await User.objects.last()

# 获取最早/最新对象
earliest = await User.objects.earliest("created_at")
latest = await User.objects.latest("created_at", "updated_at")

# 迭代器（处理大数据集）
async for user in User.objects.iterator():
    print(user.name)

# 索引访问
user = await User.objects.get_item(0)        # 第一个用户
users = await User.objects.get_item(slice(0, 10))  # 前10个用户
```

### 创建操作

```python
# 创建单个对象
user = await User.objects.create(
    name="John",
    email="john@example.com",
    age=25
)

# 创建时跳过验证
user = await User.objects.create(
    name="John",
    email="invalid-email",  # 跳过邮箱验证
    validate=False
)

# 使用指定会话创建
user = await User.objects.using(analytics_session).create(
    name="John",
    email="john@example.com"
)

# 批量创建
users_data = [
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob", "email": "bob@example.com"},
    {"name": "Charlie", "email": "charlie@example.com"}
]
await User.objects.bulk_create(users_data)
```

### 获取或创建操作

```python
# 基础获取或创建
user, created = await User.objects.get_or_create(
    User.name == "John",
    defaults={"age": 25, "email": "john@example.com"}
)

# 更新或创建
user, created = await User.objects.update_or_create(
    User.name == "John",
    defaults={"last_login": datetime.now()}
)

# 复杂条件
user, created = await User.objects.get_or_create(
    Q(User.name == "John") | Q(User.email == "john@example.com"),
    defaults={"is_active": True}
)

# 批量获取
user_dict = await User.objects.in_bulk([1, 2, 3])  # 按主键
user_dict = await User.objects.in_bulk(["john", "alice"], field_name="name")  # 按字段
```

### 批量操作

```python
# 批量更新
update_data = [
    {"id": 1, "age": 26, "status": "active"},
    {"id": 2, "age": 31, "status": "inactive"}
]
affected = await User.objects.bulk_update(update_data, match_fields=["id"])

# 批量删除
affected = await User.objects.bulk_delete([1, 2, 3], id_field="id")

# 删除所有记录
affected = await User.objects.delete_all()  # 安全删除
affected = await User.objects.delete_all(fast=True)  # 快速删除（TRUNCATE）

# 更新所有记录
affected = await User.objects.update_all({"status": "migrated"})
```

### 日期和时间查询

```python
# 获取日期列表
dates = await User.objects.dates("created_at", "month")  # 按月分组
dates = await User.objects.dates("created_at", "year", order="DESC")  # 按年倒序

# 获取时间列表
datetimes = await User.objects.datetimes("created_at", "day")  # 按天分组
datetimes = await User.objects.datetimes("last_login", "hour")  # 按小时分组
```

### 聚合和统计

```python
# 计数
total = await User.objects.count()
active_count = await User.objects.filter(User.is_active == True).count()

# 聚合操作
stats = await User.objects.aggregate(
    avg_age=func.avg(User.age),
    max_age=func.max(User.age),
    min_age=func.min(User.age)
)

# 获取字段值
names = await User.objects.values("name", "email")
ages = await User.objects.values_list("age", flat=True)
name_age_pairs = await User.objects.values_list("name", "age")
```

### QuerySet 链式操作

```python
# 过滤和排序
users = await User.objects.filter(
    User.age >= 18
).exclude(
    User.status == "banned"
).order_by("-created_at").limit(10).all()

# 去重
unique_names = await User.objects.distinct("name").values_list("name", flat=True)

# 分页
page1 = await User.objects.slice(0, 10).all()  # 前10条
page2 = await User.objects.slice(10, 20).all()  # 第11-20条

# 字段选择
users = await User.objects.only("name", "email").all()  # 只加载指定字段
users = await User.objects.defer("bio", "avatar").all()  # 延迟加载指定字段
```

### 关系查询

```python
# 预加载关系
users = await User.objects.select_related("profile").all()  # JOIN 查询
users = await User.objects.prefetch_related("posts").all()  # 分离查询

# 手动连接
query = User.objects.join(Profile, User.id == Profile.user_id)
query = User.objects.leftjoin(Profile, User.id == Profile.user_id)
```

### 高级查询

```python
# 注解字段
users = await User.objects.annotate(
    post_count=func.count(Post.id)
).filter(
    User.post_count > 5
).all()

# 分组查询
stats = await User.objects.values("department").annotate(
    avg_salary=func.avg(User.salary)
).group_by("department").all()

# HAVING 子句
results = await User.objects.group_by("department").having(
    func.avg(User.salary) > 50000
).all()
```

### 锁定和事务

```python
# 行级锁定
user = await User.objects.select_for_update().get(User.id == 1)
user = await User.objects.select_for_update(nowait=True).get(User.id == 1)

# 跳过已锁定行
users = await User.objects.select_for_update(skip_locked=True).all()
```

### 工具方法

```python
# 随机获取
random_users = await User.objects.random(5)  # 随机获取5个用户
random_user = await User.objects.random()    # 随机获取1个用户

# 大数据集迭代
async for user in User.objects.iterator(memory_cleanup_interval=500):
    # 处理用户数据，每500条清理一次内存
    process_user(user)

# 索引访问
first_user = await User.objects.get_item(0)           # 第一个用户
last_user = await User.objects.get_item(-1)           # 最后一个用户
first_10 = await User.objects.get_item(slice(0, 10))  # 前10个用户
```

## 使用指南

### 基础用法

```python
# 简单查询操作
users = await User.objects.all()                    # 获取所有用户
user = await User.objects.get(User.name == "John")  # 获取单个用户
first_user = await User.objects.first()             # 获取第一个用户

# 基础过滤
active_users = await User.objects.filter(User.age >= 18).all()  # 年龄筛选
young_users = await User.objects.filter(User.age < 25).all()    # 年龄范围

# 创建和更新
user = await User.objects.create(name="Alice", age=25)  # 创建用户
user, created = await User.objects.get_or_create(
    User.name == "John",
    defaults={"age": 30}
)  # 获取或创建

# 使用指定会话
user = await User.objects.using(analytics_session).create(name="Bob", age=30)
```

### 复杂用法

```python
# 复杂查询条件 - 使用 Q 对象
from sqlobjects.queries import Q

complex_users = await User.objects.filter(
    Q(User.age >= 18) & Q(User.name.startswith("A"))
).all()  # Q 对象组合查询

# 使用 SQLAlchemy 原生语法
from sqlalchemy import or_, and_, not_

# or_ 方法：多条件或查询
users = await User.objects.filter(
    or_(User.age >= 65, User.is_vip == True)
).all()  # 年长用户或 VIP 用户

# and_ 方法：多条件与查询
users = await User.objects.filter(
    and_(User.age >= 18, User.age <= 65, User.is_active == True)
).all()  # 工作年龄段的活跃用户

# not_ 方法：否定条件
users = await User.objects.filter(
    not_(or_(User.is_banned == True, User.is_deleted == True))
).all()  # 未被封禁且未删除的用户

# 复杂条件嵌套
users = await User.objects.filter(
    and_(
        or_(User.role == "admin", User.role == "moderator"),
        User.is_active == True,
        not_(User.is_suspended == True)
    )
).all()  # 活跃的管理员或版主（未被暂停）

# 混合使用 Q 对象和 SQLAlchemy 语法
users = await User.objects.filter(
    Q(User.department == "IT") & or_(
        User.level >= 5,
        User.years_experience >= 10
    )
).all()  # IT 部门的高级或资深员工

# 批量操作优化
update_mappings = [
    {"id": 1, "last_login": datetime.now()},
    {"id": 2, "last_login": datetime.now()},
    # ... 更多记录
]
affected = await User.objects.bulk_update(
    update_mappings, 
    match_fields=["id"],
    batch_size=1000  # 批量处理优化
)

# 高级聚合查询
stats = await User.objects.aggregate(
    total_users=func.count(),
    avg_age=func.avg(User.age),
    max_age=func.max(User.age)
)

# 子查询和复杂关联
subquery = User.objects.filter(User.is_active == True).subquery()
results = await Post.objects.join(
    subquery, 
    Post.author_id == subquery.c.id
).all()
```

### 批量操作

```python
# 批量更新
update_data = [
    {"id": 1, "name": "Alice Updated", "age": 26},
    {"id": 2, "name": "Bob Updated", "age": 31},
    {"id": 3, "name": "Charlie Updated", "age": 36}
]
affected = await User.objects.bulk_update(
    update_data,
    match_fields=["id"],
    batch_size=1000
)

# 批量删除
deleted = await User.objects.bulk_delete(
    [1, 2, 3, 4, 5],
    id_field="id",
    batch_size=1000
)

# 删除所有记录
deleted = await User.objects.delete_all()

# 快速删除（使用 TRUNCATE）
await User.objects.delete_all(fast=True)

# 更新所有记录
affected = await User.objects.update_all({
    "status": "migrated",
    "updated_at": datetime.now()
})

# 使用指定会话更新
affected = await User.objects.using(analytics_session).update_all({
    "status": "migrated"
})
```

### 聚合和统计

```python
# 计数
total_users = await User.objects.count()
active_users = await User.objects.filter(User.is_active == True).count()

# 聚合操作
stats = await User.objects.aggregate(
    total_count=func.count(User.id),
    avg_age=func.avg(User.age),
    max_age=func.max(User.age),
    min_age=func.min(User.age)
)

# 获取字段值
user_names = await User.objects.values("name", "email")
# [{"name": "John", "email": "john@example.com"}, ...]

# 获取字段值列表
names = await User.objects.values_list("name", flat=True)
# ["John", "Alice", "Bob", ...]

name_email_pairs = await User.objects.values_list("name", "email")
# [("John", "john@example.com"), ("Alice", "alice@example.com"), ...]
```

### 批量获取

```python
# 按主键批量获取
users_dict = await User.objects.in_bulk([1, 2, 3, 4, 5])
# {1: <User id=1>, 2: <User id=2>, ...}

# 按其他字段批量获取
users_dict = await User.objects.in_bulk(
    ["john@example.com", "alice@example.com"],
    field_name="email"
)
# {"john@example.com": <User email="john@example.com">, ...}

# 获取所有对象的字典
all_users_dict = await User.objects.in_bulk()
```

### QuerySet 快捷方法

```python
# 过滤和排除
active_users = User.objects.filter(User.is_active == True)
inactive_users = User.objects.exclude(User.is_active == True)

# 排序
users_by_name = User.objects.order_by("name")
users_by_age_desc = User.objects.order_by("-age")

# 限制和偏移
first_10_users = User.objects.limit(10)
next_10_users = User.objects.offset(10).limit(10)
users_slice = User.objects.slice(10, 20)

# 去重
unique_ages = User.objects.distinct("age")

# 字段加载控制
users_name_only = User.objects.only("name", "email")
users_defer_bio = User.objects.defer("biography", "profile_data")

# 关系预加载
users_with_profile = User.objects.select_related("profile")
users_with_posts = User.objects.prefetch_related("posts")

# 锁定查询
locked_users = User.objects.select_for_update()
nowait_locked = User.objects.select_for_update(nowait=True)
```

### 高级查询方法

```python
# 注解
users_with_post_count = User.objects.annotate(
    post_count=func.count(Post.id)
).filter(User.post_count > 5)

# 分组
user_stats = User.objects.values("department").annotate(
    user_count=func.count(User.id),
    avg_salary=func.avg(User.salary)
).group_by("department")

# Having 子句
departments = User.objects.values("department").annotate(
    user_count=func.count(User.id)
).having(func.count(User.id) > 10)

# 手动连接
users_with_posts = User.objects.join(
    Post, 
    Post.author_id == User.id
).distinct()

# 查询选项
users_optimized = User.objects.options(
    joinedload(User.profile),
    selectinload(User.posts)
)
```

### 日期和时间查询

```python
# 日期查询
dates = await User.objects.dates("created_at", "month", order="DESC")
# [datetime.date(2023, 12, 1), datetime.date(2023, 11, 1), ...]

# 日期时间查询
datetimes = await User.objects.datetimes("created_at", "day", order="ASC")
# [datetime.datetime(2023, 12, 1, 0, 0), ...]
```

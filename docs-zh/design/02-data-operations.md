# SQLObjects 数据操作设计文档

## 概述

SQLObjects 数据操作模块采用组合模式架构，提供 Django 风格的数据库操作接口。通过 ObjectsDescriptor 描述符、组合式 QuerySet 和统一的 QueryExecutor 实现高性能的数据库访问。

## 核心特性

### 1. 描述符模式 Objects 管理器

通过 ObjectsDescriptor 描述符自动为每个模型类提供独立的 ObjectsManager 实例：

```python
# ObjectsDescriptor 自动设置
class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)
# 自动设置: User.objects = ObjectsDescriptor(User)

# ObjectsDescriptor 每次访问 User.objects 返回新的 ObjectsManager 实例
# 查询操作返回 ObjectModel 实例或实例列表
users = await User.objects.all()  # 返回 list[User]
user = await User.objects.get(User.name == "John")  # 返回 User 实例
first_user = await User.objects.first()  # 返回 User 实例或 None

# 链式查询 - ObjectsManager 方法返回 QuerySet
active_users = await User.objects.filter(
    User.age >= 18
).order_by("name").limit(10).all()

# 会话绑定 - 返回新的 ObjectsManager 实例
bound_manager = User.objects.using("analytics")
analytics_users = await bound_manager.all()
```

### 2. 组合模式 QuerySet 架构

QuerySet 使用组合模式，通过 QueryBuilder、QueryCache 和 QueryExecutor 组件实现：

```python
# QuerySet 组合组件
class QuerySet:
    def __init__(self, table, model_class, db_or_session=None):
        self._builder = QueryBuilder(model_class)      # 查询构建
        self._cache = QueryCache()                      # FIFO 缓存
        self._executor = QueryExecutor(db_or_session)   # 统一执行

# 链式构建 - 每个方法返回新的 QuerySet 实例
query = User.objects.filter(User.is_active == True)  # 新 QuerySet
query = query.filter(User.age >= 18)                 # 新 QuerySet
query = query.order_by(User.name)                    # 新 QuerySet
users = await query.all()  # 执行查询，使用缓存

# Q 对象逻辑组合 - 支持 SQLAlchemy 表达式
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).all()

# 组件共享 - 新 QuerySet 共享 cache 和 executor
new_qs = query.filter(User.department == "IT")
# new_qs._cache 与 query._cache 是同一个实例
```

### 3. CRUD 操作

完整的创建、读取、更新、删除操作支持：

```python
# 创建
user = await User.objects.create(name="Alice", age=25)

# 读取
user = await User.objects.get(User.id == 1)
users = await User.objects.filter(User.age >= 18).all()

# 更新
await User.objects.filter(User.id == 1).update(age=26)

# 删除
await User.objects.filter(User.id == 1).delete()
```

### 4. 信号集成批量处理

批量操作使用 @emit_signals 装饰器集成信号系统，支持批量信号发射：

```python
# 批量创建 - 自动发射 before_bulk_create/after_bulk_create 信号
@emit_signals(Operation.SAVE, is_bulk=True)
async def bulk_create(self, objects):
    # 实际实现使用 SQLAlchemy Core insert
    stmt = insert(self._table).values(objects)
    await session.execute(stmt)

users_data = [
    {"name": "Alice", "age": 25},
    {"name": "Bob", "age": 30}
]
await User.objects.bulk_create(users_data)

# 批量更新 - 使用 bindparam 和批处理
@emit_signals(Operation.SAVE, is_bulk=True)
async def bulk_update(self, mappings, match_fields=["id"], batch_size=1000):
    # 使用 SQLAlchemy Core update + bindparam
    # 支持批处理和参数绑定
    pass

update_data = [
    {"id": 1, "age": 26},
    {"id": 2, "age": 31}
]
affected_rows = await User.objects.bulk_update(update_data, match_fields=["id"])

# 批量删除 - 使用 IN 子句和批处理
deleted_rows = await User.objects.bulk_delete([1, 2, 3], batch_size=1000)
```

## 模块架构

### 核心组件

**管理器层**
- **ObjectsDescriptor**: 描述符模式，为每个模型类提供独立的 ObjectsManager 实例
- **ObjectsManager**: Django 风格的数据库操作管理器，支持会话绑定和批量操作

**查询构建层**
- **QuerySet**: 组合模式查询构建器，集成 QueryBuilder、QueryCache 和 QueryExecutor
- **QueryBuilder**: 不可变查询构建器，处理 SQL 构建和查询优化
- **Q**: SQLAlchemy 表达式逻辑组合器，支持 AND/OR/NOT 复杂条件

**执行层**
- **QueryExecutor**: 统一查询执行引擎，支持多种查询类型、迭代器和延迟加载
- **QueryCache**: FIFO 缓存机制，提供查询结果缓存和性能统计

### 设计理念

**描述符模式**: 通过 ObjectsDescriptor 为每个模型类提供独立的管理器实例
**组合模式架构**: QuerySet 通过组件组合避免 MRO 问题，提高可维护性
**不可变构建**: QueryBuilder 不可变设计，每个方法返回新实例
**组件共享**: 新 QuerySet 实例共享 cache 和 executor，提高性能
**统一执行**: QueryExecutor 单一执行方法处理所有查询类型
**信号集成**: 批量操作使用 @emit_signals 装饰器集成信号系统
**会话管理**: 支持 using() 方法进行会话绑定和 readonly 参数控制

### 与其他模块的集成

**核心架构模块**: 通过 SessionContextManager 获取数据库会话
**字段系统模块**: 支持字段表达式和函数调用
**关系处理模块**: 集成 select_related 和 prefetch_related

## API 参考

### Objects 管理器

```python
# 基础查询
await User.objects.all()
await User.objects.get(*conditions)
await User.objects.first()
await User.objects.count()

# 创建操作
await User.objects.create(**kwargs)
await User.objects.get_or_create(defaults=None, **lookup)
await User.objects.update_or_create(defaults=None, **lookup)

# 批量操作
await User.objects.bulk_create(objects)
await User.objects.bulk_update(mappings, match_fields)
await User.objects.bulk_delete(ids, id_field)
```

### QuerySet 方法

```python
# 查询构建方法（返回 QuerySet）
.filter(*conditions) / .exclude(*conditions)
.order_by(*fields) / .limit(count) / .offset(count)
.only(*fields) / .defer(*fields)
.select_related(*fields) / .prefetch_related(*fields)
.distinct(*fields) / .annotate(**kwargs)
.group_by(*fields) / .having(*conditions)
.join(table, condition) / .select_for_update()
.skip_default_ordering() / .reverse() / .none()

# 查询执行方法（执行查询）
await .all() / await .get() / await .first()
await .count() / await .exists()
await .last() / await .earliest() / await .latest()
await .values(*fields) / await .values_list(*fields)
await .aggregate(**kwargs) / await .raw(sql)
await .iterator() / await .create() / await .update() / await .delete()

# 日期时间查询方法
await .dates(field, precision, order) / await .datetimes(field, precision, order)

# 索引访问方法
await .get_item(index_or_slice)

# 缓存控制方法
.no_cache()

# 子查询方法
.subquery(name, query_type)
```

### Q 对象操作

```python
# 基本用法
Q(User.name == "John")
Q(User.age >= 18, User.is_active == True)

# 逻辑组合
Q(User.name == "John") & Q(User.age >= 18)
Q(User.role == "admin") | Q(User.is_staff == True)
~Q(User.is_deleted == True)
```

## 使用指南

### 基础用法

```python
# 简单查询
users = await User.objects.all()
user = await User.objects.get(User.name == "John")

# 过滤和排序
active_users = await User.objects.filter(
    User.is_active == True
).order_by("name").all()

# 创建和更新
user = await User.objects.create(name="Alice", age=25)
await User.objects.filter(User.id == user.id).update(age=26)
```

### 高级用法

```python
# 复杂查询组合
admin_or_staff = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True),
    User.is_active == True
).select_related("profile").all()

# 高级查询方法
users = await User.objects.distinct("department").annotate(
    full_name=func.concat(User.first_name, " ", User.last_name),
    post_count=func.count(User.posts)
).group_by("department").having(
    func.count() > 5
).all()

# 聚合查询
stats = await User.objects.aggregate(
    total_users=func.count(),
    avg_age=func.avg(User.age),
    max_age=func.max(User.age)
)

# 缓存控制
cached_users = await User.objects.filter(User.is_active == True).all()
live_users = await User.objects.no_cache().filter(User.status == "online").all()

# 查询执行方法
last_user = await User.objects.last()
earliest = await User.objects.earliest("created_at")
user_data = await User.objects.values("id", "username", "email")
usernames = await User.objects.values_list("username", flat=True)

# 批量操作
users_data = [
    {"name": f"User{i}", "age": 20 + i}
    for i in range(100)
]
await User.objects.bulk_create(users_data)

# 大数据集处理
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)

# 日期时间查询
signup_years = await User.objects.dates("created_at", "year", order="DESC")
login_hours = await User.objects.datetimes("last_login", "hour")

# 索引访问
first_user = await User.objects.order_by("created_at").get_item(0)
recent_users = await User.objects.order_by("-created_at").get_item(slice(0, 5))

# 会话管理
async with ctx_session() as session:
    users = await User.objects.using(session).filter(
        User.is_active == True
    ).all()
    
    for user in users:
        await User.objects.using(session).filter(
            User.id == user.id
        ).update(last_seen=datetime.now())
```
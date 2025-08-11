# SQLObjects Queries 设计说明文档

## 概述

SQLObjects Queries 模块提供查询构建系统，专注于核心查询功能和表达式组合。通过 Q 对象和统一的表达式支持，提供类型安全、高性能的查询构建体验。

## 核心特性

### 1. 统一表达式系统

支持多种表达式类型的统一处理：

```python
# Q 对象：包装 SQLAlchemy 表达式进行逻辑组合简化代码
(User.age >= 18) & (User.name.like('%admin%')
Q(User.age >= 18, User.name.like('%admin%')     # 等价 SQLAlchemy 的 & 表达式

# SQLAlchemy 表达式：直接字段操作
User.age >= 18
User.name.like('%admin%')
User.name.upper() == "JOHN"                     # 字段链式操作
User.birth_date.age_in_years() >= 18            # 增强功能

# 多表达式 Q 对象（AND 组合）
Q(User.age >= 18, User.is_active == True)
```

### 2. 链式查询构建

支持延迟执行的链式查询构建：

```python
# 链式构建，延迟执行
query = User.objects.filter(User.is_active == True)
query = query.filter(User.age >= 18)
query = query.order_by(User.name)
users = await query.all()  # 单次数据库查询

# 复杂查询链
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).select_related('profile').prefetch_related('posts').limit(10).all()
```

### 3. 智能会话管理

统一的会话参数支持，适应多数据库场景：

```python
# 使用默认会话
users = await User.objects.filter(User.age >= 18).all()

# 使用指定会话
users = await User.objects.filter(User.age >= 18).all(session=analytics_session)

# 链式调用中的会话传递
user = await User.objects.filter(
    User.is_active == True,
    session=main_session
).first()
```

## 模块架构

### 核心组件

- **Q 对象**：SQLAlchemy 表达式的逻辑组合器
- **QuerySet**：链式查询构建器和执行器
- **表达式处理器**：统一的表达式类型处理
- **会话管理器**：多数据库会话支持
- **子查询集成**：与 expressions 模块的子查询系统集成

### Q 对象系统

专注于 SQLAlchemy 表达式的逻辑组合：

```python
class Q:
    """Q 对象，专注于 SQLAlchemy 表达式的逻辑组合"""
    
    def __init__(self, *expressions: Any):
        self.expressions = expressions     # SQLAlchemy 表达式列表
        self.connector = "AND"             # 逻辑连接符
        self.negated = False               # 是否取反
        self.children: list[Q] = []        # 子 Q 对象
    
    def __and__(self, other) -> "Q":
        # AND 逻辑组合
    
    def __or__(self, other) -> "Q":
        # OR 逻辑组合
    
    def __invert__(self) -> "Q":
        # NOT 操作
```

### QuerySet 系统

提供链式查询接口和执行方法：

```python
class QuerySet(Generic[T]):
    """查询集合，提供链式查询接口"""
    
    # 查询构建方法（返回新的 QuerySet）
    def filter(self, *conditions, session=None) -> "QuerySet[T]"
    def exclude(self, *conditions, session=None) -> "QuerySet[T]"
    def order_by(self, *fields) -> "QuerySet[T]"
    def limit(self, count: int) -> "QuerySet[T]"
    def offset(self, count: int) -> "QuerySet[T]"
    def select_related(self, *relations) -> "QuerySet[T]"
    def prefetch_related(self, *relations) -> "QuerySet[T]"
    def distinct(self, *fields) -> "QuerySet[T]"
    def only(self, *fields) -> "QuerySet[T]"
    def defer(self, *fields) -> "QuerySet[T]"
    def annotate(self, **kwargs) -> "QuerySet[T]"
    def group_by(self, *fields) -> "QuerySet[T]"
    def having(self, *conditions) -> "QuerySet[T]"
    def options(self, *options) -> "QuerySet[T]"
    def join(self, target_model, on_condition=None, join_type="inner", isouter=False) -> "QuerySet[T]"
    def select_for_update(self, nowait=False, skip_locked=False) -> "QuerySet[T]"
    def none(self) -> "QuerySet[T]"
    def reverse(self) -> "QuerySet[T]"
    
    # 查询执行方法（执行数据库查询）
    async def all(self, session=None) -> list[T]
    async def get(self, *conditions, session=None) -> T
    async def first(self, session=None) -> T | None
    async def last(self, session=None) -> T | None
    async def earliest(self, *fields, session=None) -> T | None
    async def latest(self, *fields, session=None) -> T | None
    async def count(self, session=None) -> int
    async def exists(self, session=None) -> bool
    async def values(self, *fields, session=None) -> list[dict[str, Any]]
    async def values_list(self, *fields, flat=False, session=None) -> list[Any] | list[tuple[Any, ...]]
    async def aggregate(self, session=None, **kwargs) -> dict[str, Any]
    async def iterator(self, session=None, memory_cleanup_interval=1000) -> AsyncGenerator[T, None]
    async def get_item(self, key, session=None) -> T | list[T]
    async def dates(self, field: str, kind: str, order="ASC", session=None) -> list[Any]
    async def datetimes(self, field: str, kind: str, order="ASC", session=None) -> list[Any]
    async def explain(self, output=None, analyze=False, session=None, **options) -> dict[str, Any]  # 查询执行计划分析
    async def raw(self, sql: str, params=None, session=None) -> list[T]
    
    # 集合操作方法（Set Operations）
    async def union(self, *other_qs, all_=False, session=None) -> list[T]
    async def intersection(self, *other_qs, session=None) -> list[T]
    async def difference(self, *other_qs, session=None) -> list[T]
    
    # 数据操作方法（Data Operations）
    async def update(self, values: dict, session=None, commit=False) -> int
    async def delete(self, session=None, commit=False) -> int
    
    # 子查询方法（Subquery Methods）
    def subquery(self, name=None, query_type="auto") -> SubqueryExpression
```

### 与其他模块的集成

#### 与 expressions 模块的集成

```python
# 与 expressions 模块集成
from sqlobjects.expressions import func, and_, or_, not_
from sqlobjects.fields import FunctionResult

# 完整的查询生态系统
User.objects.filter(
    Q(User.is_active == True),            # queries 模块的 Q 对象
    User.age >= 18,                       # SQLAlchemy 表达式
    User.name.upper() == "ADMIN",         # fields 模块的链式调用
    func.length(User.bio) > 100           # expressions 模块的函数
)
```

#### 与 fields 模块的集成

```python
# 支持字段链式操作
from sqlobjects.fields import FunctionResult

# 表达式处理逻辑
def filter(self, *conditions, session=None):
    for condition in conditions:
        if isinstance(condition, Q):
            # Q 对象处理
        elif isinstance(condition, FunctionResult):
            # 字段链式操作结果处理
        else:
            # 直接的 SQLAlchemy 表达式
```

#### 模块职责分离

- **queries.py**: 负责查询构建、Q 对象逻辑组合、QuerySet 链式操作
- **expressions.py**: 负责函数系统、子查询支持、表达式处理
- **fields.py**: 负责字段定义、链式调用、类型系统
- **集成点**: 通过统一的表达式接口实现模块协作

## API 参考

### Q 对象

```python
# 基础用法
q1 = Q(User.name == "John")
q2 = Q(User.age >= 25)

# 多表达式（AND 组合）
q3 = Q(User.age >= 18, User.name.like('%admin%'))

# 逻辑组合
combined = q1 & q2                     # AND 组合
alternative = q1 | q2                  # OR 组合
negated = ~q1                          # NOT 操作

# 与 SQLAlchemy 表达式组合
mixed = Q(User.name.like('%admin%')) & (User.last_login >= func.now())
```

### QuerySet 方法

#### 查询构建方法

```python
# 过滤和排除
User.objects.filter(User.age >= 18, session=session)
User.objects.exclude(User.is_deleted == True)

# 排序和限制
User.objects.order_by(User.name, '-created_at')
User.objects.limit(10).offset(20)
User.objects.reverse()                      # 反向排序

# 关系加载
User.objects.select_related('profile')      # JOIN 预加载
User.objects.prefetch_related('posts')      # 分离查询预加载

# 字段选择
User.objects.only('id', 'username')         # 仅加载指定字段
User.objects.defer('large_field')           # 延迟加载字段
User.objects.distinct('department')         # 去重

# 注释和分组
User.objects.annotate(post_count=func.count(User.posts))
User.objects.group_by('department').having(func.count() > 5)

# 手动连接
User.objects.join(Profile, User.id == Profile.user_id)
User.objects.join(Profile, join_type="left")  # 左连接

# 锁定和特殊查询
User.objects.select_for_update()            # 行级锁
User.objects.select_for_update(nowait=True) # 不等待锁
User.objects.none()                         # 空结果集

# SQLAlchemy 选项
from sqlalchemy.orm import joinedload
User.objects.options(joinedload(User.profile))
```

#### 查询执行方法

```python
# 基础执行
await User.objects.all()                    # 获取所有结果
await User.objects.get(id=1)                # 获取单个对象
await User.objects.first()                  # 获取第一个对象
await User.objects.last()                   # 获取最后一个对象
await User.objects.earliest('created_at')   # 获取最早的对象
await User.objects.latest('created_at')     # 获取最新的对象
await User.objects.count()                  # 统计数量
await User.objects.exists()                 # 检查存在性

# 数据提取
await User.objects.values('id', 'username')
await User.objects.values_list('username', flat=True)
await User.objects.aggregate(avg_age=func.avg(User.age))

# 索引和切片访问
user = await User.objects.get_item(0)       # 获取第一个对象
users = await User.objects.get_item(slice(0, 10))  # 获取前10个对象

# 日期时间查询
dates = await User.objects.dates('created_at', 'month')  # 按月分组的日期
datetimes = await User.objects.datetimes('created_at', 'day')  # 按天分组的时间

# 查询执行计划分析
plan = await User.objects.explain()  # 基本执行计划
plan = await User.objects.explain(analyze=True)  # 实际执行并分析
plan = await User.objects.explain(output="json")  # JSON 格式输出
# PostgreSQL 高级选项
plan = await User.objects.explain(analyze=True, verbose=True, buffers=True)
# MySQL JSON 格式
plan = await User.objects.explain(output="json")
# SQLite 查询计划
plan = await User.objects.explain()  # 自动适配 SQLite 语法

# 原生SQL查询
users = await User.objects.raw("SELECT * FROM users WHERE age > :age", {"age": 18})

# 异步迭代器（大数据集处理）
async for user in User.objects.iterator():
    # 逐个处理用户对象
    process_user(user)

# 集合操作（在内存中处理，适用于中小型数据集）
active_users = User.objects.filter(is_active=True)
staff_users = User.objects.filter(is_staff=True)

# 并集：合并两个查询结果，去除重复
union_result = await active_users.union(staff_users)  # UNION 去重
union_all_result = await active_users.union(staff_users, all_=True)  # UNION ALL 保留重复

# 交集：获取同时存在于两个查询结果中的记录
intersection_result = await active_users.intersection(staff_users)

# 差集：获取在第一个查询中但不在第二个查询中的记录
difference_result = await active_users.difference(staff_users)

# 多个 QuerySet 的集合操作
admin_users = User.objects.filter(role="admin")
manager_users = User.objects.filter(role="manager")
all_privileged = await active_users.union(admin_users, manager_users)  # 多个并集
common_users = await active_users.intersection(staff_users, admin_users)  # 多个交集

# 批量操作
updated_count = await User.objects.filter(is_active=False).update(values={"status": "inactive"})
deleted_count = await User.objects.filter(is_deleted=True).delete()

# 子查询
avg_age_subq = User.objects.aggregate(avg_age=func.avg(User.age)).subquery()
high_earners = await User.objects.filter(User.salary > avg_age_subq).all()
```

## 使用指南

### 基础用法

```python
# 简单查询
active_users = await User.objects.filter(User.is_active == True).all()

# Q 对象逻辑组合
admin_or_staff = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).all()

# 多表达式 Q 对象（AND 组合）
active_adults = await User.objects.filter(
    Q(User.is_active == True, User.age >= 18)
).all()

# 排序和限制
recent_users = await User.objects.order_by('-created_at').limit(10).all()

# 字段选择
user_names = await User.objects.values_list('username', flat=True)
```

### 高级用法

```python
from sqlalchemy import and_, or_, not_
from sqlobjects.queries import Q

# 复杂条件组合（使用 Q 对象）
complex_users = await User.objects.filter(
    Q(User.role == "admin") & (
        Q(User.department == "IT") | Q(User.department == "Security")
    ),
    User.salary >= 50000,
    User.hire_date.year() >= 2020
).all()

# 使用 SQLAlchemy 原生语法
complex_users_sqlalchemy = await User.objects.filter(
    and_(
        User.role == "admin",
        or_(
            User.department == "IT",
            User.department == "Security"
        ),
        User.salary >= 50000,
        User.hire_date.year() >= 2020
    )
).all()

# 混合使用 Q 对象和 SQLAlchemy 语法
mixed_query = await User.objects.filter(
    Q(User.is_active == True),
    or_(
        and_(User.role == "admin", User.department == "IT"),
        and_(User.role == "manager", User.salary >= 80000)
    ),
    not_(User.is_deleted == True)
).all()

# 复杂逻辑组合
advanced_filter = await User.objects.filter(
    and_(
        or_(
            User.role.in_(["admin", "manager"]),
            User.permissions.contains("write")
        ),
        not_(User.status == "suspended"),
        User.created_at >= datetime(2023, 1, 1)
    )
).all()

# 关系查询
users_with_posts = await User.objects.select_related('profile').prefetch_related('posts').all()

# 聚合查询
user_stats = await User.objects.annotate(
    full_name=func.concat(User.first_name, " ", User.last_name),
    age_years=User.birth_date.age_in_years()
).all()

# 子查询集成（与 expressions 模块）
avg_salary_subq = User.objects.aggregate(avg_salary=func.avg(User.salary)).subquery()
high_earners = await User.objects.filter(User.salary > avg_salary_subq).all()

# 多数据库支持
main_users = await User.objects.filter(User.is_active == True).all(session=main_session)
analytics_users = await User.objects.filter(User.created_at >= last_month).all(session=analytics_session)

# 批量操作
updated_count = await User.objects.filter(
    User.last_login < inactive_threshold
).update(values={"is_active": False, "status": "inactive"})

deleted_count = await User.objects.filter(
    Q(User.is_deleted == True),
    User.deleted_at < permanent_delete_threshold
).delete()

# 事务控制
async with ctx_session() as session:
    users = await User.objects.filter(User.is_active == True).all(session=session)
    await User.objects.filter(User.id.in_([u.id for u in users])).update(
        values={"last_seen": datetime.now()}, 
        session=session
    )
    await session.commit()
```
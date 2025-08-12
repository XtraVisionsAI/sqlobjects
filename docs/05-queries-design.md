# SQLObjects 查询系统设计文档

## 概述

SQLObjects 查询模块提供查询构建系统，专注于核心查询功能和表达式组合。通过 Q 对象和统一表达式支持，提供类型安全、高性能的查询构建体验。

## 核心功能

### 1. 统一表达式系统

支持多种表达式类型的统一处理：

```python
# Q 对象：包装 SQLAlchemy 表达式进行逻辑组合
(User.age >= 18) & (User.name.like('%admin%'))
Q(User.age >= 18, User.name.like('%admin%'))     # 等价于 SQLAlchemy & 表达式

# SQLAlchemy 表达式：直接字段操作
User.age >= 18
User.name.like('%admin%')
User.name.upper() == "JOHN"                     # 字段链式操作
User.birth_date.age_in_years() >= 18            # 增强功能

# 多表达式 Q 对象（AND 组合）
Q(User.age >= 18, User.is_active == True)
```

### 2. 链式查询构建

支持惰性求值的链式查询构建：

```python
# 链式构建，惰性执行
query = User.objects.filter(User.is_active == True)
query = query.filter(User.age >= 18)
query = query.order_by(User.name)
users = await query.all()  # 单次数据库查询

# 复杂查询链
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).select_related('profile').prefetch_related('posts').limit(10).all()
```

### 3. 默认排序支持

智能默认排序应用，具有优先级系统：

```python
class User(ObjectModel):
    name: Column[str] = str_column()
    created_at: Column[datetime] = datetime_column()
    
    class Config:
        ordering = ["-created_at", "name"]  # 默认排序

# 自动应用默认排序
users = await User.objects.all()        # 使用默认排序
first_user = await User.objects.first() # 使用默认排序

# 覆盖默认排序
users = await User.objects.order_by("name").all()  # 自定义排序优先

# 跳过默认排序以提升性能
count = await User.objects.skip_default_ordering().count()
```

### 4. 智能会话管理

统一会话参数支持，适用于多数据库场景：

```python
# 使用默认会话
users = await User.objects.filter(User.age >= 18).all()

# 使用指定会话
users = await User.objects.using(analytics_session).filter(User.age >= 18).all()

# 链式调用中的会话传递
user = await User.objects.using(main_session).filter(
    User.is_active == True
).first()
```

## 模块架构

### 核心组件

- **Q 对象**：SQLAlchemy 表达式的逻辑组合器
- **QuerySet**：链式查询构建器和执行器
- **表达式处理器**：统一表达式类型处理
- **会话管理器**：多数据库会话支持
- **默认排序系统**：智能排序应用
- **子查询集成**：与 expressions 模块子查询系统集成

### Q 对象系统

专注于 SQLAlchemy 表达式的逻辑组合：

```python
class Q:
    """用于 SQLAlchemy 表达式逻辑组合的 Q 对象。"""
    
    def __init__(self, *expressions: Any):
        self.expressions = list(expressions)  # SQLAlchemy 表达式列表
        self.connector = "AND"                # 逻辑连接符
        self.negated = False                  # 是否取反
        self.children: list[Q] = []           # 子 Q 对象
    
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
    """提供链式查询接口的查询集类。"""
    
    def __init__(
        self,
        model: type[T],
        query: Select | None = None,
        db_or_session: str | AsyncSession | None = None,
        default_ordering: bool = True,
    ) -> None:
        self._db_or_session = db_or_session
        self._model = model
        self._query = query if query is not None else select(model)
        self._default_ordering = default_ordering
        
        # 如果没有提供查询且模型有默认排序，则应用默认排序
        if query is None and default_ordering and self._has_default_ordering():
            self._query = self._apply_default_ordering(self._query)
    
    @property
    def _session(self) -> AsyncSession:
        """获取有效的会话对象"""
        if self._db_or_session is None:
            return SessionContextManager.get_session()
        elif isinstance(self._db_or_session, str):
            return SessionContextManager.get_session(self._db_or_session)
        else:
            return self._db_or_session
```

### 默认排序系统

QuerySet 集成智能默认排序支持：

```python
class QuerySet(Generic[T]):
    # 默认排序内部方法
    def _has_default_ordering(self) -> bool:
        """检查模型是否配置了默认排序。"""
        return hasattr(self._model, "_default_ordering") and bool(self._model._default_ordering)
    
    def _apply_default_ordering(self, query: Select) -> Select:
        """从模型配置应用默认排序。"""
        if not self._has_default_ordering():
            return query
        
        order_clauses = self._build_order_clauses(self._model._default_ordering)
        if order_clauses:
            query = query.order_by(*order_clauses)
        return query
    
    def _ensure_ordering(self, query: Select) -> Select:
        """确保查询有排序，优先使用现有排序而非默认排序。"""
        # 优先级：显式排序 > 默认排序
        if not self._default_ordering:
            return query
        
        # 如果查询已有排序，保持现有排序
        if hasattr(query, "_order_by") and query._order_by:
            return query
        
        # 应用默认排序
        return self._apply_default_ordering(query)
    
    def skip_default_ordering(self) -> "QuerySet[T]":
        """返回跳过应用默认排序的 QuerySet。"""
        return QuerySet(self._model, self._query, self._db_or_session, default_ordering=False)
```

### 与其他模块的集成

#### 与 expressions 模块集成

```python
# 与 expressions 模块集成
from sqlobjects.expressions import func, and_, or_, not_
from sqlobjects.fields import FunctionResult

# 完整查询生态系统
User.objects.filter(
    Q(User.is_active == True),            # 来自 queries 模块的 Q 对象
    User.age >= 18,                       # SQLAlchemy 表达式
    User.name.upper() == "ADMIN",         # 来自 fields 模块的链式调用
    func.length(User.bio) > 100           # 来自 expressions 模块的函数
)
```

#### 与 fields 模块集成

```python
# 支持字段链式操作
from sqlobjects.fields import FunctionResult

# 表达式处理逻辑
def filter(self, *conditions):
    for condition in conditions:
        if isinstance(condition, Q):
            # Q 对象处理
        elif isinstance(condition, FunctionResult):
            # 字段链式操作结果处理
        else:
            # 直接 SQLAlchemy 表达式
```

#### 模块职责分离

- **queries.py**：负责查询构建、Q 对象逻辑组合、QuerySet 链式操作
- **expressions.py**：负责函数系统、子查询支持、表达式处理
- **fields.py**：负责字段定义、链式调用、类型系统
- **集成点**：通过统一表达式接口进行模块协作

## API 参考

### Q 对象

```python
# 基本用法
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
User.objects.filter(User.age >= 18)
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

# 注解和分组
User.objects.annotate(post_count=func.count(User.posts))
User.objects.group_by('department').having(func.count() > 5)

# 手动连接
User.objects.join(Profile, User.id == Profile.user_id)
User.objects.join(Profile, join_type="left")  # 左连接

# 锁定和特殊查询
User.objects.select_for_update()            # 行级锁定
User.objects.select_for_update(nowait=True) # 无等待锁定
User.objects.none()                         # 空结果集

# SQLAlchemy 选项
from sqlalchemy.orm import joinedload
User.objects.options(joinedload(User.profile))

# 默认排序控制
User.objects.skip_default_ordering()        # 跳过默认排序
User.objects.reverse()                      # 反向默认排序
```

#### 查询执行方法

```python
# 基本执行
await User.objects.all()                    # 获取所有结果
await User.objects.get(User.id == 1)        # 获取单个对象
await User.objects.first()                  # 获取第一个对象
await User.objects.last()                   # 获取最后一个对象
await User.objects.earliest('created_at')   # 获取最早对象
await User.objects.latest('created_at')     # 获取最新对象
await User.objects.count()                  # 计数
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
datetimes = await User.objects.datetimes('created_at', 'day')  # 按天分组的日期时间

# 查询执行计划分析
plan = await User.objects.explain()  # 基本执行计划
plan = await User.objects.explain(analyze=True)  # 实际执行和分析
plan = await User.objects.explain(output="json")  # JSON 格式输出

# 原生 SQL 查询
users = await User.objects.raw("SELECT * FROM users WHERE age > :age", {"age": 18})

# 异步迭代器（大数据集处理）
async for user in User.objects.iterator():
    # 逐个处理用户对象
    process_user(user)

# 集合操作（在内存中处理，适用于中小型数据集）
active_users = User.objects.filter(User.is_active == True)
staff_users = User.objects.filter(User.is_staff == True)

# 并集：合并两个查询结果，去除重复
union_result = await active_users.union(staff_users)  # UNION 去重
union_all_result = await active_users.union(staff_users, all_=True)  # UNION ALL 保留重复

# 交集：获取两个查询结果中都存在的记录
intersection_result = await active_users.intersection(staff_users)

# 差集：获取第一个查询中存在但第二个查询中不存在的记录
difference_result = await active_users.difference(staff_users)

# 批量操作
updated_count = await User.objects.filter(User.is_active == False).update({"status": "inactive"})
deleted_count = await User.objects.filter(User.is_deleted == True).delete()

# 子查询
avg_age_subq = User.objects.aggregate(avg_age=func.avg(User.age)).subquery()
high_earners = await User.objects.filter(User.salary > avg_age_subq).all()

# 使用指定会话
users = await User.objects.using(analytics_session).filter(User.age >= 18).all()
```

## 使用指南

### 基本用法

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

### 默认排序用法

```python
# 带默认排序的模型
class User(ObjectModel):
    name: Column[str] = str_column()
    created_at: Column[datetime] = datetime_column()
    
    class Config:
        ordering = ["-created_at", "name"]  # 默认排序

# 自动应用默认排序
users = await User.objects.all()        # 按 -created_at, name 排序
first_user = await User.objects.first() # 使用默认排序
last_user = await User.objects.last()   # 使用默认排序

# 覆盖默认排序
users = await User.objects.order_by("name").all()  # 自定义排序覆盖默认

# 跳过默认排序以提升性能
count = await User.objects.skip_default_ordering().count()  # 计数时无排序
users = await User.objects.skip_default_ordering().order_by("id").all()  # 仅自定义排序

# 反向默认排序
users = await User.objects.reverse().all()  # 反向默认排序

# 与默认排序链式调用
users = await User.objects.filter(User.is_active == True).all()  # 包含默认排序
users = await User.objects.filter(User.is_active == True).skip_default_ordering().all()  # 无默认排序
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

# 混合 Q 对象和 SQLAlchemy 语法
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
main_users = await User.objects.using(main_session).filter(User.is_active == True).all()
analytics_users = await User.objects.using(analytics_session).filter(User.created_at >= last_month).all()

# 批量操作
updated_count = await User.objects.filter(
    User.last_login < inactive_threshold
).update({"is_active": False, "status": "inactive"})

deleted_count = await User.objects.filter(
    Q(User.is_deleted == True),
    User.deleted_at < permanent_delete_threshold
).delete()

# 事务控制
async with ctx_session() as session:
    users = await User.objects.using(session).filter(User.is_active == True).all()
    await User.objects.using(session).filter(User.id.in_([u.id for u in users])).update(
        {"last_seen": datetime.now()}
    )
```

### 性能优化

```python
# 计数操作跳过默认排序
total_users = await User.objects.skip_default_ordering().count()

# 高效使用默认排序
recent_users = await User.objects.limit(10).all()  # 高效使用默认排序

# 需要时覆盖默认排序
alphabetical_users = await User.objects.order_by("name").all()  # 覆盖默认

# 与过滤结合
active_recent = await User.objects.filter(User.is_active == True).limit(5).all()  # 默认排序 + 过滤

# 带排序控制的复杂查询
complex_query = await User.objects.filter(
    Q(User.department == "IT") | Q(User.role == "admin")
).skip_default_ordering().order_by("salary", "-hire_date").all()
```
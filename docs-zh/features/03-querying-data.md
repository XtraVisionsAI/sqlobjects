# 查询和过滤数据

## 概述

SQLObjects 提供了 Django 风格的查询 API，支持链式调用方法、用于复杂条件的 Q 对象，以及强大的数据库操作表达式支持。

## 快速开始

### 基础查询

```python
# 获取所有用户
users = await User.objects.all()

# 按条件过滤
active_users = await User.objects.filter(User.is_active == True).all()

# 获取单个对象
user = await User.objects.get(User.username == "john")

# 检查是否存在
exists = await User.objects.filter(User.email == "john@example.com").exists()
```

### 查询链式调用

```python
# 链接多个条件
users = await (User.objects
    .filter(User.is_active == True)
    .filter(User.age >= 18)
    .order_by("-created_at")
    .limit(10)
    .all())
```

## 过滤

### 基础条件

```python
# 相等条件
users = await User.objects.filter(User.username == "john").all()

# 比较操作符
adults = await User.objects.filter(User.age >= 18).all()
recent = await User.objects.filter(User.created_at > datetime.now(timezone.utc) - timedelta(days=7)).all()

# 字符串操作
users = await User.objects.filter(User.username.like("%admin%")).all()
users = await User.objects.filter(User.email.ilike("%GMAIL%")).all()  # 不区分大小写
```

### 多条件查询

```python
# AND 条件（默认）
users = await User.objects.filter(
    User.is_active == True,
    User.age >= 18,
    User.email.like("%@company.com")
).all()

# 排除条件
users = await User.objects.exclude(User.is_deleted == True).all()
```

### 使用 Q 对象进行复杂逻辑查询

```python
from sqlobjects import Q

# OR 条件
users = await User.objects.filter(
    Q(User.role == "admin") | Q(User.is_staff == True)
).all()

# 复杂组合
users = await User.objects.filter(
    Q(User.age >= 18) & (Q(User.role == "admin") | Q(User.is_staff == True))
).all()

# 否定条件
users = await User.objects.filter(~Q(User.is_deleted == True)).all()
```

## 排序和限制

### 排序

```python
# 单字段排序
users = await User.objects.order_by("username").all()
users = await User.objects.order_by("-created_at").all()  # 降序

# 多字段排序
users = await User.objects.order_by("department", "-salary").all()

# 跳过默认排序以提高性能
count = await User.objects.skip_default_ordering().count()
```

### 分页

```python
# 限制和偏移
users = await User.objects.limit(10).all()
users = await User.objects.offset(20).limit(10).all()

# 索引和切片访问
first_user = await User.objects.get_item(0)  # 第一个用户
last_user = await User.objects.get_item(-1)  # 最后一个用户
users = await User.objects.get_item(slice(0, 10))  # 前 10 个
users = await User.objects.get_item(slice(20, 30))  # 第 20-30 个
```

## 字段选择

### 指定字段

```python
# 只加载指定字段
users = await User.objects.only("id", "username", "email").all()

# 排除重字段
users = await User.objects.defer("large_text_field", "binary_data").all()

# 以字典形式返回值
user_data = await User.objects.values("id", "username", "email").all()
# 结果: [{"id": 1, "username": "john", "email": "john@example.com"}, ...]

# 以元组形式返回值
usernames = await User.objects.values_list("username", flat=True).all()
# 结果: ["john", "alice", "bob", ...]
```

## 聚合

### 基础聚合

```python
from sqlobjects.expressions import func

# 计数
user_count = await User.objects.count()
active_count = await User.objects.filter(User.is_active == True).count()

# 其他聚合函数
stats = await User.objects.aggregate(
    total_users=func.count(),
    avg_age=func.avg(User.age),
    max_age=func.max(User.age),
    min_age=func.min(User.age)
)
# 结果: {"total_users": 100, "avg_age": 32.5, "max_age": 65, "min_age": 18}
```

### 注解

```python
# 添加计算字段
users = await User.objects.annotate(
    full_name=func.concat(User.first_name, " ", User.last_name),
    post_count=func.count(User.posts),
    latest_post=func.max(User.posts.created_at)
).all()

# 在过滤中使用注解
active_posters = await User.objects.annotate(
    post_count=func.count(User.posts)
).filter(
    User.post_count > 5
).all()
```

## 字段选择控制

### 字段加载管理

```python
# 只加载指定字段
users = await User.objects.only("id", "username", "email").all()

# 延迟加载重字段
live_users = await User.objects.defer("bio", "profile_image").all()

# 结合过滤和字段选择
active_users = await User.objects.filter(
    User.is_active == True
).only("id", "username").all()
```

## 高级查询方法

### 查询构建方法

```python
# 使用计算字段进行注解
users = await User.objects.annotate(
    full_name=func.concat(User.first_name, " ", User.last_name),
    post_count=func.count(User.posts)
).all()

# 分组聚合 —— 每组一行的结果来自 values 模式，而不是 aggregate()
dept_stats = await User.objects.annotate(
    dept_count=func.count(),
    avg_salary=func.avg(User.salary)
).group_by("department").having(
    func.count() > 5
).values("department", "dept_count", "avg_salary")

# 复杂查询的手动连接（使用 Model 类 - 推荐）
posts = await Post.objects.join(
    User, 
    Post.author_id == User.id,
    join_type="inner"
).all()

# 左连接和外连接
posts = await Post.objects.leftjoin(
    Comment,
    Comment.post_id == Post.id
).all()

posts = await Post.objects.outerjoin(
    Tag,
    Tag.post_id == Post.id
).all()

# 行级锁定
users = await User.objects.select_for_update(
    nowait=True, 
    skip_locked=False
).filter(User.balance > 0).all()

users = await User.objects.select_for_share(
    nowait=False, 
    skip_locked=True
).filter(User.is_active == True).all()

# 额外的 SQL 片段
users = await User.objects.extra(
    columns={"full_name": "first_name || ' ' || last_name"},
    where=["age > %s"],
    params=[18]
).all()

# 跳过默认排序以提高性能
count = await User.objects.skip_default_ordering().count()

# 子查询创建
avg_age = User.objects.aggregate(
    avg_age=func.avg(User.age)
).subquery(query_type="scalar")

active_users = User.objects.filter(
    User.is_active == True
).subquery("active_users")
```

### 分组和聚合

按组聚合使用 **values 模式**：用 `annotate()` 声明聚合表达式，用 `group_by()`
分组，再在 `values()` 中列出分组列和聚合别名——每组返回一个 dict。
`aggregate()` 只做单行聚合，与 `group_by()` 组合会抛出 `QueryError`。

```python
# 带有 having 子句的分组
dept_stats = await User.objects.annotate(
    dept_count=func.count(),
    avg_salary=func.avg(User.salary)
).group_by("department").having(
    func.count() > 5
).values("department", "dept_count", "avg_salary")
# [{"department": "sales", "dept_count": 12, "avg_salary": 52000.0}, ...]

# 按表达式复杂分组：先用 annotate 给表达式起别名，values() 才能与聚合值一起选取
monthly_stats = await Sale.objects.annotate(
    year=func.extract("year", Sale.created_at),
    month=func.extract("month", Sale.created_at),
    total_sales=func.sum(Sale.amount),
    avg_sale=func.avg(Sale.amount)
).group_by(
    func.extract("year", Sale.created_at),
    func.extract("month", Sale.created_at)
).values("year", "month", "total_sales", "avg_sale")
```

### 手动连接和锁定

```python
# 连接类型
# 内连接（默认）- 使用 Model 类（推荐）
posts = await Post.objects.join(
    User,
    Post.author_id == User.id
).all()

# 左连接
posts = await Post.objects.leftjoin(
    Comment,
    Comment.post_id == Post.id
).all()

# 外连接
posts = await Post.objects.outerjoin(
    Tag,
    Tag.post_id == Post.id
).all()

# 多表连接
posts = await Post.objects.join(
    User.__table__, Post.author_id == User.id
).leftjoin(
    Comment.__table__, Comment.post_id == Post.id
).all()

# 复杂连接条件
posts = await Post.objects.join(
    User.__table__,
    and_(
        Post.author_id == User.id,
        User.is_active == True,
        User.created_at < Post.created_at
    )
).all()

# 悲观锁
# FOR UPDATE 锁定
users = await User.objects.select_for_update().filter(
    User.balance > 0
).all()

# FOR UPDATE with NOWAIT
users = await User.objects.select_for_update(nowait=True).filter(
    User.account_status == "active"
).all()

# FOR UPDATE with SKIP LOCKED
users = await User.objects.select_for_update(skip_locked=True).filter(
    User.processing_status == "pending"
).all()

# 共享锁
# FOR SHARE 锁定
users = await User.objects.select_for_share().filter(
    User.is_active == True
).all()

# 带选项的 FOR SHARE
users = await User.objects.select_for_share(
    nowait=True,
    skip_locked=True
).filter(User.role == "admin").all()
```

## 查询执行方法

### 其他执行方法

```python
# 检查存在性
exists = await User.objects.filter(User.email == "test@example.com").exists()

# 批量删除匹配的行。cascade 策略控制关联行的处理方式：
# "auto"（默认）根据模型的关系和删除信号选择策略，"full" 逐实例执行
# ORM 级联，"fast" 执行最小化的外键级联，"none" 发出直接的 SQL 删除。
deleted = await User.objects.filter(User.is_active == False).delete()
deleted = await User.objects.filter(User.is_active == False).delete(cascade="none")

# 原生 SQL 执行
users = await User.objects.raw(
    "SELECT * FROM users WHERE age > :age",
    {"age": 18}
)

# 带排序的第一个和最后一个
first_user = await User.objects.order_by("created_at").first()
last_user = await User.objects.order_by("created_at").last()

# 按指定字段的最早和最晚
earliest = await User.objects.earliest("created_at")
latest = await User.objects.latest("updated_at")

# 多字段的最早/最晚
earliest = await User.objects.earliest("created_at", "id")
latest = await User.objects.latest("updated_at", "username")

# 以字典形式返回值
user_data = await User.objects.values("id", "username", "email")
# 结果: [{"id": 1, "username": "john", "email": "john@example.com"}]

# 以元组或平坦列表形式返回值
user_tuples = await User.objects.values_list("username", "email")
# 结果: [("john", "john@example.com"), ("alice", "alice@example.com")]

usernames = await User.objects.values_list("username", flat=True)
# 结果: ["john", "alice", "bob"]

# 日期和日期时间提取
signup_years = await User.objects.dates("created_at", "year", order="DESC")
# 结果: [date(2023, 1, 1), date(2022, 1, 1)]

login_hours = await User.objects.datetimes("last_login", "hour", order="ASC")
# 结果: [datetime(2023, 12, 1, 10, 0), datetime(2023, 12, 1, 11, 0)]

# 索引和切片访问
first_user = await User.objects.get_item(0)
last_user = await User.objects.get_item(-1)
users_slice = await User.objects.get_item(slice(10, 20))

# 内存高效处理的迭代器
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)
```

### 原生 SQL 查询

```python
# 使用参数执行原生 SQL
users = await User.objects.raw(
    "SELECT * FROM users WHERE age > :age AND department = :dept",
    {"age": 18, "dept": "engineering"}
)

# 复杂原生查询
results = await User.objects.raw(
    """
    SELECT u.*, COUNT(p.id) as post_count
    FROM users u
    LEFT JOIN posts p ON u.id = p.author_id
    WHERE u.is_active = true
    GROUP BY u.id
    HAVING COUNT(p.id) > :min_posts
    """,
    {"min_posts": 5}
)
```

## 高级查询

### 子查询

```python
# 标量子查询用于单值比较
avg_salary = User.objects.aggregate(
    avg_salary=func.avg(User.salary)
).subquery(query_type="scalar")

high_earners = await User.objects.filter(
    User.salary > avg_salary
).all()

# 多个标量子查询
max_age = User.objects.aggregate(max_age=func.max(User.age)).subquery(query_type="scalar")
min_age = User.objects.aggregate(min_age=func.min(User.age)).subquery(query_type="scalar")

users = await User.objects.filter(
    (User.age == max_age) | (User.age == min_age)
).all()

# EXISTS 子查询用于布尔条件
has_posts = Post.objects.filter(
    Post.author_id == User.id
).subquery(query_type="exists")

authors = await User.objects.filter(has_posts).all()

# 复杂 EXISTS 条件
has_recent_posts = Post.objects.filter(
    Post.author_id == User.id,
    Post.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
).subquery(query_type="exists")

active_authors = await User.objects.filter(has_recent_posts).all()

# 表子查询用于复杂连接
active_users = User.objects.filter(
    User.is_active == True
).subquery("active_users")

posts = await Post.objects.join(
    active_users, 
    Post.author_id == active_users.c.id
).all()

# 复杂表子查询
top_users = User.objects.annotate(
    post_count=func.count(User.posts)
).filter(
    User.post_count > 10
).subquery("top_users")

popular_posts = await Post.objects.join(
    top_users,
    Post.author_id == top_users.c.id
).all()
```

### 复杂聚合

```python
# 部门统计（每组一行 → values 模式）
dept_stats = await User.objects.annotate(
    user_count=func.count(),
    avg_salary=func.avg(User.salary),
    max_salary=func.max(User.salary)
).group_by("department").values("department", "user_count", "avg_salary", "max_salary")

# 条件聚合
stats = await User.objects.aggregate(
    total_users=func.count(),
    active_users=func.sum(func.case([(User.is_active == True, 1)], else_=0)),
    avg_age=func.avg(User.age)
)
```

### 原生 SQL

```python
# 原生 SQL 查询 - raw() 是异步方法，返回实例列表
users = await User.objects.raw(
    "SELECT * FROM users WHERE age > :min_age AND created_at > :date",
    {"min_age": 18, "date": datetime.now(timezone.utc) - timedelta(days=30)}
)

# 原生表达式
users = await User.objects.annotate(
    custom_field=text("CASE WHEN age >= 18 THEN 'adult' ELSE 'minor' END")
).all()

# func.raw() 按名称调用任意 SQL 函数，参数既可以是普通值，也可以是
# SQLAlchemy 表达式（列/其他函数表达式），表达式会作为 SQL 片段透传，
# 而非绑定参数。
from sqlobjects.expressions import func

docs = await Document.objects.annotate(
    rank=func.raw("ts_rank", Document.content_vector, func.raw("to_tsvector", Document.body))
).order_by("-rank").all()
```

## 关联查询

### 加载相关数据

```python
# select_related（JOIN）- 使用字符串字段名
users = await User.objects.select_related("profile").all()

# prefetch_related（单独查询）- 使用字符串字段名
users = await User.objects.prefetch_related("posts").all()

# 多个关联
users = await User.objects.select_related("profile").prefetch_related("posts", "groups").all()
```

### 按相关字段过滤

```python
# 按相关字段过滤
users = await User.objects.filter(User.profile.bio.like("%developer%")).all()
users = await User.objects.filter(User.posts.title.like("%python%")).all()

# 统计相关对象
users = await User.objects.annotate(
    post_count=func.count(User.posts)
).filter(
    User.post_count > 5
).all()
```

## 性能优化

### 高效查询

```python
# 使用 exists() 而不是 count() 进行布尔检查
has_users = await User.objects.filter(User.is_active == True).exists()

# 对大数据集使用迭代器
async for user in User.objects.filter(User.is_active == True).iterator():
    await process_user(user)

# 使用自定义块大小的批处理
async for user in User.objects.iterator(
    chunk_size=1000
):
    await process_user(user)

# 对计数操作跳过默认排序
count = await User.objects.skip_default_ordering().count()
```

### 窗口函数

```python
from sqlobjects.expressions import func

# 行号
users = await User.objects.annotate(
    row_num=func.row_number().over(order_by=[User.created_at])
).all()

# 分区内排名
users = await User.objects.annotate(
    dept_rank=func.rank().over(
        partition_by=[User.department],
        order_by=[(User.salary, 'desc')]
    )
).all()

# 密集排名（排名无间隔）
users = await User.objects.annotate(
    dense_rank=func.dense_rank().over(order_by=[(User.score, 'desc')])
).all()

# LAG/LEAD 访问相邻行
users = await User.objects.annotate(
    prev_salary=func.lag(User.salary, 1).over(order_by=[User.created_at]),
    next_salary=func.lead(User.salary, 1).over(order_by=[User.created_at])
).all()

# FIRST_VALUE / LAST_VALUE
users = await User.objects.annotate(
    highest_salary=func.first_value(User.salary).over(
        partition_by=[User.department],
        order_by=[(User.salary, 'desc')]
    )
).all()

# NTILE - 将行分为 N 个桶
users = await User.objects.annotate(
    quartile=func.ntile(4).over(order_by=[User.salary])
).all()
```

可用的窗口函数：`row_number()`、`rank()`、`dense_rank()`、`percent_rank()`、`ntile(n)`、`lag(col, offset, default)`、`lead(col, offset, default)`、`first_value(col)`、`last_value(col)`、`nth_value(col, n)`。

### CTE（公共表表达式）

```python
# 基本 CTE
adults = User.objects.filter(User.age >= 18).cte("adults")
result = await User.objects.with_cte(adults).filter(
    adults.c.age < 30
).all()

# 多个 CTE
active = User.objects.filter(User.is_active == True).cte("active")
recent = User.objects.filter(
    User.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
).cte("recent")
result = await User.objects.with_cte(active, recent).all()

# 递归 CTE（例如组织层级结构）
base = Employee.objects.filter(
    Employee.manager_id.is_(None)
).cte("hierarchy", recursive=True)
recursive_part = Employee.objects.join(
    base, Employee.manager_id == base.c.id
)
hierarchy = base.union_all(recursive_part)
all_employees = await Employee.objects.with_cte(hierarchy).all()
```

### 查询分析

终端查询表达式（例如 `.all()` 返回的表达式）暴露一个可等待的 `explain()`，以字符串形式返回执行计划。它接受 `analyze` 和 `verbose` 标志；没有 JSON/`output=` 选项。

```python
# 解释查询执行（以字符串形式返回计划）
plan = await User.objects.filter(User.age >= 18).all().explain(analyze=True)
print(plan)

# 更详细的详尽计划
plan = await User.objects.filter(User.age >= 18).all().explain(analyze=True, verbose=True)
print(plan)
```

### QuerySet 快捷方法

ObjectsManager 提供对所有 QuerySet 方法的直接访问：

```python
# 去重操作
unique_departments = await User.objects.distinct("department").all()
all_distinct = await User.objects.distinct().all()

# 排除过滤
non_deleted = await User.objects.exclude(User.is_deleted == True).all()

# 排序
users = await User.objects.order_by("username", "-created_at").all()

# 分页
page_users = await User.objects.limit(10).offset(20).all()

# 字段选择
users = await User.objects.only("id", "username").all()
users = await User.objects.defer("large_field").all()

# 空查询集
empty = await User.objects.none().all()  # 总是返回 []

# 反转排序
users = await User.objects.order_by("created_at").reverse().all()

# 关联加载
users = await User.objects.select_related("profile").all()
users = await User.objects.prefetch_related("posts").all()

# 使用自定义查询集的高级预取
users = await User.objects.prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
    ).order_by("-created_at").limit(5)
).all()
```

## 日期和时间查询

### 日期提取

```python
# 兼容多数据库的日期部分提取
users_by_year = await User.objects.dates("created_at", "year", order="DESC")
users_by_month = await User.objects.dates("created_at", "month", order="ASC")
users_by_day = await User.objects.dates("created_at", "day")

# 带精度级别的日期时间提取
login_times = await User.objects.datetimes("last_login", "hour", order="ASC")
minute_logins = await User.objects.datetimes("last_login", "minute")
second_logins = await User.objects.datetimes("last_login", "second")

# 支持的精度级别：
# dates(): "year", "month", "day"
# datetimes(): "year", "month", "day", "hour", "minute", "second"
```

### 日期过滤

```python
from datetime import datetime, timedelta, timezone

# 最近记录
recent_users = await User.objects.filter(
    User.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
).all()

# 日期范围
this_month_users = await User.objects.filter(
    User.created_at >= datetime.now(timezone.utc).replace(day=1),
    User.created_at < datetime.now(timezone.utc).replace(day=1) + timedelta(days=32)
).all()

# 在过滤中提取日期部分
users_2023 = await User.objects.filter(
    func.extract("year", User.created_at) == 2023
).all()
```

## 最佳实践

### 查询优化

```python
# 对外键使用 select_related
users = await User.objects.select_related("department").all()

# 对反向外键和多对多关系使用 prefetch_related
users = await User.objects.prefetch_related("posts", "groups").all()

# 为复杂关联结合两者
users = await User.objects.select_related("department").prefetch_related("posts").all()
```

### 错误处理

```python
from sqlobjects.exceptions import DoesNotExist, MultipleObjectsReturned

try:
    user = await User.objects.get(User.username == "john")
except DoesNotExist:
    # 处理用户未找到
    user = None
except MultipleObjectsReturned:
    # 处理找到多个用户
    user = await User.objects.filter(User.username == "john").first()
```

### 内存管理

```python
# 对大结果集，使用迭代器
async for user in User.objects.filter(User.is_active == True).iterator():
    # 一次处理一个用户
    await process_user(user)

# 或使用分页
page_size = 100
offset = 0
while True:
    users = await User.objects.offset(offset).limit(page_size).all()
    if not users:
        break
  
    for user in users:
        await process_user(user)
  
    offset += page_size
```
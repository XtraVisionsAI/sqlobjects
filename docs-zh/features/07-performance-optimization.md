# 性能优化

## 概览

SQLObjects 提供了全面的性能优化功能，包括批量操作、查询优化、内存管理和连接池，用于构建高性能数据库应用程序。

## 快速开始

### 基本优化

```python
# 对大型数据集使用批量操作
users_data = [{"username": f"user{i}", "email": f"user{i}@example.com"} for i in range(1000)]
await User.objects.bulk_create(users_data, batch_size=500)

# 不需要时跳过默认排序
count = await User.objects.skip_default_ordering().count()

# 对外键关系使用 select_related
posts = await Post.objects.select_related("author").all()

# 对大型结果集使用迭代器
async for user in User.objects.iterator():
    await process_user(user)

# 使用字段选择优化
users = await User.objects.only("id", "username", "email").all()  # 只加载必要字段
live_data = await User.objects.defer("bio", "profile_image").all()  # 延迟加载重字段
```

## 批量操作

### 批量创建

```python
# 标准批量创建
users_data = [
    {"username": "user1", "email": "user1@example.com"},
    {"username": "user2", "email": "user2@example.com"},
    # ... 数千条记录
]

# 批次处理以提高内存效率
users = await User.objects.bulk_create(users_data, batch_size=1000)

# 数据库特定批次大小
postgresql_batch = 1000  # PostgreSQL 能很好地处理较大批次
mysql_batch = 500        # MySQL 首选较小批次
sqlite_batch = 100       # SQLite 有较低的限制

await User.objects.bulk_create(
    users_data, 
    batch_size=postgresql_batch if db_type == "postgresql" else mysql_batch
)
```

### 批量更新

```python
# 标准更新（中等性能）
affected = await User.objects.filter(
    User.is_active == False
).update(status="inactive")

# 真正的批量更新（对大型数据集快 10-100 倍）
mappings = [
    {"id": 1, "status": "active", "last_seen": datetime.now()},
    {"id": 2, "status": "inactive", "last_seen": datetime.now()},
    # ... 数千条记录
]

affected = await User.objects.bulk_update(
    mappings,
    match_fields=["id"],
    batch_size=1000
)

# 多字段匹配
mappings = [
    {"username": "alice", "email": "alice@old.com", "new_email": "alice@new.com"},
    {"username": "bob", "email": "bob@old.com", "new_email": "bob@new.com"}
]

affected = await User.objects.bulk_update(
    mappings,
    match_fields=["username", "email"]
)
```

### 批量删除

```python
# 基于条件的标准删除
deleted = await User.objects.filter(
    User.is_active == False,
    User.last_login < datetime.now() - timedelta(days=365)
).delete()

# 真正的批量删除（对大型 ID 列表快 10-100 倍）
user_ids = [1, 2, 3, 4, 5]  # 数千个 ID
deleted = await User.objects.bulk_delete(
    user_ids,
    id_field="id",
    batch_size=1000
)

# 使用自定义字段批量删除
usernames = ["inactive_user1", "inactive_user2", "inactive_user3"]
deleted = await User.objects.bulk_delete(
    usernames,
    id_field="username",
    batch_size=500
)
```

## 字段和关系缓存

### 字段元数据缓存

```python
# 字段信息在类级别自动缓存
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    bio: Column[str] = StringColumn(type="text", deferred=True)
  
    # 字段缓存在模型创建时自动构建
    # 包括常规字段、延迟字段和关系字段的分类

# 访问缓存的字段信息
field_cache = User._get_field_cache()
deferred_fields = field_cache.get("deferred_fields", set())
relationship_fields = field_cache.get("relationship_fields", set())
```

### 关系对象缓存

```python
# 相关对象在首次访问后被缓存
user = await User.objects.get(User.id == 1)
posts = await user.posts  # 加载并缓存相关文章
posts_again = await user.posts  # 返回缓存的文章

# 单一关系缓存
post = await Post.objects.get(Post.id == 1)
author = await post.author  # 加载并缓存作者
author_again = await post.author  # 返回缓存的作者
```

## 查询优化

### 默认排序控制

```python
# 在计数操作中跳过默认排序（显著的性能提升）
count = await User.objects.skip_default_ordering().count()

# 应用自定义排序时跳过
users = await User.objects.skip_default_ordering().order_by("username").all()

# 只在需要时使用默认排序
recent_users = await User.objects.limit(10).all()  # 使用默认排序
```

### 关系加载

```python
# 高效的关系加载
# 对外键使用 select_related（JOIN）
posts = await Post.objects.select_related("author", "category").all()

# 对反向关系使用 prefetch_related（独立查询）
users = await User.objects.prefetch_related("posts", "comments").all()

# 使用自定义 QuerySets 的高级预获取（并发执行）
users = await User.objects.prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=30)
    ).order_by('-created_at').limit(10),
    popular_posts=Post.objects.filter(Post.view_count > 1000)
                             .order_by('-view_count')
                             .limit(5)
).all()  # 所有预获取查询并发执行

# 结合两种策略
posts = await Post.objects.select_related("author").prefetch_related("tags").all()

# 表达式语法（推荐）
posts = await Post.objects.select_related(Post.author).prefetch_related(Post.tags).all()
```

### 字段选择

```python
# 只加载必要的字段
users = await User.objects.only("id", "username", "email").all()

# 排除重字段
users = await User.objects.defer("bio", "profile_image").all()

# 关系的选择性加载
posts = await Post.objects.select_related("author").only(
    "title", "content", "author__username"
).all()
```

### 子查询优化

```python
# 使用适当的子查询类型
# 对单值比较使用标量子查询（最高效）
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery(query_type="scalar")
older_users = await User.objects.filter(User.age > avg_age).all()

# 对布尔条件使用 EXISTS 子查询（通常比 IN 更高效）
has_posts = Post.objects.filter(Post.author_id == User.id).subquery(query_type="exists")
authors = await User.objects.filter(has_posts).all()

# 对复杂 JOIN 使用表子查询
active_users = User.objects.filter(User.is_active == True).subquery("active")
posts = await Post.objects.join(active_users, Post.author_id == active_users.c.id).all()
```

## 内存管理

### 大型数据集的迭代器

```python
# 处理大型数据集而不将所有内容加载到内存中
async for user in User.objects.filter(User.is_active == True).iterator():
    await process_user(user)

# 自定义块大小
async for user in User.objects.iterator(
    chunk_size=1000
):
    await process_user(user)

# 带过滤和排序的迭代器
async for post in Post.objects.filter(
    Post.created_at >= datetime.now() - timedelta(days=30)
).order_by("-created_at").iterator():
    await process_post(post)

# 内存高效的批处理
async def process_large_dataset():
    processed_count = 0
  
    async for record in LargeTable.objects.iterator(chunk_size=1000):
        await process_record(record)
        processed_count += 1
      
        # 进度报告
        if processed_count % 10000 == 0:
            print(f"已处理 {processed_count} 条记录")
```

### 分页策略

```python
# 基于偏移量的分页（简单但对大偏移量可能很慢）
page_size = 100
offset = 0

while True:
    users = await User.objects.offset(offset).limit(page_size).all()
    if not users:
        break
  
    for user in users:
        await process_user(user)
  
    offset += page_size

# 基于游标的分页（对大型数据集更高效）
last_id = 0
page_size = 100

while True:
    users = await User.objects.filter(
        User.id > last_id
    ).order_by("id").limit(page_size).all()
  
    if not users:
        break
  
    for user in users:
        await process_user(user)
  
    last_id = users[-1].id
```

### 切片访问

```python
# 高效的切片访问
first_10 = await User.objects.get_item(slice(0, 10))
next_10 = await User.objects.get_item(slice(10, 20))

# 单项访问
first_user = await User.objects.get_item(0)
fifth_user = await User.objects.get_item(4)
```

## 数据库连接优化

### 连接池配置

```python
from sqlobjects.database import DatabaseConfig

# 优化的连接池设置
config = DatabaseConfig(
    "postgresql://user:pass@localhost/db",
    pool_size=20,           # 基础连接池大小
    max_overflow=30,        # 高峰负载时的额外连接
    pool_timeout=30,        # 连接的最大等待时间
    pool_recycle=3600,      # 每小时回收连接
    pool_pre_ping=True,     # 使用前验证连接
    echo=False              # 生产环境中禁用 SQL 日志
)

db = await init_db(config.url, **config.engine_kwargs)
```

### 会话管理模式

```python
# 为您的用例选择适当的会话模式

# 模式 1：ContextVar 继承（最适合统一事务）
async with ctx_session() as session:
    tasks = [asyncio.create_task(process_batch(batch)) for batch in batches]
    await asyncio.gather(*tasks)  # 所有任务共享同一会话

# 模式 2：独立上下文（最适合容错）
tasks = [
    asyncio.create_task(process_batch(batch), context=contextvars.copy_context())
    for batch in batches
]
await asyncio.gather(*tasks, return_exceptions=True)

# 模式 3：显式传递（最适合复杂逻辑）
async with ctx_session() as session:
    tasks = [asyncio.create_task(process_batch(batch, session)) for batch in batches]
    await asyncio.gather(*tasks)
```

### 连接生命周期管理

```python
# 使用自动故障转移的优雅关闭
await close_db("primary", auto_default=True)  # 自动切换到备份

# 健康检查
async def check_database_health():
    try:
        count = await User.objects.count()
        return {"status": "healthy", "user_count": count}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

## 高级优化技术

### 查询分析

```python
# 分析查询性能。终端查询表达式（例如来自 .all()）暴露一个可等待的
# explain()，以字符串形式返回计划。它接受 analyze 和 verbose 标志；
# 没有 JSON/output= 选项。
plan = await User.objects.filter(User.age >= 18).all().explain(analyze=True)
print(plan)

# 更详细的详尽计划
plan = await User.objects.filter(User.age >= 18).all().explain(analyze=True, verbose=True)

# 识别慢查询
import time

start_time = time.time()
users = await User.objects.filter(User.is_active == True).all()
execution_time = time.time() - start_time

if execution_time > 1.0:  # 记录慢查询
    logger.warning(f"检测到慢查询: {execution_time:.2f}s")
```

### 数据库函数使用

```python
from sqlobjects.expressions import func

# 使用数据库函数进行计算（比 Python 更高效）
users = await User.objects.annotate(
    full_name=func.concat(User.first_name, " ", User.last_name),
    age_years=func.extract("year", func.age(User.birth_date))
).all()

# 数据库中的聚合
stats = await Order.objects.aggregate(
    total_amount=func.sum(Order.amount),
    avg_amount=func.avg(Order.amount),
    order_count=func.count(),
    max_order_date=func.max(Order.created_at)
)
```

### 批处理模式

```python
# 高效的批处理
async def process_users_in_batches(batch_size=1000):
    offset = 0
  
    while True:
        # 处理批次
        users = await User.objects.offset(offset).limit(batch_size).all()
        if not users:
            break
      
        # 批量操作
        updates = []
        for user in users:
            # 处理用户
            processed_data = await process_user_data(user)
            updates.append({"id": user.id, **processed_data})
      
        # 批量更新结果
        if updates:
            await User.objects.bulk_update(updates, match_fields=["id"])
      
        offset += batch_size

# 并行批处理
async def parallel_batch_processing(user_ids: list[int], batch_size=100):
    batches = [user_ids[i:i + batch_size] for i in range(0, len(user_ids), batch_size)]
  
    async def process_batch(batch_ids):
        users = await User.objects.filter(User.id.in_(batch_ids)).all()
        # 批处理用户
        return await process_user_batch(users)
  
    # 并行处理批次
    tasks = [asyncio.create_task(process_batch(batch)) for batch in batches]
    results = await asyncio.gather(*tasks, return_exceptions=True)
  
    return results
```

## 性能监控

### 指标收集

```python
import time
from collections import defaultdict

class QueryMetrics:
    def __init__(self):
        self.query_times = defaultdict(list)
        self.query_counts = defaultdict(int)
  
    async def time_query(self, query_name, query_func):
        start_time = time.time()
        try:
            result = await query_func()
            execution_time = time.time() - start_time
          
            self.query_times[query_name].append(execution_time)
            self.query_counts[query_name] += 1
          
            if execution_time > 1.0:
                logger.warning(f"慢查询 {query_name}: {execution_time:.2f}s")
          
            return result
        except Exception as e:
            logger.error(f"查询 {query_name} 失败: {e}")
            raise

# 用法
metrics = QueryMetrics()

users = await metrics.time_query(
    "get_active_users",
    lambda: User.objects.filter(User.is_active == True).all()
)
```

### 性能基准测试

```python
async def benchmark_bulk_operations():
    # 测试数据
    test_data = [
        {"username": f"user{i}", "email": f"user{i}@test.com"}
        for i in range(10000)
    ]
  
    # 基准测试批量创建
    start_time = time.time()
    await User.objects.bulk_create(test_data, batch_size=1000)
    bulk_create_time = time.time() - start_time
  
    # 基准测试单独创建
    start_time = time.time()
    for data in test_data[:100]:  # 测试较小样本
        await User.objects.create(**data)
    individual_create_time = (time.time() - start_time) * 100  # 放大
  
    print(f"批量创建: {bulk_create_time:.2f}s")
    print(f"单独创建（估计）: {individual_create_time:.2f}s")
    print(f"性能提升: {individual_create_time / bulk_create_time:.1f}x")
```

## 最佳实践

### 查询优化检查清单

```python
# ✅ 使用适当的加载策略
posts = await Post.objects.select_related("author").prefetch_related("tags").all()

# ✅ 使用高级预获取进行过滤关系
users = await User.objects.prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=30)
    ).order_by('-created_at')
).all()

# ✅ 不需要时跳过默认排序
count = await User.objects.skip_default_ordering().count()

# ✅ 对大型数据集使用批量操作
await User.objects.bulk_update(mappings, match_fields=["id"])

# ✅ 对大型结果集使用迭代器
async for user in User.objects.iterator():
    process_user(user)

# ✅ 只选择需要的字段
users = await User.objects.only("id", "username").all()

# ❌ 避免 N+1 查询
posts = await Post.objects.all()
for post in posts:
    author = await post.author  # N 个额外查询！
```

### 内存管理检查清单

```python
# ✅ 对大型数据集使用迭代器
async for record in Model.objects.iterator():
    process_record(record)

# ✅ 对大型结果集使用分页
users = await User.objects.offset(0).limit(100).all()

# ✅ 在字段级别定义延迟字段
class User(ObjectModel):
    username: Column[str] = column(type="string", length=50)
    bio: Column[str] = column(type="text", deferred=True)  # 默认延迟
    profile_image: Column[bytes] = column(
        type="binary", 
        deferred=True, 
        deferred_group="media"  # 分组相关的延迟字段
    )
  
    # 重要字段的活动历史跟踪
    important_field: Column[str] = column(
        type="string",
        active_history=True  # 跟踪字段值变化
    )

# ✅ 对未标记为延迟的其他字段使用 defer()
users = await User.objects.defer("additional_field").all()

# ❌ 避免将所有内容加载到内存中
all_users = await User.objects.all()  # 可能是数百万条记录！

# ✅ 对大数据使用延迟字段
class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(
        type="text", 
        deferred=True  # 默认不加载
    )
  
# ✅ 对变更跟踪使用活动历史
class AuditableModel(ObjectModel):
    sensitive_field: Column[str] = column(
        type="string",
        active_history=True  # 跟踪此字段的所有变更
    )
```

### 连接池优化

```python
# ✅ 配置适当的池大小
config = DatabaseConfig(
    database_url,
    pool_size=10,      # 基础连接
    max_overflow=20,   # 突发容量
    pool_recycle=3600  # 刷新连接
)

# ✅ 使用会话上下文管理器
async with ctx_session() as session:
    # 事务内的操作
    pass

# ✅ 优雅地处理连接错误
try:
    result = await User.objects.count()
except DatabaseError:
    # 回退或重试逻辑
    pass
```

### 性能测试

```python
# 负载测试示例
async def load_test_queries(concurrent_users=10, queries_per_user=100):
    async def user_simulation():
        for _ in range(queries_per_user):
            # 模拟用户查询
            users = await User.objects.filter(User.is_active == True).limit(10).all()
            await asyncio.sleep(0.1)  # 模拟处理时间
  
    # 运行并发模拟
    tasks = [asyncio.create_task(user_simulation()) for _ in range(concurrent_users)]
  
    start_time = time.time()
    await asyncio.gather(*tasks)
    total_time = time.time() - start_time
  
    total_queries = concurrent_users * queries_per_user
    qps = total_queries / total_time
  
    print(f"在 {total_time:.2f}s 内处理了 {total_queries} 个查询")
    print(f"每秒查询数: {qps:.1f}")
```
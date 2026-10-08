# CRUD 操作

## 概述

SQLObjects 提供了全面的创建、读取、更新、删除操作支持，包括单个和批量处理能力、智能操作检测和事务支持。

## 快速开始

### 基本 CRUD 操作

```python
# 创建
user = await User.objects.create(username="john", email="john@example.com")

# 读取
user = await User.objects.get(User.id == 1)
users = await User.objects.filter(User.is_active == True).all()

# 更新
user.email = "john.new@example.com"
await user.save()

# 删除
await user.delete()
```

## 创建操作

### 单个对象创建

```python
# 方法 1：使用对象管理器
user = await User.objects.create(
    username="alice",
    email="alice@example.com",
    age=25
)

# ObjectsManager 的 create 方法内部使用 from_dict
user = await User.objects.create(
    username="alice",
    email="alice@example.com",
    id=1  # init=False 字段会自动处理
)

# 方法 2：实例创建和保存
user = User(username="bob", email="bob@example.com")
await user.save()

# 带验证控制
user = await User.objects.create(
    username="charlie",
    email="invalid-email",  # 会抛出 ValidationError
    validate=True  # 默认行为
)
```

### 批量创建

```python
# 批量创建以提升性能
users_data = [
    {"username": "user1", "email": "user1@example.com"},
    {"username": "user2", "email": "user2@example.com"},
    {"username": "user3", "email": "user3@example.com"},
]

# 返回创建的记录数量
created_count = await User.objects.bulk_create(users_data, batch_size=1000)
```

### 获取或创建模式

```python
# 获取现有或创建新的
user, created = await User.objects.get_or_create(
    username="david",  # 查找字段
    defaults={"email": "david@example.com", "age": 30}  # 创建时的值
)

# get_or_create 和 update_or_create 也使用 from_dict
user, created = await User.objects.get_or_create(
    username="david",
    defaults={"email": "david@example.com", "id": 100}  # 处理所有字段类型
)

if created:
    print("创建了新用户")
else:
    print("找到了现有用户")

# 多个查找字段
user, created = await User.objects.get_or_create(
    username="eve",
    email="eve@example.com",
    defaults={"age": 25, "is_active": True}
)
```

## 读取操作

### 单个对象检索

```python
# 通过主键获取
user = await User.objects.get(User.id == 1)

# 通过唯一字段获取
user = await User.objects.get(User.username == "john")

# 多条件获取
user = await User.objects.get(
    User.username == "john",
    User.is_active == True
)

# 带排序的第一个/最后一个
first_user = await User.objects.order_by("created_at").first()
latest_user = await User.objects.order_by("-created_at").first()
```

### 多个对象检索

```python
# 所有对象
users = await User.objects.all()

# 过滤结果
active_users = await User.objects.filter(User.is_active == True).all()

# 分页
users_page = await User.objects.offset(20).limit(10).all()
```

### 批量检索

```python
# 通过字段值批量获取
user_dict = await User.objects.in_bulk([1, 2, 3], field_name="id")
# 结果：{1: User(id=1), 2: User(id=2), 3: User(id=3)}

user_dict = await User.objects.in_bulk(
    ["john", "alice", "bob"], 
    field_name="username"
)
# 结果：{"john": User(username="john"), "alice": User(username="alice")}

# 使用主键（默认）
user_dict = await User.objects.in_bulk([1, 2, 3])  # field_name="pk" 为默认值
```

## 更新操作

### 单个对象更新

```python
# 方法 1：加载、修改、保存
user = await User.objects.get(User.id == 1)
user.email = "new.email@example.com"
user.last_login = datetime.now(timezone.utc)
await user.save()

# 方法 2：分离实例的智能保存
user = User(id=1, email="updated@example.com", username="updated_user")
await user.save()  # 自动检测 UPDATE 操作
```

### 批量更新

```python
# 使用相同值更新多条记录
affected = await User.objects.filter(
    User.is_active == False
).update(
    status="inactive",
    updated_at=func.now()  # 数据库时钟而非应用时钟（避免时区错位）
)

# 使用 Q 对象的条件更新
affected = await User.objects.filter(
    Q(User.last_login < datetime.now(timezone.utc) - timedelta(days=30)) |
    Q(User.login_count == 0)
).update(is_active=False)

# 带冲突解决的批量更新
mappings = [
    {"id": 1, "email": "user1@new.com", "status": "active"},
    {"id": 2, "email": "user2@new.com", "status": "inactive"},
    # ... 数千条记录
]

affected = await User.objects.bulk_update(
    mappings,
    match_fields=["id"],
    batch_size=1000
)

# 带冲突处理
from sqlobjects import ConflictResolution

affected = await User.objects.bulk_create(
    users_data,
    on_conflict=ConflictResolution.IGNORE,  # 跳过重复项
    batch_size=1000
)
```

#### 批量操作的事务模式

`bulk_create()` / `bulk_update()` 等批量方法通过 `transaction_mode` 参数
（`sqlobjects.TransactionMode`）控制事务边界：

| 模式 | 事务边界 |
| --- | --- |
| `INHERIT`（默认） | 使用调用方的显式事务；没有显式事务时，为整个调用自有一个事务。 |
| `INDEPENDENT` | 在同一数据库上另开一个独立事务，覆盖所有批次。 |
| `BATCH` | 每个批次自有一个事务，先提交的批次不受后续批次失败影响。 |
| `SAVEPOINT` | 在调用方事务（或自有事务）内，用 savepoint 隔离每个批次。 |

`on_error` 为 `ErrorHandling.COLLECT` 或 `ErrorHandling.IGNORE` 时，每条尝试写入的记录
都用一个 savepoint 隔离，`COLLECT` 报告的是跨批次的输入索引。独立连接可能被外层事务
持有的锁阻塞，不要在独立批次中写入外层事务已锁定的行；SQLite 还会在数据库级别限制并发写入。

UPSERT（`on_conflict=ConflictResolution.UPDATE` 等）会处理每一条输入行。当 RETURNING
能按唯一冲突键匹配时，结果按输入顺序返回，返回对象包含数据库中实际存储的值；
不支持 RETURNING 的后端会按键回查插入或更新的记录，这会产生额外查询。在不报告
`executemany` 行数的驱动上，精确的 UPDATE 计数需要逐行执行。

### 更新或创建模式

```python
# 更新现有或创建新的
user, created = await User.objects.update_or_create(
    username="frank",  # 查找字段
    defaults={
        "email": "frank@example.com",
        "last_login": datetime.now(timezone.utc),
        "login_count": 1
    }
)

if created:
    print("创建了新用户")
else:
    print("更新了现有用户")
```

## 删除操作

### 单个对象删除

```python
# 方法 1：加载并删除
user = await User.objects.get(User.id == 1)
await user.delete()

# 方法 2：删除分离实例
user = User(id=1)
await user.delete()  # 自动附加到会话
```

`Model.delete(cascade=None)` 根据模型的关系自动检测是否需要级联处理。传入 `cascade=True` 可强制级联处理，传入 `cascade=False` 则执行不带级联的直接删除。数据库层外键动作（`OnDelete.CASCADE` 等）与 ORM 层 `relationship(cascade=...)` 在模型本身上配置；详见[级联操作](05-relationships.md#级联操作)一节。

### 批量删除

```python
# 带条件删除
deleted = await User.objects.filter(
    User.is_active == False,
    User.last_login < datetime.now(timezone.utc) - timedelta(days=365)
).delete()

# 使用 Q 对象删除
deleted = await User.objects.filter(
    Q(User.is_deleted == True) | Q(User.status == "banned")
).delete()

# 大型 ID 列表的真正批量删除（快 10-100 倍）
user_ids = [1, 2, 3, 4, 5]  # 数千个 ID
deleted = await User.objects.bulk_delete(
    user_ids,
    id_field="id",
    batch_size=1000
)

# 使用自定义字段的批量删除
usernames = ["user1", "user2", "user3"]
deleted = await User.objects.bulk_delete(
    usernames,
    id_field="username"
)

### 更新所有记录

```python
# 使用相同值更新所有记录
affected = await User.objects.update_all(
    status="migrated",
    updated_at=func.now()
)
```

### 删除所有记录

```python
# 删除所有记录
deleted = await User.objects.delete_all()

# 使用 TRUNCATE 的快速删除（请谨慎使用）
deleted = await User.objects.delete_all(fast=True)  # 返回 -1，无事务安全性
```

## 高级实例操作

### 智能保存检测

```python
# 自动 CREATE vs UPDATE 检测
# 新实例（无主键）→ CREATE
user = User(username="new_user", email="new@example.com")
await user.save()  # INSERT 操作

# 从数据库加载的实例 → UPDATE，只写入脏字段（被赋值过的字段）
user.email = "updated@example.com"
await user.save()  # UPDATE 操作，仅更新 email；没有脏字段时不发出 UPDATE

# 新构造但带主键的实例 → 先 SELECT 判断该主键是否存在：
# 存在则 UPDATE（仅写入已赋值的字段），不存在则 INSERT。不存在 merge() 步骤。
detached_user = User(id=1, username="detached", email="detached@example.com")
await detached_user.save()

# from_dict 创建的实例同样遵循上述规则
user_data = {"username": "new_user", "email": "new@example.com"}
user = User.from_dict(user_data)  # 没有主键
await user.save()  # INSERT 操作

# 手动构造且没有主键的实例一律 INSERT
user = User(username="manual", email="manual@example.com")
await user.save()  # INSERT 操作
```

保存已持久化对象时只写入脏字段，因此一个过期的对象不会覆盖其他字段上的并发修改。
事务回滚不会回退 Python 对象的状态，受影响的实例应丢弃或 `refresh()`。
`create()` / `save()` 不会把数据库异常包装成 `RuntimeError` 或 `PrimaryKeyError`，
`IntegrityError` 等原始异常会直接抛出。

### 刷新操作

```python
# 从数据库完全刷新
user = await User.objects.get(User.id == 1)
user.username = "modified_locally"
await user.refresh()  # 将所有字段重置为数据库状态

# 选择性字段刷新
await user.refresh(fields=["username", "updated_at"])

# 刷新分离实例
detached_user = User(id=1)
await detached_user.refresh()  # 从数据库加载当前数据
```

### 会话管理

```python
# 使用特定数据库会话
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="session_user")
    user.email = "updated@example.com"
    await user.using(session).save()

# 跨数据库操作
user = User(username="multi_db_user")
await user.using("main_db").save()
await user.using("analytics_db").save()  # 相同数据到不同数据库
```

## 事务管理

### 自动事务

```python
# 单个操作（自动提交）
user = await User.objects.create(username="auto_commit")

# 事务中的多个操作
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="tx_user")
    profile = await Profile.objects.using(session).create(user_id=user.id)
    # 成功时自动提交，错误时回滚
```

### 手动事务控制

```python
from sqlobjects.session import ctx_session

async with ctx_session() as session:
    try:
        # 多个操作
        user = await User.objects.using(session).create(username="manual_tx")
        await User.objects.using(session).filter(
            User.is_active == False
        ).update(status="archived")
      
        # 手动提交
        await session.commit()
    except Exception as e:
        # 手动回滚
        await session.rollback()
        raise
```

### 显式事务中的失败处理

显式事务里某条 SQL 失败后（且不在 savepoint 内），事务在回滚之前不可再用：
仅捕获异常不能恢复它，后续语句会抛出 `TransactionError`。对于可恢复的错误，
把语句包在 savepoint 中：

```python
from sqlalchemy.exc import IntegrityError

async with ctx_session() as session:
    try:
        async with await session.begin_nested():
            await User.objects.create(username="duplicate")
    except IntegrityError:
        pass
    await User.objects.create(username="next")  # 事务仍可用
```

只读会话不持有事务，每条语句后即释放连接，失败的查询不影响后续查询。在隐式
（自动提交）会话上，`begin_nested()` 只为 savepoint 打开一个事务，最外层 savepoint
结束后该事务自动提交。

## 性能优化

### 批量大小指南

```python
# 按数据库类型推荐的批量大小
postgresql_batch = 1000  # PostgreSQL 处理更大批次
mysql_batch = 500        # MySQL 倾向于较小批次
sqlite_batch = 100       # SQLite 有较低限制

# 根据记录复杂性调整
simple_records_batch = 2000    # 简单字段（id、name、status）
complex_records_batch = 200    # 复杂字段（JSON、text、binary）

# 使用示例
await User.objects.bulk_create(
    large_dataset,
    batch_size=postgresql_batch if db_type == "postgresql" else mysql_batch
)
```

### 内存管理

```python
# 批量处理大型更新
async def process_large_update(user_ids: list[int]):
    batch_size = 1000
    for i in range(0, len(user_ids), batch_size):
        batch = user_ids[i:i + batch_size]
        await User.objects.bulk_update(
            [{"id": uid, "processed": True} for uid in batch],
            match_fields=["id"]
        )
```

## 错误处理

### 常见异常

```python
from sqlobjects.exceptions import (
    DoesNotExist, 
    MultipleObjectsReturned, 
    ValidationError,
    IntegrityError
)

# 处理未找到
try:
    user = await User.objects.get(User.username == "nonexistent")
except DoesNotExist:
    print("用户未找到")

# 处理多个结果
try:
    user = await User.objects.get(User.email.like("%@gmail.com"))
except MultipleObjectsReturned:
    user = await User.objects.filter(User.email.like("%@gmail.com")).first()

# 处理验证错误
try:
    user = await User.objects.create(username="ab", email="invalid")
except ValidationError as e:
    print(f"验证失败：{e.message}")

# 处理数据库约束
try:
    user = await User.objects.create(username="existing_user")
except IntegrityError as e:
    print(f"数据库约束违反：{e}")
```

### 批量操作错误处理

```python
# 带错误处理的批量操作
try:
    affected = await User.objects.bulk_update(mappings, match_fields=["id"])
    print(f"更新了 {affected} 条记录")
except Exception as e:
    # 处理批量操作失败
    logger.error(f"批量更新失败：{e}")
  
    # 回退到个别更新
    for mapping in mappings:
        try:
            await User.objects.filter(User.id == mapping["id"]).update(
                **{k: v for k, v in mapping.items() if k != "id"}
            )
        except Exception as individual_error:
            logger.error(f"ID {mapping['id']} 的个别更新失败：{individual_error}")
```

## 最佳实践

### 验证策略

```python
# 对用户输入启用验证
user_data = request.json  # 来自 API 请求
user = await User.objects.create(**user_data, validate=True)

# 对可信数据跳过验证
system_user = await User.objects.create(
    username="system",
    email="system@internal.com",
    validate=False  # 为了性能跳过验证
)
```

### 批量 vs 个别操作

```python
# 对大数据集使用批量操作
if len(user_updates) > 100:
    # 批量更新（快 10-100 倍）
    await User.objects.bulk_update(user_updates, match_fields=["id"])
else:
    # 个别更新（更好的错误处理）
    for update in user_updates:
        await User.objects.filter(User.id == update["id"]).update(**update)
```

### 会话使用

```python
# 对相关操作使用会话
async with ctx_session() as session:
    # 所有操作在同一事务中
    user = await User.objects.using(session).create(username="related_ops")
    profile = await Profile.objects.using(session).create(user_id=user.id)
    settings = await Settings.objects.using(session).create(user_id=user.id)
```
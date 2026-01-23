# 模型定义和字段

## 概述

SQLObjects 提供 Django 风格的模型定义系统，具有自动表生成、类型安全字段和全面的验证支持。

## 快速开始

### 基本模型

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100, unique=True)
    age: Column[int] = IntegerColumn(nullable=True)
    is_active: Column[bool] = BooleanColumn(default=True)
```

### 自动生成功能

```python
# ModelProcessor 元类自动处理：
# - 表名："users"（复数形式的 snake_case）
# - 对象管理器：User.objects = ObjectsDescriptor(User)
# - 字段缓存：_cached_field_info 用于性能优化
# - 主键：如果未指定，自动生成 id 字段

user = await User.objects.create(username="john", email="john@example.com")
print(user.id)  # 使用 identity() 或 primary_key=True 时自动生成

# ObjectsDescriptor 在每次访问时提供新的 ObjectsManager 实例
manager1 = User.objects  # 新的 ObjectsManager 实例
manager2 = User.objects  # 另一个新的 ObjectsManager 实例
```

## 字段类型

### 字符串字段

```python
# 基本字符串字段
name: Column[str] = StringColumn(length=100)

# 文本字段（无长度限制）
description: Column[str] = TextColumn()

# 固定长度
code: Column[str] = StringColumn(type="char", length=10)

# 带验证
email: Column[str] = StringColumn(length=100, validators=[validate_email()])
```

### 数值字段

```python
# 整数类型变体
id: Column[int] = IntegerColumn(primary_key=True)
count: Column[int] = IntegerColumn(type="bigint")
rating: Column[int] = IntegerColumn(type="smallint")

# 十进制精度
price: Column[Decimal] = NumericColumn(precision=10, scale=2)
percentage: Column[float] = FloatColumn()
```

### 日期和时间

```python
from datetime import datetime, date, time

# DateTime 自动时间戳
created_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)
updated_at: Column[datetime] = DateTimeColumn(onupdate=datetime.now)

# 日期和时间变体
birth_date: Column[date] = DateTimeColumn(type="date")
start_time: Column[time] = DateTimeColumn(type="time")
```

### 高级类型

```python
# JSON 数据
preferences: Column[dict] = JsonColumn(default=dict)
metadata: Column[list] = JsonColumn(default=list)

# 数组（PostgreSQL）
tags: Column[list[str]] = ArrayColumn("string")
matrix: Column[list[list[int]]] = ArrayColumn("integer", dimensions=2)

# 枚举
from enum import Enum

class UserStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

status: Column[UserStatus] = EnumColumn(UserStatus, default=UserStatus.ACTIVE)

# UUID
import uuid
external_id: Column[str] = UuidColumn(default_factory=uuid.uuid4)

# 二进制数据
file_data: Column[bytes] = BinaryColumn(length=1024)

# 外键关系
from sqlalchemy import ForeignKey
author_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
category_id: Column[int] = column(type="integer", foreign_key=ForeignKey("categories.id"), nullable=False, index=True)

# 自定义类型（参见自定义字段类型文档）
# 在模型中使用之前注册自定义类型
content_vector: Column = column(type="tsvector")  # PostgreSQL 全文搜索
embedding: Column = column(type="pgvector", dimensions=1536)  # 向量相似度
```

对于像 `tsvector` 和 `pgvector` 这样的数据库特定类型，请参阅[自定义字段类型](08-custom-field-types.md)。

## 字段参数

### 通用参数

```python
# 可空性和默认值
username: Column[str] = StringColumn(nullable=False)  # 必需
nickname: Column[str] = StringColumn(nullable=True)   # 可选
is_active: Column[bool] = BooleanColumn(default=True) # 默认值

# 约束
email: Column[str] = StringColumn(unique=True)        # 唯一约束
code: Column[str] = StringColumn(index=True)          # 数据库索引
```

### 智能代码生成参数

```python
# _apply_codegen_defaults 函数自动推断参数
class User(ObjectModel):
    # 常规字段获得默认值：init=True, repr=True, compare=False
    username: Column[str] = column(type="string")  # 自动应用默认值

    # 主键字段自动设置：init=False, repr=True, compare=True
    id: Column[int] = identity()  # 自动检测为主键

    # 自增字段自动设置：init=False
    sequence_id: Column[int] = column(type="integer", autoincrement=True)

    # 服务器默认字段自动设置：init=False
    created_at: Column[datetime] = column(type="datetime", server_default=func.now())

    # 手动覆盖默认值
    internal_field: Column[str] = column(type="string", init=False, repr=False)
    password: Column[str] = column(type="string", repr=False)  # 隐藏敏感信息
    version: Column[int] = column(type="integer", compare=True)  # 包含在比较中

# from_dict 方法自动处理 init 参数
user_data = {"id": 1, "username": "alice", "created_at": datetime.now()}
user = User.from_dict(user_data)  # 自动分离 init=True/False 字段

# ObjectsManager 创建方法使用 from_dict 保持一致性
user = await User.objects.create(
    id=1,  # init=False 字段通过 setattr 处理
    username="bob",  # init=True 字段通过构造函数处理
    created_at=datetime.now()  # init=False 字段通过 setattr 处理
)
```

### 性能优化参数

```python
# 延迟加载参数
bio: Column[str] = column(
    type="text",
    deferred=True,  # 延迟加载直到访问
    deferred_group="details",  # 分组延迟字段
    deferred_raiseload=True  # 访问延迟字段时抛出错误
)

# 历史跟踪
important_field: Column[str] = column(
    type="string",
    active_history=True  # 跟踪字段值变化
)

# 内存优化
profile_image: Column[bytes] = column(
    type="binary",
    deferred=True,
    init=False,      # 从构造函数中排除
    repr=False       # 在字符串表示中隐藏
)
```

### 自动默认规则

```python
# 主键字段自动获得：init=False, repr=True, compare=True
id: Column[int] = identity()

# 自增字段自动获得：init=False
sequence_id: Column[int] = column(type="integer", autoincrement=True)

# 服务器默认字段自动获得：init=False
created_at: Column[datetime] = column(type="datetime", server_default=func.now())

# 常规字段获得：init=True, repr=True, compare=False, hash=None, kw_only=False
username: Column[str] = column(type="string")
```

### 增强功能参数

```python
# 动态默认值和验证
created_at: Column[datetime] = column(
    type="datetime",
    default_factory=datetime.now,  # 动态默认值
    validators=[validate_datetime()]  # 字段级验证
)

# 仅插入默认值
status: Column[str] = column(
    type="string",
    insert_default="pending"  # 仅在 INSERT 操作时的默认值
)

# 关键字参数
optional_param: Column[str] = column(type="string", kw_only=True)
```

## 外键字段

```python
from sqlobjects.fields import column
from sqlalchemy import ForeignKey

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)

    # 使用 column() 和 ForeignKey 参数
    author_id: Column[int] = column(
        type="integer",
        foreign_key=ForeignKey("users.id")
    )
    
    category_id: Column[int] = column(
        type="integer",
        foreign_key=ForeignKey("categories.id"),
        nullable=False,
        index=True
    )

    # 自定义类型的外键
    uuid_ref: Column[str] = column(
        type="string",
        foreign_key=ForeignKey("external_table.uuid")
    )
```

## 字段快捷方式

### Identity 和时间戳

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IdentityColumn, column
from sqlalchemy import ForeignKey
from datetime import datetime

class Post(ObjectModel):
    id: Column[int] = IdentityColumn()  # 自增主键
    title: Column[str] = StringColumn(length=200)
    author_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"), nullable=False)
    created_at: Column[datetime] = column(type="datetime", default_factory=datetime.now)
    updated_at: Column[datetime] = column(type="datetime", onupdate=datetime.now)
```

### Identity 和 Computed 字段

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, NumericColumn, IdentityColumn, ComputedColumn
from decimal import Decimal

class Order(ObjectModel):
    # 自定义配置的 Identity 列
    id: Column[int] = IdentityColumn(start=1000, increment=1)
    order_number: Column[int] = IdentityColumn(start=1000, increment=1, cache=10)

    subtotal: Column[Decimal] = NumericColumn(precision=10, scale=2)
    tax_rate: Column[Decimal] = NumericColumn(precision=5, scale=4)

    # Computed 列
    total: Column[Decimal] = ComputedColumn(
        "subtotal * (1 + tax_rate)", 
        column_type="numeric"
    )

    # 持久化的 computed 列（存储在数据库中）
    total_cached: Column[Decimal] = ComputedColumn(
        "subtotal * (1 + tax_rate)",
        persisted=True,
        column_type="numeric"
    )
```

## 模型配置

### 表设置

```python
class User(ObjectModel):
    # ... 字段 ...

    class Config:
        table_name = "app_users"  # 覆盖默认表名
        ordering = ["-created_at"]  # 默认排序
        verbose_name = "User Account"
        verbose_name_plural = "User Accounts"
```

### 索引和约束

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, NumericColumn
from sqlobjects.config import index, constraint, unique
from decimal import Decimal

class Product(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    sku: Column[str] = StringColumn(length=50)
    price: Column[Decimal] = NumericColumn(precision=10, scale=2)

    class Config:
        indexes = [
            index("idx_sku", "sku", unique=True),
            index("idx_name_price", "name", "price")
        ]
        constraints = [
            constraint("price > 0", "chk_positive_price"),
            unique("name", "sku", name="uq_name_sku")
        ]
```

## 验证

### 字段验证

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column
from sqlobjects.validators import validate_email, validate_length, validate_range

class User(ObjectModel):
    username: Column[str] = column(
        type="string", length=50,
        validators=[validate_length(3, 50)]
    )
    email: Column[str] = column(
        type="string", length=100,
        validators=[validate_email()]
    )
    age: Column[int] = column(
        type="integer",
        validators=[validate_range(0, 150)]
    )
```

### 模型验证

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn
from sqlobjects.exceptions import ValidationError

class User(ObjectModel):
    # ... 字段 ...

    def validate(self):
        """自定义模型级验证"""
        if self.age and self.age < 18 and self.is_admin:
            raise ValidationError("Users under 18 cannot be administrators")
    
        if self.username and self.username.lower() in ['admin', 'root']:
            raise ValidationError("Reserved usernames are not allowed")
```

### 自定义验证

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column
from sqlobjects.validators import validate_regex, validate_length
from sqlobjects.exceptions import ValidationError

def validate_file_extension(value):
    """自定义文件扩展名验证器"""
    if not value.lower().endswith(('.pdf', '.doc', '.docx')):
        raise ValidationError("Only PDF and Word documents are allowed")

class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)

    # 自定义验证
    filename: Column[str] = column(
        type="string",
        validators=[
            validate_length(1, 255),
            validate_file_extension
        ]
    )

    # 模式验证
    document_code: Column[str] = column(
        type="string",
        validators=[
            validate_regex(r'^DOC-\d{4}-\d{2}$', "Format: DOC-YYYY-MM")
        ]
    )
```

## 模型方法

### 实例操作

```python
# 创建和保存
user = User(username="alice", email="alice@example.com")
await user.save()

# 更新
user.email = "alice.new@example.com"
await user.save()

# 删除
await user.delete()

# 从数据库刷新
await user.refresh()
await user.refresh(fields=["username", "email"])  # 选择性刷新
```

### 智能数据转换

```python
# to_dict 方法 - 支持延迟字段和安全访问
user_dict = user.to_dict()  # 所有已加载字段
user_dict = user.to_dict(include=["id", "username"])  # 特定字段
user_dict = user.to_dict(exclude=["password_hash"])  # 排除敏感字段
user_dict = user.to_dict(include_deferred=True)  # 包含延迟字段
user_dict = user.to_dict(safe_access=False)  # 不安全访问可能抛出异常

# from_dict 方法 - 智能处理 init 参数和默认值
user_data = {"username": "bob", "email": "bob@example.com", "id": 1}
user = User.from_dict(user_data, validate=True)

# from_dict 内部过程：
# 1. 过滤无效字段（不在 table.columns 中）
# 2. 应用 default_factory 和 column.default
# 3. 根据 field.get_codegen_params() 分离 init=True/False 字段
# 4. 使用 init=True 字段创建实例
# 5. 通过 setattr 设置 init=False 字段
# 6. 清除脏字段跟踪
# 7. 执行验证（如果 validate=True）

# ObjectsManager 集成 - 所有创建方法使用 from_dict
user = await User.objects.create(
    id=1,  # init=False 字段自动处理
    username="alice",  # init=True 字段
    created_at=datetime.now()  # init=False 字段自动处理
)

user, created = await User.objects.get_or_create(
    username="bob",
    defaults={"id": 2, "created_at": datetime.now()}  # 混合字段类型自动处理
)

user, created = await User.objects.update_or_create(
    username="charlie",
    defaults={"email": "charlie@example.com"}  # 更新也使用 from_dict 逻辑
)
```

## 最佳实践

### 字段命名

```python
# 使用描述性名称
created_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)
is_active: Column[bool] = BooleanColumn(default=True)
user_count: Column[int] = IntegerColumn(default=0)

# 避免缩写
# 好：description, category_id, is_published
# 避免：desc, cat_id, pub
```

### 默认值

```python
# 静态默认值
is_active: Column[bool] = BooleanColumn(default=True)
status: Column[str] = StringColumn(default="pending")

# 动态默认值
created_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)
uuid: Column[str] = UuidColumn(default_factory=uuid.uuid4)
```

### 验证策略

```python
# 结合字段和模型验证
class User(ObjectModel):
    email: Column[str] = column(type="string", validators=[validate_email()])  # 字段级
    age: Column[int] = column(type="integer", validators=[validate_range(0, 150)])

    def validate(self):  # 模型级
        if self.email and User.objects.filter(User.email == self.email).exists():
            raise ValidationError("Email already exists")
```

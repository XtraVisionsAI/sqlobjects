# 验证和信号

## 概述

SQLObjects 提供了字段级和模型级的全面验证功能，以及强大的信号系统，用于连接数据库操作并提供自动生命周期管理。

## 快速开始

### 基础验证

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn
from sqlobjects.validators import validate_email, validate_length
from sqlobjects.exceptions import ValidationError

class User(ObjectModel):
    username: Column[str] = StringColumn(
        length=50, 
        validators=[validate_length(3, 50)]
    )
    email: Column[str] = StringColumn(
        length=100, 
        validators=[validate_email()]
    )
    age: Column[int] = IntegerColumn(nullable=True)
  
    def validate(self):
        """模型级验证"""
        if self.age and self.age < 13:
            raise ValidationError("用户年龄必须至少13岁")
```

### 基础信号

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
from datetime import datetime

class User(ObjectModel):  # 内置信号支持
    # ... 字段定义 ...
  
    async def before_save(self, context: SignalContext):
        """在任何保存操作前调用"""
        self.updated_at = datetime.now()
  
    async def before_create(self, context: SignalContext):
        """仅在创建新记录前调用"""
        self.created_at = datetime.now()
```

## 字段验证

### 内置验证器

```python
from sqlobjects.validators import (
    validate_email, validate_url, validate_length, validate_range,
    validate_regex, validate_choices, validate_date, validate_time,
    validate_decimal, validate_json
)

class User(ObjectModel):
    # 邮箱验证
    email: Column[str] = StringColumn(validators=[validate_email()])
  
    # 长度验证
    username: Column[str] = StringColumn(validators=[validate_length(3, 50)])
  
    # 范围验证
    age: Column[int] = IntegerColumn(validators=[validate_range(0, 150)])
  
    # 正则表达式验证
    phone: Column[str] = StringColumn(validators=[validate_regex(r"^\d{3}-\d{3}-\d{4}$")])
  
    # 选择值验证
    status: Column[str] = StringColumn(validators=[validate_choices(["active", "inactive", "pending"])])
  
    # URL验证
    website: Column[str] = StringColumn(validators=[validate_url()])
  
    # 日期/时间验证
    birth_date: Column[str] = StringColumn(validators=[validate_date("%Y-%m-%d")])
    work_time: Column[str] = StringColumn(validators=[validate_time("%H:%M")])
  
    # 小数验证
    price: Column[str] = StringColumn(validators=[validate_decimal(10, 2)])
  
    # JSON验证
    metadata: Column[str] = StringColumn(validators=[validate_json()])
```

### 高级验证器

```python
from sqlobjects.validators import validate_regex, validate_choices

class Document(ObjectModel):
    title: Column[str] = StringColumn(length=200)
  
    # 使用正则表达式验证文件扩展名
    filename: Column[str] = StringColumn(validators=[
        validate_regex(
            r'\.(pdf|doc|docx|txt)$',
            "文件必须是PDF、DOC、DOCX或TXT格式"
        )
    ])
  
    # 文档类型验证
    doc_type: Column[str] = StringColumn(validators=[
        validate_choices(["report", "manual", "specification", "other"])
    ])
  
    # 文件大小验证（字符串表示）
    file_size: Column[str] = StringColumn(validators=[
        validate_regex(r'^\d+[KMGT]?B$', "大小格式：100B、1KB、1MB等")
    ])
```

### 自定义验证器

```python
from sqlobjects.exceptions import ValidationError

def validate_username(value):
    """自定义用户名验证器"""
    if not value:
        raise ValidationError("用户名是必需的")
  
    if len(value) < 3:
        raise ValidationError("用户名至少需要3个字符")
  
    if not value.isalnum():
        raise ValidationError("用户名只能包含字母和数字")
  
    # 检查保留名称
    reserved = ["admin", "root", "system", "api"]
    if value.lower() in reserved:
        raise ValidationError("该用户名为保留名称")

def validate_strong_password(value):
    """强密码验证器"""
    if not value:
        raise ValidationError("密码是必需的")
  
    if len(value) < 8:
        raise ValidationError("密码至少需要8个字符")
  
    if not any(c.isupper() for c in value):
        raise ValidationError("密码必须包含至少一个大写字母")
  
    if not any(c.islower() for c in value):
        raise ValidationError("密码必须包含至少一个小写字母")
  
    if not any(c.isdigit() for c in value):
        raise ValidationError("密码必须包含至少一个数字")

class User(ObjectModel):
    username: Column[str] = StringColumn(validators=[validate_username])
    password: Column[str] = StringColumn(validators=[validate_strong_password])
```

### 组合验证器

```python
from sqlobjects.validators import combine_validators

class User(ObjectModel):
    # 组合多个验证器
    username: Column[str] = StringColumn(validators=[
        combine_validators(
            validate_length(3, 50),
            validate_regex(r"^[a-zA-Z0-9_]+$"),
            validate_username  # 自定义验证器
        )
    ])
  
    # 多个独立验证器
    email: Column[str] = StringColumn(validators=[
        validate_email(),
        validate_length(5, 100)
    ])
```

## 模型验证

### 模型级验证

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    age: Column[int] = IntegerColumn(nullable=True)
    is_admin: Column[bool] = BooleanColumn(default=False)
  
    def validate(self):
        """跨字段验证"""
        # 管理员用户的年龄限制
        if self.is_admin and self.age and self.age < 18:
            raise ValidationError("管理员用户必须至少18岁")
      
        # 邮箱域名限制
        if self.email and self.is_admin:
            if not self.email.endswith("@company.com"):
                raise ValidationError("管理员用户必须使用公司邮箱")
      
        # 用户名唯一性（示例 - 通常由数据库约束处理）
        if self.username:
            existing = User.objects.filter(
                User.username == self.username,
                User.id != self.id  # 更新时排除自身
            ).exists()
            if existing:
                raise ValidationError("用户名已存在")
```

### 验证控制

```python
# 自动验证（默认）
user = await User.objects.create(
    username="john",
    email="john@example.com"
)  # 自动验证

# 跳过可信数据的验证
system_user = await User.objects.create(
    username="system",
    email="system@internal.com",
    validate=False  # 跳过验证
)

# 手动验证
user = User(username="alice", email="alice@example.com")
user.validate_all()  # 验证所有字段和模型
user.validate_fields(["username", "email"])  # 验证特定字段
user.validate()  # 仅模型级验证

# 保存时验证
user = User(username="bob", email="bob@example.com")
await user.save(validate=True)  # 默认行为
await user.save(validate=False)  # 跳过验证
```

### 验证错误处理

```python
from sqlobjects.exceptions import ValidationError, ValidationErrorCollector

# 单个验证错误
try:
    user = User(username="ab", email="invalid-email")
    user.validate_all()
except ValidationError as e:
    print(f"验证失败：{e.message}")
    print(f"字段：{e.field}")
    print(f"代码：{e.code}")

# 多个验证错误
try:
    user = User(username="a", email="bad", age=-5)
    user.validate_all()
except ValidationError as e:
    if hasattr(e, 'errors') and e.errors:
        for field, errors in e.errors.items():
            print(f"{field}: {', '.join(errors)}")

# 手动错误收集
collector = ValidationErrorCollector()
if not username:
    collector.add_error("username", "用户名是必需的")
if not email:
    collector.add_error("email", "邮箱是必需的")
collector.raise_if_errors()  # 如有错误则抛出ValidationError
```

## 信号系统

### 信号类型

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext, Operation
from datetime import datetime
import uuid

class User(ObjectModel):  # 已内置信号功能
    # 实例级信号（单记录操作）
    async def before_save(self, context: SignalContext):
        """通用保存逻辑 - 总是触发"""
        self.updated_at = datetime.now()
  
    async def before_create(self, context: SignalContext):
        """仅在CREATE操作时触发"""
        self.created_at = datetime.now()
        self.uuid = str(uuid.uuid4())
  
    async def before_update(self, context: SignalContext):
        """仅在UPDATE操作时触发"""
        self.version += 1
  
    async def before_delete(self, context: SignalContext):
        """删除前触发"""
        # 记录删除或清理操作
        await AuditLog.objects.create(
            action="delete",
            model="User",
            object_id=self.id
        )
  
    async def after_save(self, context: SignalContext):
        """保存操作后"""
        # 发送通知、更新缓存等
        pass
  
    async def after_create(self, context: SignalContext):
        """仅在创建后"""
        # 发送欢迎邮件、创建相关对象
        await self.send_welcome_email()
  
    async def after_update(self, context: SignalContext):
        """仅在更新后"""
        # 使缓存失效、发送更新通知
        cache.delete(f"user:{self.id}")
  
    async def after_delete(self, context: SignalContext):
        """删除后"""
        # 清理相关数据
        await self.cleanup_user_data()
```

### 批量操作信号

```python
class User(ObjectModel):
    # 批量操作信号（多记录）
    @classmethod
    async def before_bulk_create(cls, context: SignalContext):
        """批量创建前"""
        print(f"正在创建 {context.affected_count} 个用户")
  
    @classmethod
    async def before_bulk_update(cls, context: SignalContext):
        """批量更新前"""
        print(f"正在更新 {context.affected_count} 个用户")
        # 访问更新数据
        if context.update_data:
            print(f"更新数据：{context.update_data}")
  
    @classmethod
    async def before_bulk_delete(cls, context: SignalContext):
        """批量删除前"""
        print(f"正在删除 {context.affected_count} 个用户")
  
    @classmethod
    async def after_bulk_create(cls, context: SignalContext):
        """批量创建后"""
        # 发送批量通知
        pass
  
    @classmethod
    async def after_bulk_update(cls, context: SignalContext):
        """批量更新后"""
        # 使受影响记录的缓存失效
        pass
  
    @classmethod
    async def after_bulk_delete(cls, context: SignalContext):
        """批量删除后"""
        # 清理相关数据
        pass
```

### 信号上下文

```python
from sqlobjects.signals import SignalContext, Operation

# SignalContext提供操作信息
async def before_save(self, context: SignalContext):
    print(f"操作：{context.operation}")  # SAVE, CREATE, UPDATE, DELETE
    print(f"会话：{context.session}")  # 数据库会话
    print(f"模型：{context.model_class}")  # 模型类
    print(f"实例：{context.instance}")  # 模型实例（单操作）
    print(f"影响数量：{context.affected_count}")  # 批量操作
    print(f"更新数据：{context.update_data}")  # 批量更新
    print(f"实际操作：{context.actual_operation}")  # SAVE的检测操作
```

### 智能SAVE操作

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
from datetime import datetime

class User(ObjectModel):
    async def before_save(self, context: SignalContext):
        """总是为save()操作调用"""
        self.updated_at = datetime.now()
  
    async def before_create(self, context: SignalContext):
        """为新实例调用"""
        self.created_at = datetime.now()
  
    async def before_update(self, context: SignalContext):
        """为现有实例调用"""
        self.version += 1

# 智能保存自动检测CREATE vs UPDATE
user = User(username="new_user")  # 无主键
await user.save()  # 触发：before_save → before_create → after_save → after_create

user.username = "updated_user"
await user.save()  # 触发：before_save → before_update → after_save → after_update

# 有主键的分离实例
detached_user = User(id=1, username="detached")
await detached_user.save()  # 触发：before_save → before_update → after_save → after_update
```

### 信号与操作集成

```python
# get_or_create和update_or_create触发信号
user, created = await User.objects.get_or_create(
    username="signal_user",
    defaults={"email": "signal@example.com"}
)
# 如果创建：before_save → before_create → after_save → after_create
# 如果找到：不触发信号

user, created = await User.objects.update_or_create(
    username="signal_user",
    defaults={"last_login": datetime.now()}
)
# 如果更新：before_save → before_update → after_save → after_update
# 如果创建：before_save → before_create → after_save → after_create
```

## 高级验证模式

### 条件验证

```python
class User(ObjectModel):
    user_type: Column[str] = StringColumn(length=20)
    company_email: Column[str] = StringColumn(length=100, nullable=True)
    personal_email: Column[str] = StringColumn(length=100, nullable=True)
  
    def validate(self):
        if self.user_type == "employee":
            if not self.company_email:
                raise ValidationError("员工用户必须有公司邮箱")
            if not self.company_email.endswith("@company.com"):
                raise ValidationError("公司邮箱必须来自公司域名")
      
        elif self.user_type == "customer":
            if not self.personal_email:
                raise ValidationError("客户用户必须有个人邮箱")
```

### 异步验证

```python
class User(ObjectModel):
    email: Column[str] = StringColumn(length=100)
  
    async def validate(self):
        """异步模型验证"""
        # 在数据库中检查邮箱唯一性
        if self.email:
            existing = await User.objects.filter(
                User.email == self.email,
                User.id != self.id
            ).exists()
            if existing:
                raise ValidationError("邮箱已存在")
      
        # 外部API验证
        if self.email:
            is_valid = await validate_email_with_external_service(self.email)
            if not is_valid:
                raise ValidationError("邮箱未通过外部验证")
```

### 验证与信号结合

```python
class User(ObjectModel, SignalMixin):
    async def before_save(self, context: SignalContext):
        """信号中的验证"""
        # 保存前执行验证
        if not self.email:
            raise ValidationError("邮箱是必需的")
      
        # 业务规则验证
        if self.is_admin and self.age < 21:
            raise ValidationError("管理员用户必须至少21岁")
  
    async def before_create(self, context: SignalContext):
        """创建特定验证"""
        # 检查重复用户名
        existing = await User.objects.filter(User.username == self.username).exists()
        if existing:
            raise ValidationError("用户名已存在")
```

## 最佳实践

### 验证策略

```python
# 分层验证
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn
from sqlobjects.validators import validate_email, validate_range
from sqlobjects.exceptions import ValidationError
from sqlobjects.signals import SignalContext

class User(ObjectModel):
    # 字段级：基础格式验证
    email: Column[str] = StringColumn(validators=[validate_email()])
    age: Column[int] = IntegerColumn(validators=[validate_range(0, 150)])
    is_admin: Column[bool] = BooleanColumn(default=False)
  
    # 模型级：跨字段和业务规则
    def validate(self):
        if self.is_admin and self.age < 18:
            raise ValidationError("管理员用户必须为成年人")
  
    # 信号级：依赖数据库的验证
    async def before_save(self, context: SignalContext):
        if await self.has_pending_violations():
            raise ValidationError("不能保存有待处理违规的用户")
```

### 信号组织

```python
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
from datetime import datetime

class User(ObjectModel):
    # 分组相关信号处理器
  
    # === 时间戳管理 ===
    async def before_save(self, context: SignalContext):
        self.updated_at = datetime.now()
  
    async def before_create(self, context: SignalContext):
        self.created_at = datetime.now()
  
    # === 审计日志 ===
    async def after_save(self, context: SignalContext):
        await self.log_change(context.operation)
  
    async def after_delete(self, context: SignalContext):
        await self.log_deletion()
  
    # === 缓存管理 ===
    async def after_update(self, context: SignalContext):
        cache.delete(f"user:{self.id}")
  
    # === 通知 ===
    async def after_create(self, context: SignalContext):
        await self.send_welcome_email()
```

### 错误处理

```python
# 信号中的优雅错误处理
from sqlobjects.model import ObjectModel
from sqlobjects.signals import SignalContext
import logging

logger = logging.getLogger(__name__)

class User(ObjectModel):
    async def after_create(self, context: SignalContext):
        try:
            # 非关键操作
            await self.send_welcome_email()
            await self.create_default_preferences()
        except Exception as e:
            # 记录但不使事务失败
            logger.error(f"用户 {self.id} 的创建后任务失败：{e}")
  
    async def before_save(self, context: SignalContext):
        # 关键验证 - 让异常向上抛出
        if not self.email:
            raise ValidationError("邮箱是必需的")
```
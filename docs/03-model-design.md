# SQLObjects 模型设计文档

## 概述

SQLObjects 模型模块提供强大的模型基类和配置系统，支持 Django 风格的模型定义、验证系统、实例操作和灵活的数据库配置。通过
ObjectModel 基类和 ConfigManager 配置系统，为开发者提供完整的 ORM 模型解决方案。

## 核心特性

### 1. Django 风格模型定义

提供熟悉的模型定义方式，支持字段定义、配置和自动表名生成：

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import str_column, int_column, datetime_column
from datetime import datetime

class User(ObjectModel):
    name: Column[str] = str_column(length=50)
    email: Column[str] = str_column(length=100, unique=True)
    age: Column[int] = int_column()
    created_at: Column[datetime] = datetime_column(default=datetime.now)
    
    class Config:
        table_name = "users"                           # 自定义表名
        ordering = ["-created_at", "name"]             # 默认排序
        verbose_name = "User"                          # 人类可读名称
        description = "User information table"         # 模型描述

# 自动表名生成：User -> users（复数形式）
# 自动提供 objects 管理器
users = await User.objects.all()
```

### 2. 完整的验证系统

支持字段级验证、模型级验证和自定义验证器：

```python
from sqlobjects.validators import EmailValidator, LengthValidator

class User(ObjectModel):
    username: Column[str] = str_column(
        length=50,
        validators=[LengthValidator(min_length=3, max_length=50)]
    )
    email: Column[str] = str_column(
        length=100,
        validators=[EmailValidator()]
    )
    
    def validate(self):
        """模型级验证"""
        if self.age < 0:
            raise ValidationError("Age cannot be negative")
        if self.username and self.username.lower() == "admin":
            raise ValidationError("Username cannot be admin")
    
    @classmethod
    def setup_validators(cls):
        """设置字段验证器"""
        cls.add_field_validator("username", cls.validate_username)
    
    @staticmethod
    def validate_username(value):
        if value and len(value.strip()) != len(value):
            raise ValidationError("Username cannot contain leading/trailing spaces")

# 验证使用
user = User(username="john", email="john@example.com", age=25)
user.validate_all()  # 执行完整验证
await user.save()    # 保存时自动验证
```

### 3. 灵活的数据库配置系统

支持多数据库配置、索引、约束和数据库特定优化：

```python
from sqlobjects.config import (
    index, constraint, unique, 
    mysql_config, postgresql_config, multi_db_config
)

class Product(ObjectModel):
    name: Column[str] = str_column(length=100)
    price: Column[Decimal] = numeric_column(precision=10, scale=2)
    category: Column[str] = str_column(length=50)
    status: Column[str] = str_column(length=20)
    
    class Config:
        # 索引配置
        indexes = [
            index("idx_name", "name"),                           # 普通索引
            index("idx_category_status", "category", "status"),  # 复合索引
            index("idx_price", "price", unique=True),            # 唯一索引
        ]
        
        # 约束配置
        constraints = [
            constraint("price > 0", "ck_price_positive"),
            unique("name", "category", name="uq_name_category")
        ]
        
        # 多数据库配置
        db_options = multi_db_config(
            mysql={"engine": "InnoDB", "charset": "utf8mb4"},
            postgresql={"tablespace": "fast_storage"},
            generic={"comment": "Product information table"}
        )
```

### 4. 增强的实例操作功能

#### 智能 save() 方法

自动检测 CREATE vs UPDATE 操作，支持分离实例处理：

```python
# 新实例自动检测为 CREATE
user = User(name="John", email="john@example.com")
await user.save()  # 执行 INSERT 操作

# 现有实例自动检测为 UPDATE
user.name = "Jane"
await user.save()  # 执行 UPDATE 操作

# 分离实例（带主键）智能处理
detached_user = User(id=1, name="Alice", email="alice@example.com")
await detached_user.save()  # 使用 merge() 执行 UPDATE 操作

# 支持复合主键
composite_model = CompositeModel(key1="a", key2="b", data="value")
await composite_model.save()  # 智能检测主键状态
```

#### 分离实例操作支持

处理未附加到 SQLAlchemy 会话的实例：

```python
# 分离实例删除
detached_user = User(id=1)  # 仅有主键的实例
await detached_user.delete()  # 自动附加到会话后删除

# 分离实例刷新
detached_user = User(id=1, name="Old Name")
await detached_user.refresh()  # 从数据库重新加载数据
print(detached_user.name)  # 显示最新数据

# 选择性字段刷新
await detached_user.refresh(fields=["name", "email"])
```

#### 统一的 refresh() 方法

合并原有的 refresh() 和 refresh_from_db() 功能：

```python
# 完整刷新（替代原 refresh_from_db()）
user = await User.objects.get(User.id == 1)
user.name = "Modified"
await user.refresh()  # 重置所有字段到数据库状态

# 选择性字段刷新
await user.refresh(fields=["name", "updated_at"])  # 仅刷新指定字段

# 分离实例刷新
detached_user = User(id=1)
await detached_user.refresh()  # 通过直接查询加载数据
```

### 5. 会话绑定和多数据库支持

通过 ModelProxy 提供灵活的会话管理，支持多数据库操作：

```python
# 默认会话使用
user = User(name="John", email="john@example.com")
await user.save()

# 特定会话绑定
user = User(name="Alice", email="alice@example.com")
await user.using(analytics_session).save()

# 数据库名称绑定
await user.using("analytics").save()

# 会话绑定保留所有模型功能
proxy_user = user.using(analytics_session)
await proxy_user.save()
await proxy_user.delete()
user_dict = proxy_user.to_dict()
```

## 模块架构

### 模块文件结构

模型模块由两个核心文件组成：

- **base.py**：模型基类实现，包含 ObjectModel、ModelMixin、ModelProxy 等核心类
- **config.py**：配置系统实现，包含 ConfigManager、ModelConfig、数据库特定配置函数

### 核心组件

#### base.py 组件

##### 1. ModelMixin - 实例方法接口

通过私有方法提供模型实例操作的抽象接口：

```python
class ModelMixin(SignalMixin):
    """为模型添加实例方法和验证功能的混入类"""
    
    # 私有接口方法（由子类实现）
    def _get_session(self) -> AsyncSession:
        """获取数据库操作的有效会话"""
        raise NotImplementedError("Subclasses must implement _get_session()")
    
    def _get_model_class(self) -> type:
        """获取此实例的模型类"""
        raise NotImplementedError("Subclasses must implement _get_model_class()")
    
    def _get_instance(self):
        """获取实际的模型实例"""
        raise NotImplementedError("Subclasses must implement _get_instance()")
    
    def _update_instance(self, new_instance):
        """更新内部实例引用（用于 ModelProxy）"""
        # ObjectModel 的默认实现 - 无操作
        pass
    
    def _has_primary_key_values(self) -> bool:
        """检测实例是否具有主键值"""
        instance = self._get_instance()
        if hasattr(instance, "__table__"):
            for pk_col in instance.__table__.primary_key.columns:
                value = getattr(instance, pk_col.name, None)
                if value is None:
                    return False
            return len(instance.__table__.primary_key.columns) > 0
        return False
    
    # 会话绑定方法
    def using(self, db_or_session: str | AsyncSession) -> "ModelProxy":
        """返回绑定到特定数据库/会话的代理"""
        return ModelProxy(self._get_instance(), db_or_session)
```

##### 2. ModelProxy - 会话绑定代理

实现会话绑定功能，支持自动会话附加：

```python
class ModelProxy(ModelMixin):
    """包装模型实例并绑定特定会话的代理类"""
    
    def __init__(self, instance, db_or_session: str | AsyncSession):
        self._instance = instance
        self._db_or_session = db_or_session
        self._session_attached = False
    
    def _ensure_session_attachment(self, session: AsyncSession) -> None:
        """确保实例正确附加到指定会话"""
        if self._session_attached:
            return
        
        current_session = async_object_session(self._instance)
        if current_session is None:
            # 对于带主键的分离实例，避免与 merge() 操作冲突
            if not self._has_primary_key_values():
                session.add(self._instance)
        elif current_session is not session:
            self._handle_session_migration(current_session, session)
        
        self._session_attached = True
    
    def _update_instance(self, new_instance):
        """更新内部实例引用（处理 merge() 返回的新实例）"""
        self._instance = new_instance
        self._session_attached = True  # 新实例已附加到会话
    
    def __getattr__(self, name):
        """将属性访问代理到包装的实例"""
        return getattr(self._instance, name)
    
    def __setattr__(self, name, value):
        """将属性设置代理到包装的实例"""
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            setattr(self._instance, name, value)
```

##### 3. ObjectModel - 主要基类

继承自 SQLAlchemy DeclarativeBase 和 ModelMixin，提供完整的模型功能：

```python
class ObjectModel(DeclarativeBase, ModelMixin):
    """支持配置和通用功能的基础模型类"""
    
    __abstract__ = True
    
    def __init_subclass__(cls, **kwargs):
        """处理子类初始化，包括配置解析和设置"""
        cls._process_config()      # 处理配置
        cls._setup_validators()    # 设置验证器
        super().__init_subclass__(**kwargs)
    
    @classmethod
    def _process_config(cls):
        """使用全局配置管理器处理和应用模型配置"""
        _, is_abstract = process_model_config(cls)
        
        # 为非抽象模型设置 objects 管理器
        if not is_abstract and not hasattr(cls, "objects"):
            cls.objects = ObjectsDescriptor(cls)
```

#### config.py 组件

##### 1. ConfigManager - 全局配置管理器

管理模型配置生命周期，支持缓存和处理：

```python
class ConfigManager:
    """处理完整模型配置生命周期的统一配置管理器"""
    
    def __init__(self):
        self.parser = _ConfigParser()
        self._config_cache: dict[type, ModelConfig] = {}
    
    def process_model_config(self, model_class: type) -> tuple[ModelConfig, bool]:
        """处理模型配置并缓存结果"""
        # 处理配置
        config = self.parser.process_complete_config(model_class)
        
        # 将配置应用到模型类
        is_abstract = self._is_abstract_model(model_class, config)
        if not is_abstract:
            self._apply_config_to_model(model_class, config)
        
        # 缓存配置
        self._config_cache[model_class] = config
        return config, is_abstract
```

##### 2. _ConfigParser - 配置解析器

处理配置解析和合并逻辑：

```python
class _ConfigParser:
    """内部配置解析器，处理配置解析和合并逻辑"""
    
    def process_complete_config(self, model_class: type) -> ModelConfig:
        """处理模型的完整配置"""
        configs = []
        
        # 解析类属性配置
        class_config = self.parse_class_attributes(model_class)
        if class_config:
            configs.append(class_config)
        
        # 解析 Config 内部类
        config_class = getattr(model_class, "Config", None)
        if config_class:
            inner_config = self.parse_config_class(config_class)
            if inner_config:
                configs.append(inner_config)
        
        # 合并配置
        return self.merge_configs(*configs) if configs else ModelConfig()
```

### 设计理念

#### 1. 职责分离

- **ModelMixin**：定义实例方法接口，不依赖具体实现
- **ModelProxy**：处理会话绑定逻辑，透明代理功能
- **ObjectModel**：组合功能，提供完整模型体验
- **ConfigManager**：统一配置管理，支持缓存和生命周期

#### 2. 灵活的会话管理

```python
# 设计支持多种会话绑定方式
user.using(session)        # AsyncSession 实例
user.using("database")     # 数据库名称字符串
user.using(None)           # 使用默认会话

# 代理保持完整功能
proxy = user.using(session)
await proxy.save()         # 所有方法都可用
proxy.name = "New Name"    # 属性访问透明
```

#### 3. 智能实例操作设计

实例操作的智能化设计原则：

- **自动操作检测**：save() 方法根据主键状态自动选择 CREATE 或 UPDATE
- **分离实例支持**：处理未附加到会话的实例，使用 merge() 策略
- **会话状态管理**：智能处理实例在不同会话间的迁移
- **引用一致性**：ModelProxy 自动更新内部引用以保持一致性

```python
# 智能操作检测示例
def _has_primary_key_values(self) -> bool:
    """CREATE vs UPDATE 的关键判断逻辑"""
    for pk_col in self.__table__.primary_key.columns:
        if getattr(self, pk_col.name, None) is None:
            return False
    return True

# 分离实例处理策略
if self._has_primary_key_values():
    # 使用 merge() 实现 UPDATE 语义
    merged_instance = await session.merge(instance)
    self._update_instance(merged_instance)  # 更新引用
else:
    # 使用 add() 实现 CREATE 语义
    session.add(instance)
```

#### 4. 配置系统集成

模型配置通过多个层次进行处理：

1. **类属性解析**：从模型类直接定义的属性中提取配置
2. **Config 类解析**：处理内部 Config 类的配置
3. **配置合并**：智能合并多个配置源
4. **配置应用**：将最终配置应用到模型类

## API 参考

### 模型定义

#### ObjectModel 基类

```python
class ObjectModel(DeclarativeBase, ModelMixin):
    # 配置访问方法
    @classmethod
    def get_table_name(cls) -> str
    @classmethod
    def get_verbose_name(cls) -> str
    @classmethod
    def get_verbose_name_plural(cls) -> str
    @classmethod
    def get_description(cls) -> str
    @classmethod
    def get_config(cls) -> ModelConfig
    @classmethod
    def get_metadata(cls) -> dict[str, Any]
    
    # 验证方法
    def validate(self) -> None
    def validate_all(self) -> None
    def validate_fields(self, field_names: list[str]) -> None
    
    # 实例操作方法
    async def save(self, validate: bool = True) -> None
    async def delete(self) -> None
    async def refresh(self, fields: list[str] = None) -> None
    
    # 数据转换方法
    def to_dict(self, include: list[str] = None, exclude: list[str] = None) -> dict
    @classmethod
    def from_dict(cls, data: dict, validate: bool = True) -> Self
```

#### 会话绑定 API

```python
# ModelMixin 提供的会话绑定接口
def using(self, db_or_session: str | AsyncSession) -> ModelProxy

# ModelProxy 提供的代理功能
class ModelProxy(ModelMixin):
    # 透明代理所有模型属性和方法
    def __getattr__(self, name) -> Any
    def __setattr__(self, name, value) -> None
    
    # 继承所有 ModelMixin 方法
    async def save(self, validate: bool = True) -> None
    async def delete(self) -> None
    def to_dict(self, **kwargs) -> dict
```

### 配置系统

#### 配置函数

```python
# 索引配置
def index(name: str, *fields: str, unique: bool = False) -> IndexConfig

# 约束配置
def constraint(condition: str, name: str = None) -> ConstraintConfig
def unique(*fields: str, name: str = None) -> UniqueConfig

# 数据库特定配置
def mysql_config(**options) -> dict
def postgresql_config(**options) -> dict
def multi_db_config(**db_configs) -> dict
```

#### Config 类配置选项

```python
class Config:
    # 基本配置
    table_name: str = None                    # 自定义表名
    verbose_name: str = None                  # 人类可读名称
    verbose_name_plural: str = None           # 复数形式名称
    description: str = None                   # 模型描述
    
    # 查询配置
    ordering: list[str] = None                # 默认排序
    
    # 数据库配置
    indexes: list[IndexConfig] = None         # 索引配置
    constraints: list[ConstraintConfig] = None # 约束配置
    db_options: dict = None                   # 数据库特定选项
```

### 验证系统

#### 验证器设置

```python
# 字段级验证器
from sqlobjects.validators import EmailValidator, LengthValidator

field: Column[str] = str_column(
    validators=[EmailValidator(), LengthValidator(min_length=3)]
)

# 类方法设置验证器
@classmethod
def setup_validators(cls):
    cls.add_field_validator("field_name", validator_function)

# 静态验证方法
@staticmethod
def validate_field(value):
    if not condition:
        raise ValidationError("Error message")
```

#### 验证执行

```python
# 实例验证方法
user.validate()                    # 模型级验证
user.validate_all()               # 完整验证（字段 + 模型）
user.validate_fields(["name"])    # 特定字段验证

# 保存时自动验证
await user.save()                 # 默认执行验证
await user.save(validate=False)   # 跳过验证
```

## 使用指南

### 基础使用

#### 简单模型定义

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import str_column, int_column, bool_column

class User(ObjectModel):
    name: Column[str] = str_column(length=50)
    age: Column[int] = int_column()
    is_active: Column[bool] = bool_column(default=True)

# 自动生成表名：users
# 自动提供 objects 管理器
users = await User.objects.all()
```

#### 基本实例操作

```python
# 创建新实例
user = User(name="John", age=25)
await user.save()  # 自动检测为 CREATE 操作

# 更新现有实例
user.name = "Jane"
await user.save()  # 自动检测为 UPDATE 操作

# 处理分离实例（带主键的实例）
detached_user = User(id=1, name="Alice", age=30)
await detached_user.save()  # 智能处理为 UPDATE 操作

# 删除实例（支持分离实例）
await user.delete()

# 刷新实例（统一方法）
await user.refresh()                    # 完整刷新
await user.refresh(fields=["name"])     # 选择性字段刷新
```

#### 数据转换

```python
# 转换为字典
user_dict = user.to_dict()
user_dict = user.to_dict(include=["name", "age"])
user_dict = user.to_dict(exclude=["password"])

# 从字典创建
data = {"name": "John", "age": 25}
user = User.from_dict(data, validate=True)
```

### 高级使用

#### 复杂模型配置

```python
from sqlobjects.config import index, constraint, multi_db_config

class Product(ObjectModel):
    name: Column[str] = str_column(length=100)
    price: Column[Decimal] = numeric_column(precision=10, scale=2)
    category_id: Column[int] = int_column()
    
    class Config:
        table_name = "products"
        verbose_name = "Product"
        description = "Product catalog"
        ordering = ["name", "-created_at"]
        
        indexes = [
            index("idx_name", "name"),
            index("idx_category_price", "category_id", "price"),
            index("idx_unique_name", "name", "category_id", unique=True)
        ]
        
        constraints = [
            constraint("price > 0", "ck_positive_price"),
            constraint("length(name) >= 3", "ck_name_length")
        ]
        
        db_options = multi_db_config(
            mysql={"engine": "InnoDB", "charset": "utf8mb4"},
            postgresql={"tablespace": "products_space"},
            generic={"comment": "Product information"}
        )
```

#### 智能实例操作高级用法

```python
# 分离实例的智能处理
detached_user = User(id=1, name="Alice", email="alice@example.com")
# save() 方法自动检测为 UPDATE 操作
await detached_user.save()

# 处理复合主键的分离实例
order_item = OrderItem(order_id=1, product_id=2, quantity=5)
await order_item.save()  # 智能检测复合主键

# 分离实例的删除和刷新
user_to_delete = User(id=1)
await user_to_delete.delete()  # 自动附加到会话后删除

user_to_refresh = User(id=2, name="Old Data")
await user_to_refresh.refresh()  # 从数据库重新加载

# 选择性字段刷新的高级用法
user = await User.objects.get(User.id == 1)
user.name = "Modified Locally"
user.email = "modified@example.com"
# 仅刷新 name 字段，保持 email 的本地修改
await user.refresh(fields=["name"])
```

#### 多数据库会话管理

```python
# 不同数据库的会话绑定
main_user = User(name="Main User")
await main_user.using(main_session).save()

analytics_user = User(name="Analytics User")
await analytics_user.using("analytics").save()

# 会话迁移和分离实例处理
detached_user = User(id=1, name="Migrated User")
await detached_user.using(main_session).save()      # merge() 到主数据库
await detached_user.using(analytics_session).save()  # merge() 到分析数据库

# 代理功能保持（包括分离实例）
proxy = detached_user.using(analytics_session)
proxy.name = "Updated Name"
await proxy.save()  # ModelProxy 自动处理引用更新
user_data = proxy.to_dict()
```

#### 高级验证配置

```python
from sqlobjects.validators import combine_validators, validate_email, validate_length

class User(ObjectModel):
    username: Column[str] = str_column(
        length=50,
        validators=[
            combine_validators(
                validate_length(3, 50),
                lambda x: x.isalnum() or ValidationError("Only alphanumeric characters allowed")
            )
        ]
    )
    
    email: Column[str] = str_column(
        length=100,
        validators=[validate_email()]
    )
    
    def validate(self):
        """复杂的模型级验证"""
        if self.username and self.email:
            if self.username.lower() in self.email.lower():
                raise ValidationError("Username cannot be part of email")
        
        if hasattr(self, 'age') and self.age:
            if self.age < 13 and not self.parent_consent:
                raise ValidationError("Users under 13 require parent consent")
    
    @classmethod
    def setup_validators(cls):
        """设置动态验证器"""
        cls.add_field_validator("username", cls.validate_unique_username)
    
    @staticmethod
    async def validate_unique_username(value):
        """异步验证器示例"""
        if value:
            existing = await User.objects.filter(User.username == value).exists()
            if existing:
                raise ValidationError("Username already exists")
```

#### 配置访问和元数据

```python
# 访问模型配置
table_name = User.get_table_name()           # "users"
verbose_name = User.get_verbose_name()       # "User"
description = User.get_description()         # 模型描述
config = User.get_config()                   # 完整配置对象
metadata = User.get_metadata()               # 所有元数据

# 动态配置检查
if User.get_config().has_indexes:
    print("Model has custom indexes")

if User.get_config().has_constraints:
    print("Model has custom constraints")
```
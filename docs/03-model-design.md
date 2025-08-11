# SQLObjects Model 设计说明文档

## 概述

SQLObjects Model 模块提供强大的模型基类和配置系统，支持 Django 风格的模型定义、验证系统、实例操作和灵活的数据库配置。通过
ObjectModel 基类和 ModelConfig 配置系统，为开发者提供完整的 ORM 模型解决方案。

## 核心特性

### 1. Django 风格的模型定义

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
        verbose_name = "user_table"                    # 可读名称
        description = "The table of user information"  # 模型描述

# 自动生成表名：user -> users（复数化）
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
            raise ValidationError("年龄不能为负数")
        if self.username and self.username.lower() == "admin":
            raise ValidationError("用户名不能为 admin")
    
    @classmethod
    def setup_validators(cls):
        """设置字段验证器"""
        cls.add_field_validator("username", cls.validate_username)
    
    @staticmethod
    def validate_username(value):
        if value and len(value.strip()) != len(value):
            raise ValidationError("用户名不能包含前后空格")

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
            generic={"comment": "产品信息表"}
        )
```

## 模块架构

### 核心组件

#### 1. ObjectModel 基类

继承自 SQLAlchemy DeclarativeBase 和 ModelMixin，提供完整的模型功能：

```python
class ObjectModel(DeclarativeBase, ModelMixin):
    """模型基类，提供配置支持和通用功能"""
    
    __abstract__ = True
    _config_cache: dict[type, ModelConfig] = {}
    
    def __init_subclass__(cls, **kwargs):
        """子类初始化时处理配置和设置"""
        cls._process_config()      # 处理配置
        cls._setup_validators()    # 设置验证器
        super().__init_subclass__(**kwargs)
    
    @classmethod
    def _process_config(cls):
        """处理和应用模型配置"""
        parser = ConfigParser()
        configs = [parser.parse_class_attributes(cls)]
        
        # 解析 Config 内部类
        config_class = getattr(cls, "Config", None)
        if config_class:
            configs.append(parser.parse_config_class(config_class))
        
        # 合并配置并应用
        merged_config = parser.merge_configs(*configs)
        cls._apply_config(merged_config)
```

#### 2. ModelMixin 实例方法

提供模型实例的验证、保存、删除等操作方法：

```python
class ModelMixin(SignalMixin):
    """模型实例方法混入类"""
    
    # 验证方法
    def validate_fields(self, fields: list[str] | None = None) -> None:
        """字段级验证"""
        error_collector = ValidationErrorCollector()
        field_names = fields or self._get_field_names()
        
        for field_name in field_names:
            validators = self._get_all_validators(field_name)
            value = getattr(self, field_name, None)
            for validator in validators:
                try:
                    validator(value)
                except ValidationError as e:
                    error_collector.add_error(field_name, e.message)
        
        error_collector.raise_if_errors()
    
    def validate(self) -> None:
        """模型级验证钩子，子类可重写"""
        pass
    
    def validate_all(self, fields: list[str] | None = None) -> None:
        """完整验证：字段级 + 模型级"""
        self.validate_fields(fields)
        if fields is None:
            self.validate()
    
    # 实例操作方法
    async def save(self, session=None, commit=False, validate=True):
        """保存模型实例"""
        session = session or SessionContextManager.get_session()
        
        if validate:
            self.validate_all()
        
        # 发送信号
        context = SignalContext(operation=Operation.SAVE, session=session, instance=self)
        await self._emit_signal("before", context)
        
        session.add(self)
        if commit:
            await session.commit()
            await session.refresh(self)
        else:
            await session.flush()
        
        await self._emit_signal("after", context)
        return self
    
    async def delete(self, session=None, commit=False):
        """删除模型实例"""
        session = session or SessionContextManager.get_session()
        
        context = SignalContext(operation=Operation.DELETE, session=session, instance=self)
        await self._emit_signal("before", context)
        
        await session.delete(self)
        if commit:
            await session.commit()
        else:
            await session.flush()
        
        await self._emit_signal("after", context)
```

#### 3. ModelConfig 配置系统

完整的模型配置数据类，支持所有配置选项：

```python
@dataclass
class ModelConfig:
    """模型配置数据类"""
    
    # 基础配置
    table_name: str | None = None
    ordering: list[str] = field(default_factory=list)
    abstract: bool = False
    
    # 数据库结构
    indexes: list[Index] = field(default_factory=list)
    constraints: list[CheckConstraint | UniqueConstraint] = field(default_factory=list)
    
    # 元数据
    verbose_name: str | None = None
    verbose_name_plural: str | None = None
    description: str | None = None
    
    # 数据库特定配置
    db_options: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    # 自定义配置
    custom: dict[str, Any] = field(default_factory=dict)
```

#### 4. ConfigParser 配置解析器

负责解析和合并来自不同源的配置：

```python
class ConfigParser:
    """配置解析器"""
    
    def parse_config_class(self, config_class: type) -> ModelConfig:
        """解析 Config 内部类"""
        config = ModelConfig()
        
        # 解析所有配置属性
        config.table_name = getattr(config_class, "table_name", None)
        config.ordering = getattr(config_class, "ordering", [])
        config.indexes = getattr(config_class, "indexes", [])
        # ... 其他属性
        
        return config
    
    def parse_class_attributes(self, model_class: type) -> ModelConfig:
        """解析 SQLAlchemy 类属性"""
        config = ModelConfig()
        
        config.table_name = getattr(model_class, "__tablename__", None)
        config.abstract = getattr(model_class, "__abstract__", False)
        
        # 解析 __table_args__
        table_args = getattr(model_class, "__table_args__", None)
        if table_args:
            self._parse_table_args(table_args, config)
        
        return config
    
    def merge_configs(self, *configs: ModelConfig) -> ModelConfig:
        """合并多个配置，后面的配置优先级更高"""
        merged = ModelConfig()
        
        for config in configs:
            # 基础配置：后面覆盖前面
            if config.table_name:
                merged.table_name = config.table_name
            
            # 列表配置：合并所有项
            merged.indexes.extend(config.indexes)
            merged.constraints.extend(config.constraints)
            
            # 字典配置：深度合并
            for db_name, db_config in config.db_options.items():
                if db_name not in merged.db_options:
                    merged.db_options[db_name] = {}
                merged.db_options[db_name].update(db_config)
        
        return merged
```

### 数据库配置工具

#### 便捷的配置函数

提供简化的索引、约束和数据库配置函数：

```python
# 索引创建
def index(name: str | None = None, *fields: str, unique: bool = False, **kwargs) -> Index:
    """创建索引"""
    if name is None:
        field_part = "_".join(fields)
        prefix = "uq" if unique else "idx"
        name = f"{prefix}_{field_part}"
    
    return Index(name, *fields, unique=unique, **kwargs)

# 约束创建
def constraint(condition: str, name: str | None = None, **kwargs) -> CheckConstraint:
    """创建检查约束"""
    if name is None:
        name = f"ck_{hash(condition) % 10000}"
    
    return CheckConstraint(condition, name=name, **kwargs)

def unique(*fields: str, name: str | None = None, **kwargs) -> UniqueConstraint:
    """创建唯一约束"""
    if name is None:
        field_part = "_".join(fields)
        name = f"uq_{field_part}"
    
    return UniqueConstraint(*fields, name=name, **kwargs)
```

#### 数据库特定配置

支持 MySQL、PostgreSQL、SQLite 的快捷配置：

```python
# MySQL 配置
def mysql_config(
    engine: str = "InnoDB",
    charset: str = "utf8mb4",
    row_format: str | None = None,
    **kwargs
) -> dict[str, dict[str, Any]]:
    """MySQL 数据库配置"""
    config = {"engine": engine, "charset": charset}
    if row_format:
        config["row_format"] = row_format
    config.update(kwargs)
    return {"mysql": config}

# PostgreSQL 配置
def postgresql_config(
    tablespace: str | None = None,
    fillfactor: int | None = None,
    parallel_workers: int | None = None,
    **kwargs
) -> dict[str, dict[str, Any]]:
    """PostgreSQL 数据库配置"""
    config = {}
    if tablespace:
        config["tablespace"] = tablespace
    if fillfactor:
        config["fillfactor"] = fillfactor
    config.update(kwargs)
    return {"postgresql": config}

# 多数据库配置
def multi_db_config(
    mysql: dict | None = None,
    postgresql: dict | None = None,
    sqlite: dict | None = None,
    generic: dict | None = None
) -> dict[str, dict[str, Any]]:
    """多数据库配置"""
    config = {}
    if mysql:
        config["mysql"] = mysql
    if postgresql:
        config["postgresql"] = postgresql
    if sqlite:
        config["sqlite"] = sqlite
    if generic:
        config["generic"] = generic
    return config
```

### 与其他模块的集成

#### 与 objects 模块的集成

ObjectModel 自动为非抽象模型提供 objects 管理器：

```python
# model 模块中的集成
class ObjectModel(DeclarativeBase, ModelMixin):
    def __init_subclass__(cls, **kwargs):
        cls._process_config()
        cls._setup_validators()
        
        # 为非抽象模型添加 objects 管理器
        if not cls._is_abstract() and not hasattr(cls, "objects"):
            cls.objects = ObjectsDescriptor(cls)
        
        super().__init_subclass__(**kwargs)

# 使用效果
class User(ObjectModel):
    name: Column[str] = str_column()

# User.objects 自动可用
users = await User.objects.all()
```

#### 与 validators 模块的集成

ModelMixin 集成验证系统，支持字段验证器和模型验证：

```python
# model 模块中的验证集成
class ModelMixin:
    def _get_column_validators(self, field_name: str) -> list:
        """获取字段的列验证器"""
        validators = []
        
        if hasattr(self.__class__, field_name):
            field_attr = getattr(self.__class__, field_name)
            
            # 从字段定义中获取验证器
            if hasattr(field_attr, "_sqlobjects_validators"):
                validators = field_attr._sqlobjects_validators or []
            elif hasattr(field_attr, "column") and hasattr(field_attr.column, "info"):
                if "_validators" in field_attr.column.info:
                    validators = field_attr.column.info["_validators"]
        
        return validators
```

#### 与 exceptions 模块的集成

ModelMixin 使用 exceptions 模块进行验证错误处理：

```python
# model 模块中使用异常系统
from .exceptions import ValidationError, ValidationErrorCollector

class ModelMixin:
    def validate_fields(self, fields: list[str] | None = None) -> None:
        """字段级验证，使用错误收集器"""
        error_collector = ValidationErrorCollector()
        
        field_names = fields or self._get_field_names()
        
        for field_name in field_names:
            validators = self._get_all_validators(field_name)
            value = getattr(self, field_name, None)
            
            for validator in validators:
                try:
                    validator(value)
                except ValidationError as e:
                    error_collector.add_error(field_name, e.message)
                except Exception as e:
                    error_collector.add_error(field_name, f"Validation error: {e}")
        
        error_collector.raise_if_errors()
```

#### 与 signals 模块的集成

ModelMixin 继承 SignalMixin，支持模型操作信号：

```python
# model 模块中的信号集成
class ModelMixin(SignalMixin):
    async def save(self, session=None, commit=False, validate=True):
        # 发送保存前信号
        context = SignalContext(operation=Operation.SAVE, session=session, instance=self)
        await self._emit_signal("before", context)
        
        # 执行保存操作
        session.add(self)
        if commit:
            await session.commit()
        
        # 发送保存后信号
        await self._emit_signal("after", context)
```

#### 模块职责分离

- **model.py**: 负责模型基类、实例方法、配置应用、验证器集成
- **config.py**: 负责配置系统、配置解析、数据库特定配置
- **objects.py**: 负责对象管理器、查询接口
- **validators.py**: 负责验证逻辑、验证器实现
- **exceptions.py**: 负责异常定义、错误处理
- **集成点**: 通过继承、描述符和配置系统实现模块协作

## API 参考

### 模型定义

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import str_column, int_column
from sqlobjects.config import index, constraint, mysql_config

class User(ObjectModel):
    # 字段定义
    name: Column[str] = str_column(length=50)
    email: Column[str] = str_column(length=100, unique=True)
    age: Column[int] = int_column()
    
    # 配置类
    class Config:
        table_name = "users"
        ordering = ["-created_at"]
        verbose_name = "用户"
        verbose_name_plural = "用户列表"
        description = "系统用户模型"
        
        indexes = [
            index("idx_email", "email", unique=True),
            index("idx_name_age", "name", "age")
        ]
        
        constraints = [
            constraint("age >= 0", "ck_age_positive")
        ]
        
        db_options = mysql_config(engine="InnoDB", charset="utf8mb4")
        
        custom = {
            "cache_timeout": 300,
            "enable_audit": True
        }
```

### 验证系统

```python
# 字段验证器
from sqlobjects.validators import EmailValidator, LengthValidator

class User(ObjectModel):
    username: Column[str] = str_column(
        validators=[LengthValidator(min_length=3, max_length=50)]
    )
    email: Column[str] = str_column(validators=[EmailValidator()])
    
    # 模型级验证
    def validate(self):
        if self.age < 0:
            raise ValidationError("年龄不能为负数")
    
    # 类级验证器设置
    @classmethod
    def setup_validators(cls):
        cls.add_field_validator("username", cls.validate_username)
    
    @staticmethod
    def validate_username(value):
        if value and "admin" in value.lower():
            raise ValidationError("用户名不能包含 admin")

# 验证使用
user = User(username="john", email="john@example.com", age=25)
user.validate_fields(["username", "email"])  # 验证特定字段
user.validate_all()                          # 完整验证
```

### 实例操作

```python
# 创建和保存
user = User(name="John", email="john@example.com")
await user.save()                                              # 保存（自动验证）
await user.save(validate=False)                                # 跳过验证保存
await user.save(commit=True)                                   # 保存并提交事务
                                                               
# 删除                                                           
await user.delete()                                            # 删除
await user.delete(commit=True)                                 # 删除并提交事务
                                                               
# 刷新                                                           
await user.refresh()                                           # 从数据库刷新
await user.refresh_from_db(["name", "email"])                  # 刷新特定字段

# 数据转换
user_dict = user.to_dict()                                     # 转换为字典
user_dict = user.to_dict(include=["name", "email"])            # 包含特定字段
user_dict = user.to_dict(exclude=["password"])                 # 排除特定字段

# 从字典创建
user_data = {"name": "Alice", "email": "alice@example.com"}
user = User.from_dict(user_data)                               # 从字典创建（自动验证）
user = User.from_dict(user_data, validate=False)               # 跳过验证创建
```

### 配置工具

```python
from sqlobjects.config import (
    index, constraint, unique,
    mysql_config, postgresql_config, multi_db_config,
    high_performance_mysql, compressed_mysql
)

# 索引创建
indexes = [
    index("idx_name", "name"),                                            # 普通索引
    index("idx_email", "email", unique=True),                             # 唯一索引
    index("idx_composite", "category", "status"),                         # 复合索引
    index("idx_partial", "status", postgresql_where="status = 'active'")  # 部分索引
]

# 约束创建
constraints = [
    constraint("price > 0", "ck_price_positive"),
    constraint("age BETWEEN 0 AND 150", "ck_age_range"),
    unique("email"),
    unique("first_name", "last_name", name="uq_full_name")
]

# 数据库配置
db_options = multi_db_config(
    mysql={"engine": "InnoDB", "charset": "utf8mb4", "row_format": "DYNAMIC"},
    postgresql={"tablespace": "fast_storage", "fillfactor": 90},
    sqlite={"without_rowid": True},
    generic={"comment": "用户数据表"}
)

# 预设配置
high_perf_mysql = high_performance_mysql()
compressed_mysql = compressed_mysql(key_block_size=8)
```

### 元数据访问

```python
# 获取模型配置
config = User.get_config()
print(config.table_name)        # 表名
print(config.verbose_name)      # 可读名称

# 获取表信息
table_name = User.get_table_name()
verbose_name = User.get_verbose_name()
verbose_plural = User.get_verbose_name_plural()
description = User.get_description()

# 获取所有元数据
metadata = User.get_metadata()
# {
#     "verbose_name": "用户",
#     "verbose_name_plural": "用户列表", 
#     "description": "系统用户模型"
# }
```

## 使用指南

### 基础用法

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import str_column, int_column, datetime_column
from sqlobjects.validators import EmailValidator
from datetime import datetime

# 基础模型定义
class User(ObjectModel):
    name: Column[str] = str_column(length=50)
    email: Column[str] = str_column(
        length=100, 
        unique=True,
        validators=[EmailValidator()]
    )
    age: Column[int] = int_column()
    created_at: Column[datetime] = datetime_column(default=datetime.now)
    
    # 简单配置
    class Config:
        ordering = ["-created_at"]
        verbose_name = "用户"

# 基础使用
# 创建用户
user = User(name="John Doe", email="john@example.com", age=25)
await user.save()

# 验证
try:
    user.validate_all()
    print("验证通过")
except ValidationError as e:
    print(f"验证失败: {e.message}")

# 数据转换
user_data = user.to_dict()
new_user = User.from_dict(user_data)

# 刷新数据
await user.refresh()
```

### 高级用法

```python
from sqlobjects.config import (
    index, constraint, unique, multi_db_config,
    high_performance_mysql, analytics_postgresql
)
from sqlobjects.validators import ChoicesValidator, LengthValidator, RangeValidator, combine_validators

# 复杂模型定义
class Product(ObjectModel):
    name: Column[str] = str_column(
        length=100,
        validators=[LengthValidator(min_length=2, max_length=100)]
    )
    price: Column[Decimal] = numeric_column(
        precision=10, 
        scale=2,
        validators=[RangeValidator(min_value=0)]
    )
    category: Column[str] = str_column(length=50)
    status: Column[str] = str_column(
        length=20,
        validators=[ChoicesValidator(["active", "inactive", "discontinued"])]
    )
    description: Column[str] = str_column(type="text")
    created_at: Column[datetime] = datetime_column(default=datetime.now)
    updated_at: Column[datetime] = datetime_column(default=datetime.now)
    
    class Config:
        table_name = "products"
        ordering = ["-created_at", "name"]
        verbose_name = "产品"
        verbose_name_plural = "产品列表"
        description = "产品信息管理模型"
        
        # 复杂索引配置
        indexes = [
            index("idx_name", "name"),
            index("idx_category_status", "category", "status"),
            index("idx_price_range", "price"),
            index("idx_active_products", "status", "created_at", 
                  postgresql_where="status = 'active'"),
            index("idx_search", "name", "description", 
                  postgresql_using="gin")
        ]
        
        # 约束配置
        constraints = [
            constraint("price > 0", "ck_price_positive"),
            constraint("length(name) > 0", "ck_name_not_empty"),
            unique("name", "category", name="uq_name_category")
        ]
        
        # 多数据库优化配置
        db_options = multi_db_config(
            mysql={
                "engine": "InnoDB",
                "charset": "utf8mb4",
                "row_format": "DYNAMIC",
                "stats_persistent": True
            },
            postgresql={
                "tablespace": "fast_storage",
                "fillfactor": 90,
                "parallel_workers": 4,
                "autovacuum_vacuum_scale_factor": 0.1
            },
            generic={
                "comment": "产品信息表，包含价格、分类等核心信息"
            }
        )
        
        # 自定义配置
        custom = {
            "cache_timeout": 600,
            "enable_search_index": True,
            "audit_fields": ["price", "status"],
            "notification_fields": ["status"]
        }
    
    # 复杂验证逻辑
    def validate(self):
        """模型级验证"""
        # 价格验证
        if self.price and self.price <= 0:
            raise ValidationError("产品价格必须大于0")
        
        # 状态变更验证
        if hasattr(self, '_original_status'):
            if self._original_status == "discontinued" and self.status != "discontinued":
                raise ValidationError("已停产的产品不能重新激活")
        
        # 分类和状态组合验证
        if self.category == "limited" and self.status == "active":
            if not self.description or len(self.description) < 50:
                raise ValidationError("限量产品必须提供详细描述（至少50字符）")
    
    @classmethod
    def setup_validators(cls):
        """设置字段验证器"""
        # 组合验证器
        name_validator = combine_validators(
            LengthValidator(min_length=2, max_length=100),
            cls.validate_name_format
        )
        cls.add_field_validator("name", name_validator)
        
        # 价格验证器
        cls.add_field_validator("price", cls.validate_price_range)
    
    @staticmethod
    def validate_name_format(value):
        """产品名称格式验证"""
        if value and not value.strip():
            raise ValidationError("产品名称不能为空白")
        if value and any(char in value for char in ['<', '>', '&']):
            raise ValidationError("产品名称不能包含特殊字符")
    
    @staticmethod
    def validate_price_range(value):
        """价格范围验证"""
        if value is not None:
            if value < 0:
                raise ValidationError("价格不能为负数")
            if value > 999999.99:
                raise ValidationError("价格不能超过999999.99")

# 抽象模型
class TimestampedModel(ObjectModel):
    created_at: Column[datetime] = datetime_column(default=datetime.now)
    updated_at: Column[datetime] = datetime_column(default=datetime.now)
    
    class Config:
        abstract = True  # 抽象模型，不创建数据库表

# 继承抽象模型
class Article(TimestampedModel):
    title: Column[str] = str_column(length=200)
    content: Column[str] = str_column(type="text")
    author_id: Column[int] = int_column()
    
    class Config:
        table_name = "articles"
        ordering = ["-created_at"]
        
        indexes = [
            index("idx_title", "title"),
            index("idx_author_created", "author_id", "created_at")
        ]

# 高性能配置示例
class AnalyticsData(ObjectModel):
    event_name: Column[str] = str_column(length=100)
    user_id: Column[int] = int_column()
    timestamp: Column[datetime] = datetime_column()
    properties: Column[dict] = json_column()
    
    class Config:
        table_name = "analytics_data"
        
        # 分析型数据库优化
        db_options = multi_db_config(
            mysql=compressed_mysql(key_block_size=4),  # 压缩存储
            postgresql=analytics_postgresql(parallel_workers=8),  # 分析优化
            generic={"comment": "用户行为分析数据"}
        )
        
        indexes = [
            index("idx_event_time", "event_name", "timestamp"),
            index("idx_user_time", "user_id", "timestamp"),
            index("idx_properties", "properties", postgresql_using="gin")
        ]

# 使用示例
async def product_management_example():
    """产品管理示例"""
    
    # 创建产品
    product = Product(
        name="智能手机",
        price=Decimal("2999.99"),
        category="electronics",
        status="active",
        description="最新款智能手机，配备先进的处理器和摄像头"
    )
    
    # 验证和保存
    try:
        await product.save(commit=True)
        print("产品创建成功")
    except ValidationError as e:
        print(f"验证失败: {e.message}")
        if e.is_multiple:
            for field, errors in e.field_errors.items():
                print(f"  {field}: {', '.join(errors)}")
    
    # 更新产品
    product.price = Decimal("2799.99")
    product.status = "sale"
    
    try:
        await product.save(commit=True)
        print("产品更新成功")
    except ValidationError as e:
        print(f"更新失败: {e.message}")
    
    # 获取产品元数据
    metadata = Product.get_metadata()
    print(f"模型信息: {metadata}")
    
    # 数据转换
    product_dict = product.to_dict(exclude=["created_at", "updated_at"])
    print(f"产品数据: {product_dict}")
    
    # 从字典创建新产品
    new_product_data = {
        "name": "平板电脑",
        "price": "1999.99",
        "category": "electronics",
        "status": "active",
        "description": "轻薄便携的平板电脑"
    }
    
    new_product = Product.from_dict(new_product_data)
    await new_product.save(commit=True)
    
    print("产品管理示例完成")

# 运行示例
# await product_management_example()
```
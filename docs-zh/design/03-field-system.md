# SQLObjects 字段系统设计文档

## 概述

SQLObjects 字段系统采用统一的 Column 描述符架构，支持数据库字段和关系字段的统一定义。通过 TypeRegistry
类型注册系统、ColumnAttribute 增强属性和综合参数系统，提供类型安全、性能优化和代码生成控制功能。

## 核心特性

### 1. 统一 Column 描述符架构

Column 描述符支持数据库字段和关系字段的统一定义，通过 __set_name__ 自动设置：

```python
class User(ObjectModel):
    # 数据库字段 - 使用 ColumnAttribute
    name: Column[str] = StringColumn(length=50)
    age: Column[int] = IntegerColumn()
    email: Column[str] = StringColumn(length=100, unique=True)
    is_active: Column[bool] = BooleanColumn(default=True)
    metadata: Column[dict] = JsonColumn(default=dict)
    
    # 关系字段 - 使用 RelationshipDescriptor
    posts: Column[List["Post"]] = relationship("Post", foreign_keys="Post.author_id")

# Column 描述符双重访问模式：
# - 类访问: User.name 返回 ColumnAttribute 用于查询
# - 实例访问: user.name 返回字段值，支持类型转换

# 自动类型推断 - 使用 Auto 类型占位符
id: Column[int] = column(type=Auto(), primary_key=True)  # ModelProcessor 时替换
name: Column[str] = column(type=Auto())  # 使用 Auto() 实例进行类型推断

# 综合参数系统
username: Column[str] = column(
    type="string", length=50, unique=True,
    # 增强功能参数
    validators=[validate_length(3, 50)],
    default_factory=None, insert_default=None,
    # 性能优化参数
    deferred=False, deferred_group=None, active_history=False,
    # 代码生成参数
    init=True, repr=True, compare=False, hash=None, kw_only=False
)
```

### 2. 函数表达式链式调用

支持字段上的链式函数调用，提供类型特定的操作方法：

```python
# 字符串函数链式调用
User.name.upper().trim()
User.email.lower().substring(1, 10)

# 数值函数链式调用
User.age.abs().round(2)
User.salary.sum().avg()

# 日期时间函数链式调用
User.birth_date.year().month()
User.created_at.age_in_years()
```

### 3. 数据验证系统

完整的字段级和模型级验证，支持内置和自定义验证器：

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(
        length=50,
        validators=[
            LengthValidator(min_length=3, max_length=50),
            RegexValidator(r"^[a-zA-Z0-9_]+$")
        ]
    )
    
    email: Column[str] = StringColumn(
        length=100,
        validators=[EmailValidator()]
    )
    
    def validate(self):
        if self.age < 0:
            raise ValidationError("Age cannot be negative")
```

### 4. 性能优化功能

字段级性能优化，支持延迟加载和内存管理：

```python
class User(ObjectModel):
    # 延迟加载大字段
    bio: Column[str] = TextColumn(deferred=True)
    profile_image: Column[bytes] = BinaryColumn(deferred=True, deferred_group="media")
    
    # 活动历史跟踪
    important_field: Column[str] = StringColumn(active_history=True)
    
    # 代码生成控制
    internal_id: Column[str] = StringColumn(init=False, repr=False)
    api_key: Column[str] = StringColumn(repr=False, compare=False)
```

## 模块架构

### 核心组件

**描述符层**

- **Column**: 统一字段描述符，支持数据库字段和关系字段的统一定义
- **ColumnAttribute**: 增强 SQLAlchemy Column，集成验证、性能优化和代码生成控制
- **RelationshipDescriptor**: 关系字段描述符，处理关系定义和访问

**类型系统层**

- **TypeRegistry**: 全局类型注册系统，支持延迟初始化和构造参数自动提取
- **Auto**: 类型推断占位符，在 ModelProcessor 处理时替换为具体类型
- **Enhanced Types**: SQLAlchemy 类型 + Comparator，支持数据库函数链式调用

**函数表达式层**

- **ColumnFunctionMixin**: 字段函数混入，为 Column 描述符提供函数调用
- **ColumnAttributeFunctionMixin**: ColumnAttribute 函数混入，支持数据库函数
- **Comparator Classes**: 类型特定的比较器，提供丰富的数据库函数

### 设计理念

**统一描述符**: Column 描述符统一处理数据库字段和关系字段，简化 API
**参数分类**: 将参数分为 SQLAlchemy、增强功能、性能优化和代码生成四类
**智能默认**: 根据字段特性自动推断 init/repr/compare 参数
**类型注册**: 全局 TypeRegistry 支持类型别名和构造参数自动提取
**函数集成**: 通过 Mixin 和 Comparator 为字段提供数据库函数调用
**性能优先**: 内置延迟加载、历史跟踪和字段缓存功能

### 与其他模块的集成

**核心架构模块**: 通过 ModelProcessor 处理字段定义
**数据操作模块**: 提供字段表达式和查询条件
**扩展功能模块**: 集成验证器和异常处理系统

## API 参考

### 字段定义类

```python
# 核心字段函数
column(
    type="auto", name=None,
    # SQLAlchemy 参数
    primary_key=False, nullable=True, default=None, index=False, unique=False,
    autoincrement="auto", doc=None, key=None, onupdate=None, comment=None,
    system=False, server_default=None, server_onupdate=None, quote=None, info=None,
    # 增强功能参数
    default_factory=None, validators=None, insert_default=None,
    # 性能优化参数
    deferred=False, deferred_group=None, active_history=False, deferred_raiseload=None,
    # 代码生成参数
    init=None, repr=None, compare=None, hash=None, kw_only=None,
    **kwargs  # 类型特定参数
)

# Column 类型类
StringColumn(length=None, **kwargs)
TextColumn(**kwargs)
IntegerColumn(type="integer", **kwargs)  # type: "integer"|"bigint"|"smallint"|"int"
FloatColumn(type="float", **kwargs)     # type: "float"|"double"
NumericColumn(precision=None, scale=None, **kwargs)
BooleanColumn(**kwargs)
DateTimeColumn(type="datetime", **kwargs)  # type: "datetime"|"date"|"time"|"interval"
BinaryColumn(length=None, **kwargs)
UuidColumn(**kwargs)
JsonColumn(**kwargs)
ArrayColumn(item_type, dimensions=1, **kwargs)
EnumColumn(enum_class, **kwargs)
IdentityColumn(start=1, increment=1, minvalue=None, maxvalue=None, cycle=False, cache=None, **kwargs)
ComputedColumn(sqltext, persisted=None, column_type="auto", **kwargs)
```

### 函数表达式

```python
# 字符串函数
field.upper() / field.lower() / field.trim()
field.substring(start, length) / field.length()
field.concat(*args) / field.replace(old, new)
field.left(length) / field.right(length)
field.lpad(length, fill_char) / field.rpad(length, fill_char)
field.ltrim(chars) / field.rtrim(chars)
field.split_part(delimiter, field) / field.position(substring)
field.reverse() / field.md5()
field.regexp_replace(pattern, replacement, flags)

# 数值函数
field.abs() / field.round(precision) / field.ceil() / field.floor()
field.sqrt() / field.power(exponent) / field.mod(divisor)
field.sign() / field.trunc(precision) / field.exp() / field.ln() / field.log(base)
field.sum() / field.avg() / field.count_distinct()

# 日期时间函数
field.extract(field) / field.year() / field.month() / field.day()
field.hour() / field.minute()
field.date_trunc(precision) / field.age_in_years() / field.age_in_months()
field.days_between(end_date) / field.to_char(format_str) / field.add_days(days)

# JSON 函数
field.extract_path(path) / field.extract_text(path)

# 通用函数
field.cast(type_, **kwargs) / field.coalesce(*values) / field.nullif(value)
field.case(*conditions, else_=None) / field.greatest(*args) / field.least(*args)
```

### 快捷函数

```python
# 身份列和计算列
identity(start=1, increment=1, minvalue=None, maxvalue=None, cycle=False, cache=None, **kwargs)
computed(sqltext, persisted=None, column_type="auto", **kwargs)

# 外键约束
foreign_key(reference, type="integer", nullable=True, **kwargs)

# 类型系统
register_field_type(field_type, type_name, comparator=None, aliases=None, default_params=None)
create_type_instance(type_name, kwargs)
get_type_definition(type_name)

# SQLAlchemy 集成
ForeignKey(reference, **kwargs)  # 直接使用 SQLAlchemy ForeignKey

# 字段兼容性
is_field_definition(attr)
get_column_from_field(field_def)

# 验证和元数据
get_field_validators(model_class, field_name)
get_model_metadata(model_class)
```

### 类型注册系统

```python
# TypeRegistry 核心方法
registry = TypeRegistry()
registry.register_type(field_type, name, comparator, aliases, default_params)
registry.get_type_config(name)
registry.create_enhanced_type(name, **params)

# Auto 类型
Auto()  # 自动类型推断占位符

# ColumnAttribute 增强功能
attr.validate_value(value, field_name)
attr.get_effective_default()
attr.get_field_metadata()
attr.get_codegen_params()
```

## 使用指南

### 基础用法

```python
# 基础字段定义
class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)
    age: Column[int] = IntegerColumn()
    email: Column[str] = StringColumn(length=100, unique=True)
    is_active: Column[bool] = BooleanColumn(default=True)

# 字段函数调用
users = await User.objects.filter(
    User.name.upper() == "JOHN",
    User.age >= 18
).all()

# 基础验证
class Product(ObjectModel):
    name: Column[str] = StringColumn(
        length=100,
        validators=[LengthValidator(min_length=1)]
    )
    price: Column[Decimal] = NumericColumn(
        precision=10, scale=2,
        validators=[RangeValidator(min_value=0)]
    )
```

### 高级用法

```python
# 复杂字段配置
class User(ObjectModel):
    username: Column[str] = column(
        type="string", length=50,
        nullable=False, unique=True,
        validators=[validate_length(3, 50), validate_regex(r"^[a-zA-Z0-9_]+$")],
        init=True, repr=True, compare=True
    )
    
    password_hash: Column[str] = column(
        type="string", length=255,
        nullable=False,
        repr=False  # 不在 __repr__ 中显示
    )
    
    created_at: Column[datetime] = column(
        type="datetime",
        default_factory=datetime.now,
        init=False  # 不在 __init__ 中包含
    )
    
    # 性能优化字段
    bio: Column[str] = column(
        type="text",
        deferred=True,  # 延迟加载
        deferred_group="details"
    )
    
    # 身份列和计算列
    id: Column[int] = identity()
    full_name: Column[str] = computed(
        "first_name || ' ' || last_name",
        column_type="string"
    )
    
    # 外键字段
    author_id: Column[int] = foreign_key("users.id")
    category_id: Column[int] = foreign_key("categories.id", nullable=False, index=True)

# 链式函数调用
users = await User.objects.annotate(
    display_name=User.first_name.concat(" ", User.last_name).upper(),
    email_domain=User.email.split_part("@", 2),
    age_years=User.birth_date.age_in_years(),
    salary_rounded=User.salary.round(2)
).filter(
    User.name.upper().like("ADMIN%"),
    User.birth_date.age_in_years() >= 18,
    User.salary.abs() > 5000
).all()

# 子查询使用
avg_salary = User.objects.aggregate(
    avg_salary=func.avg(User.salary)
).subquery()

high_earners = await User.objects.filter(
    User.salary > avg_salary
).annotate(
    salary_ratio=User.salary / avg_salary
).all()

# 自定义验证器
def validate_password_strength(value):
    if len(value) < 8:
        raise ValidationError("Password too short")
    if not any(c.isupper() for c in value):
        raise ValidationError("Password must contain uppercase")

class User(ObjectModel):
    password: Column[str] = column(
        type="string", length=255,
        validators=[validate_password_strength]
    )
    
    def validate(self):
        if self.username.lower() in self.email.lower():
            raise ValidationError("Username cannot be part of email")

# 类型注册和自定义类型
from sqlalchemy import INET

register_field_type(
    INET, 'inet',
    aliases=['ip_address'],
    default_params={}
)

class Server(ObjectModel):
    ip_address: Column[str] = column(type="inet")
    
# 字段元数据访问
metadata = User.username.get_field_metadata()
validators = get_field_validators(User, 'username')
model_info = get_model_metadata(User)
```
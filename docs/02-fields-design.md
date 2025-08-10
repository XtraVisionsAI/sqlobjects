# SQLObjects Fields 设计说明文档

## 概述

SQLObjects Fields 模块提供统一的字段定义系统，支持链式函数调用、类型安全和丰富的数据库操作功能。完全兼容 SQLAlchemy 语法。

## 核心特性

### 1. 链式函数调用

通过增强的 Comparator 类，字段支持 SQLAlchemy func 方法的链式调用：

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import Column, str_column, int_column, datetime_column

class User(ObjectModel):
    name: Column[str] = str_column(length=50)
    age: Column[int] = int_column()
    birth_date: Column[datetime] = datetime_column()

# 链式函数调用示例
query = User.objects.annotate(
    name_upper=User.name.upper(),                          # 字符串转大写
    name_prefix=User.name.trim().upper().substring(1, 3),  # 链式操作
    age_years=User.birth_date.age_in_years(),              # 计算年龄
    abs_age=User.age.abs().round(0)                        # 数值操作
).filter(
    User.name.upper().like("ADMIN%"),                      # 条件查询
    User.birth_date.age_in_years() >= 18                   # 年龄筛选
)
```

### 2. 类型系统

所有快捷函数使用增强类型，提供丰富的功能：

```python
# 字符串功能
User.name.matches(r"^admin")            # 正则匹配
User.name.upper().trim()                # 链式函数调用
User.name.length_between(3, 50)         # 长度范围检查

# 数值功能  
User.age.abs().round(2)                 # 链式函数调用
User.salary.sum().avg()                 # 聚合函数链式调用

# 日期时间功能
User.birth_date.is_today()              # 语义化方法
User.birth_date.year().month()          # 链式日期提取
User.created_at.age_in_years()          # 年龄计算

# JSON 功能
User.metadata.has_key("status")         # JSON 键检查
User.metadata.extract_text("$.name")    # JSON 路径提取
```

### 3. SQLAlchemy 语法兼容性

完全兼容 SQLAlchemy 语法，支持混合使用：

```python
# 语义化方法
User.objects.filter(
    User.birth_date.is_past(),          # 语义化方法
    User.age.between(18, 65),           # SQLAlchemy 方法
    User.name.upper().like("ADMIN%")    # 链式调用
)
```

## 模块架构

### 核心组件

#### 1. 增强类型系统

所有快捷函数使用增强类型，通过 `comparator_factory` 提供 SQLAlchemy func 方法的链式调用功能：

```python
# 增强的 SQLAlchemy 类型
class EnhancedString(String):
    comparator_factory = EnhancedStringComparator

class EnhancedInteger(Integer):
    comparator_factory = EnhancedIntegerComparator

class EnhancedDateTime(DateTime):
    comparator_factory = EnhancedDateTimeComparator

class EnhancedJSON(JSON):
    comparator_factory = EnhancedJSONComparator
```

#### 2. 链式调用系统

通过 `FunctionResult` 类和 Mixin 类实现链式调用：

```python
class FunctionResult:
    """函数调用结果，支持继续链式调用"""
    
    def __init__(self, expression):
        self.expression = expression
    
    def upper(self) -> 'FunctionResult':
        return FunctionResult(func.upper(self.expression))
    
    def trim(self) -> 'FunctionResult':
        return FunctionResult(func.trim(self.expression))
    
    # 支持操作符重载
    def __eq__(self, other):
        return self.expression == other

# Mixin 类提供特定类型的函数
class StringFunctionMixin:
    def upper(self) -> FunctionResult:
        return FunctionResult(func.upper(self._get_expression()))
    
    def trim(self) -> FunctionResult:
        return FunctionResult(func.trim(self._get_expression()))
```

#### 3. 类型注册系统

支持延迟初始化、LRU 缓存和自动参数提取：

```python
class TypeRegistry:
    """类型注册表，支持缓存和延迟加载"""
    
    def __init__(self):
        self._types: dict[str, TypeDefinition] = {}
        self._aliases: dict[str, str] = {
            "str": "string", "int": "integer", 
            "bool": "boolean", "decimal": "numeric"
        }
        self._initialized = False
    
    @lru_cache(maxsize=128)
    def get_type(self, name: str) -> TypeDefinition:
        """缓存类型查找，支持延迟初始化"""
        if not self._initialized:
            self._init_builtin_types()
        return self._types.get(self._resolve_alias(name))
```

#### 4. 参数处理系统

支持类型参数和列参数的自动分离，以及参数转换：

```python
# 类型定义结构
class TypeArgument(TypedDict):
    name: str
    type: type
    required: bool
    default: Any
    transform: NotRequired[Callable[[Any], Any]]  # 参数转换函数
    positional: NotRequired[bool]  # 位置参数标记

class TypeDefinition(TypedDict):
    type: type
    arguments: list[TypeArgument]

# 参数处理流程
def _get_type_params(type_def: TypeDefinition, kwargs: dict[str, Any]) -> dict[str, Any]:
    """提取类型构建参数，应用转换函数"""
    type_params = {}
    for key, value in kwargs.items():
        if key in type_param_names:
            arg_def = next(arg for arg in type_def["arguments"] if arg["name"] == key)
            if "transform" in arg_def and arg_def["transform"]:
                value = arg_def["transform"](value)  # 应用转换
            type_params[key] = value
    return type_params
```

### 与其他模块的集成

#### 与 expressions 模块的集成

Fields 模块与 expressions 模块紧密集成，实现字段函数系统和链式调用机制：

```python
# fields.py 导入 expressions 模块的函数系统
from .expressions import (
    DateTimeFunctionMixin, 
    FunctionResult, 
    NumericFunctionMixin, 
    StringFunctionMixin
)

# 增强类型使用 expressions 模块的 Mixin 类
class EnhancedStringComparator(String.Comparator, StringFunctionMixin):
    """字符串比较器，继承 expressions 模块的字符串函数"""
    pass

class EnhancedIntegerComparator(Integer.Comparator, NumericFunctionMixin):
    """数值比较器，继承 expressions 模块的数值函数"""
    pass

class EnhancedDateTimeComparator(DateTime.Comparator, DateTimeFunctionMixin):
    """日期时间比较器，继承 expressions 模块的日期时间函数"""
    pass
```

#### 统一的函数调用体验

通过集成，用户可以在字段上直接使用 expressions 模块的所有函数：

```python
# 字段链式调用使用 expressions 模块的 FunctionResult
User.name.upper().trim()                    # StringFunctionMixin 提供
User.age.abs().round(2)                     # NumericFunctionMixin 提供
User.created_at.year().month()              # DateTimeFunctionMixin 提供

# 类型转换使用 expressions 模块的通用函数
User.id.cast("string")                      # FunctionMixin 提供
User.nickname.coalesce(User.username)       # FunctionMixin 提供
```

#### 模块职责分离

- **fields.py**: 负责字段定义、类型系统、增强类型实现
- **expressions.py**: 负责函数系统、链式调用、表达式处理
- **集成点**: 通过 Mixin 类继承实现功能共享

## API 参考

### 基础字段函数

#### column()

核心列定义函数，支持所有 SQLAlchemy 参数和增强类型：

```python
from sqlobjects.fields import column

# 基础用法
id: Column[int] = column(type="integer", primary_key=True)
username: Column[str] = column(type="string", length=50, unique=True)
price: Column[Decimal] = column(type="numeric", precision=10, scale=2)
metadata: Column[dict] = column(type="json", default=dict)
external_id: Column[str] = column(type="uuid")

# 特殊类型参数处理
tags: Column[list[str]] = column(type="array", item_type="string", dimensions=1)
status: Column[MyEnum] = column(type="enum", enum_class=MyEnum)

# 验证器支持
username: Column[str] = column(
    type="string", 
    length=50, 
    validators=[validate_length(3, 50), validate_regex(r"^[a-zA-Z0-9_]+$")]
)
```

### 快捷函数

#### 字符串类型

```python
from sqlobjects.fields import str_column

# 基础字符串类型
name: Column[str] = str_column(length=100)
description: Column[str] = str_column(type="text")
code: Column[str] = str_column(type="char", length=10)  # 固定长度
content: Column[str] = str_column(type="varchar", length=500)

# 链式调用功能
# User.name.upper().trim()           # 字符串操作链式调用
# User.name.matches(r"^admin")        # 正则匹配
# User.name.length_between(3, 50)     # 长度范围检查
```

#### 数值类型

```python
from sqlobjects.fields import int_column, numeric_column

# 整数类型
id: Column[int] = int_column(primary_key=True)
big_number: Column[int] = int_column(type="bigint")
small_number: Column[int] = int_column(type="smallint")

# 数值类型
price: Column[Decimal] = numeric_column(precision=10, scale=2)
rate: Column[float] = numeric_column(type="float")
double_val: Column[float] = numeric_column(type="double")
percentage: Column[Decimal] = numeric_column(type="decimal", precision=5, scale=4)

# 链式调用功能
# User.age.abs().round(2)             # 数值操作链式调用
# User.salary.sum().avg()             # 聚合函数链式调用
# User.score.power(2).sqrt()          # 数学运算链式调用
```

#### 日期时间类型

```python
from sqlobjects.fields import datetime_column

# 日期时间类型
created_at: Column[datetime] = datetime_column()
birth_date: Column[date] = datetime_column(type="date")
start_time: Column[time] = datetime_column(type="time")
duration: Column[timedelta] = datetime_column(type="interval")

# 链式调用功能
# User.birth_date.is_today()           # 语义化方法
# User.birth_date.year().month()       # 链式日期提取
# User.created_at.age_in_years()       # 年龄计算
# User.birth_date.date_trunc("month")  # 日期截断
```

#### 其他核心类型

```python
from sqlobjects.fields import bool_column, json_column, uuid_column, binary_column, pickle_column

# 布尔类型
is_active: Column[bool] = bool_column(default=True)

# JSON 类型
metadata: Column[dict] = json_column(default=dict)
preferences: Column[dict] = json_column(default=dict)

# UUID 类型
external_id: Column[str] = uuid_column(unique=True)

# 二进制类型
file_data: Column[bytes] = binary_column(length=1024)
image_data: Column[bytes] = binary_column(type="varbinary", length=2048)

# Pickle 类型（Python 对象序列化）
settings: Column[dict] = pickle_column(default=dict)
cached_data: Column[Any] = pickle_column()

# 链式调用功能
# User.is_active.is_true()             # 布尔语义化方法
# User.metadata.has_key("status")      # JSON 键检查
# User.metadata.extract_text("$.name") # JSON 路径提取
# User.external_id.upper().trim()      # UUID 字符串操作
```

#### 特殊类型

```python
from sqlobjects.fields import array_column, enum_column

# 数组类型（PostgreSQL）
tags: Column[list[str]] = array_column("string")
ratings: Column[list[int]] = array_column("integer")
matrix: Column[list[list[float]]] = array_column("float", dimensions=2)
scores: Column[list[Decimal]] = array_column("numeric")

# 枚举类型
from enum import Enum
class Status(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"

status: Column[Status] = enum_column(Status, default=Status.ACTIVE)
priority: Column[Priority] = enum_column(Priority)
```

### SQLAlchemy 高级特性

```python
from sqlobjects.fields import (
    identity, computed, sequence, foreign_key, 
    created_at, updated_at, composite, column_property, synonym
)

# 自增主键
id: Column[int] = identity()                                  # 默认从1开始
product_id: Column[int] = identity(start=1000, increment=10)  # 自定义起始值

# 序列
order_number: Column[int] = sequence("order_seq", start=1000)

# 计算列（支持类型指定）
full_name: Column[str] = computed("first_name || ' ' || last_name", type="string")
total_amount: Column[Decimal] = computed("price * quantity", type="numeric")

# 外键
user_id: Column[int] = foreign_key("users.id")
department_id: Column[int] = foreign_key("departments.id", on_delete="SET NULL")

# 时间戳
created_at: Column[datetime] = created_at()
updated_at: Column[datetime] = updated_at()

# SQLAlchemy 高级特性
address: composite = composite(Address, street, city, state)
display_name: column_property = column_property(first_name + " " + last_name)
name: synonym = synonym("username")
```at: Column[datetime] = created_at()
updated_at: Column[datetime] = updated_at()

# SQLAlchemy 高级特性
address: composite = composite(Address, street, city, state)
display_name: column_property = column_property(first_name + " " + last_name)
name: synonym = synonym("username")
```

## 使用指南

### 字符串函数

```python
# 基础字符串操作
User.name.upper()                                         # 转大写
User.name.lower()                                         # 转小写
User.name.trim()                                          # 去除空白
User.name.length()                                        # 获取长度

# 字符串截取和替换
User.name.substring(1, 10)                                # 截取子字符串
User.description.regexp_replace(r'\s+', ' ')              # 正则替换
User.email.split_part('@', 2)                             # 分割字符串
User.content.position("keyword")                          # 查找位置
User.text.reverse()                                       # 反转字符串
User.password.md5()                                       # MD5 哈希

# 链式操作（返回 FunctionResult 支持继续链式调用）
User.name.trim().upper().substring(1, 3)                  # 去空白->大写->截取
User.email.lower().trim().split_part('@', 1)              # 多步处理

# 语义化方法（返回查询条件）
User.name.matches(r"^[A-Za-z]+$")                         # 正则匹配
User.name.length_between(3, 50)                           # 长度范围检查
```

### 数值函数

```python
# 基础数学运算
User.age.abs()                                           # 绝对值
User.salary.round(2)
User.score.ceil()                                        # 向上取整
User.rating.floor()                                      # 向下取整
User.area.sqrt()                                         # 平方根
User.base.power(2)                                       # 幂运算
User.value.mod(10)                                       # 取模
User.amount.sign()                                       # 符号函数

# 聚合函数
User.salary.sum()                                        # 求和
User.age.avg()                                           # 平均值
User.score.max()                                         # 最大值
User.rating.min()                                        # 最小值
User.id.count()                                          # 计数

# 链式数值操作
User.salary.abs().round(2)                               # 绝对值->四舍五入
User.score.power(2).sqrt()                               # 平方->开方
```

### 日期时间函数

```python
# 日期时间提取
User.created_at.year()                                   # 提取年份
User.created_at.month()                                  # 提取月份
User.created_at.day()                                    # 提取日期
User.created_at.hour()                                   # 提取小时
User.created_at.minute()                                 # 提取分钟
User.created_at.extract("quarter")                       # 提取季度

# 日期时间计算
User.birth_date.age_in_years()                           # 计算年龄
User.birth_date.age_in_months()                          # 计算月龄
User.start_date.days_between(User.end_date)              # 计算天数差
User.created_at.add_days(30)                             # 添加天数

# 日期时间格式化
User.created_at.date_trunc("month")                      # 截断到月
User.created_at.to_char("YYYY-MM-DD")                    # 格式化输出

# 语义化方法
User.birth_date.is_today()                               # 是否为今天
User.created_at.is_past()                                # 是否为过去
User.deadline.is_future()                                # 是否为未来
User.birth_date.year_equals(1990)                        # 年份匹配
User.created_at.month_equals(12)                         # 月份匹配
```

### JSON 函数

```python
# JSON 键检查
User.metadata.has_key("status")                          # 检查键存在
User.metadata.has_keys("name", "email")                  # 检查多个键
User.metadata.has_any_key("phone", "mobile")             # 检查任一键

# JSON 路径操作
User.metadata.path_exists("$.profile.name")              # 路径存在检查
User.metadata.extract_text("$.profile.name")             # 提取文本值
```

### 布尔函数

```python
# 布尔语义化方法
User.is_active.is_true()                                 # 检查为真
User.is_deleted.is_false()                               # 检查为假
```

### 通用函数

```python
# 类型转换
User.id.cast("string")                                   # 类型转换
User.age.to_string()                                     # 转换为字符串
User.code.to_integer()                                   # 转换为整数
User.price.to_decimal(10, 2)                             # 转换为小数
User.flag.to_boolean()                                   # 转换为布尔

# 空值处理
User.nickname.coalesce(User.username, "Anonymous")       # 空值合并
User.value.nullif(0)                                     # 空值转换

# 条件表达式
User.score.case(
    (User.score >= 90, "A"),
    (User.score >= 80, "B"),
    else_="F"
)                                                        # 条件分支

# 空值检查
User.email.is_null()                                     # 检查为空
User.phone.is_not_null()                                 # 检查非空
```

### 高级用法

```python
# 复杂查询构建
user_stats = await User.objects.annotate(
    display_name=User.first_name.concat(' ', User.last_name).upper(),
    email_domain=User.email.split_part('@', 2),
    age_years=User.birth_date.age_in_years(),
    salary_rounded=User.salary.round(2)
).filter(
    User.name.upper().like('ADMIN%'),
    User.birth_date.age_in_years() >= 18,
    User.salary.abs() > 5000
).all()

# 聚合统计
dept_stats = await User.objects.values('department').annotate(
    total_count=User.id.count(),
    avg_salary=User.salary.avg().round(2),
    max_salary=User.salary.max(),
    avg_age=User.birth_date.age_in_years().avg().round(1)
).all()

# 批量操作使用表达式
await User.objects.update(
    values={
        "display_name": User.first_name.concat(" ", User.last_name),
        "age_years": User.birth_date.age_in_years()
    },
    filter=Q(is_active=True)
)

# 自定义类型注册
from sqlobjects.fields import register_field_type
from sqlalchemy import TypeDecorator, String

class UpperCaseString(TypeDecorator):
    impl = String
    
    def process_bind_param(self, value, dialect):
        return value.upper() if value else value

register_field_type(UpperCaseString, "uppercase", aliases=["upper"])
name: Column[str] = column(type="uppercase", length=50)
```
# SQLObjects Validators 设计说明文档

## 概述

SQLObjects Validators 模块提供完整的数据验证系统，支持字段级验证、自定义验证器和验证错误收集。基于英文错误消息系统，提供类型安全的验证体验。

## 核心特性

### 1. 丰富的内置验证器

提供常用数据类型的验证器，覆盖大部分验证场景：

```python
from sqlobjects.validators import (
    EmailValidator, URLValidator, LengthValidator, 
    RangeValidator, RegexValidator, ChoicesValidator
)

# 字符串验证
email_validator = EmailValidator()                                     # 邮箱格式验证
url_validator = URLValidator()                                         # URL 格式验证
length_validator = LengthValidator(min_length=3, max_length=50)        # 长度验证
regex_validator = RegexValidator(r"^[a-zA-Z0-9_]+$")                   # 正则表达式验证
                                                                       
# 数值验证                                                                 
range_validator = RangeValidator(min_value=0, max_value=100)           # 数值范围验证
choices_validator = ChoicesValidator(["active", "inactive"])           # 选择值验证
                                                                       
# 时间验证                                                                 
date_validator = DateValidator("%Y-%m-%d")                             # 日期格式验证
time_validator = TimeValidator("%H:%M:%S")                             # 时间格式验证

# 数据类型验证
decimal_validator = DecimalValidator(max_digits=10, decimal_places=2)  # 小数精度验证
json_validator = JSONValidator()                                       # JSON 格式验证
```

### 2. 文件和图片验证

专门的文件验证器，支持扩展名、大小和图片尺寸验证：

```python
from sqlobjects.validators import FileValidator, ImageValidator

# 文件验证
file_validator = FileValidator(
    allowed_extensions=["txt", "pdf", "doc"],
    max_size=1024 * 1024,  # 1MB
    min_size=1024          # 1KB
)

# 图片验证
image_validator = ImageValidator(
    allowed_extensions=["jpg", "png", "webp"],
    max_width=1920,
    max_height=1080,
    max_size=5 * 1024 * 1024  # 5MB
)

# 使用示例
file_validator("/path/to/document.pdf")    # 验证文件
image_validator("/path/to/image.jpg")      # 验证图片
```

### 3. 验证器组合系统

支持多个验证器的组合，实现复杂验证逻辑：

```python
from sqlobjects.validators import combine_validators

# 用户名验证：长度 + 正则表达式
username_validator = combine_validators(
    LengthValidator(min_length=3, max_length=50),
    RegexValidator(r"^[a-zA-Z0-9_]+$")
)

# 邮箱验证：长度 + 格式
email_validator = combine_validators(
    LengthValidator(max_length=254),  # RFC 5321 限制
    EmailValidator()
)

# 价格验证：范围 + 小数精度
price_validator = combine_validators(
    RangeValidator(min_value=0),
    DecimalValidator(max_digits=10, decimal_places=2)
)

# 使用组合验证器
username_validator("test123")      # 通过所有验证
price_validator("99.99")           # 通过所有验证
```

## 模块架构

### 核心组件

#### 1. 验证器基类系统

所有验证器继承自 BaseValidator，提供统一的验证接口：

```python
class BaseValidator:
    """验证器基类，定义验证接口"""
    
    def __call__(self, value: Any) -> None:
        """验证值，失败时抛出 ValidationError"""
        raise NotImplementedError

# 具体验证器实现
class LengthValidator(BaseValidator):
    def __init__(self, min_length: int | None = None, max_length: int | None = None):
        self.min_length = min_length
        self.max_length = max_length
    
    def __call__(self, value: Any) -> None:
        if value is None:
            return
        length = len(str(value))
        if self.min_length and length < self.min_length:
            raise create_validation_error("min_length", params={"min_length": self.min_length})
```

#### 2. 验证错误系统

基于英文消息的验证错误系统，支持参数化错误消息：

```python
class ValidationError(SQLObjectsError):
    """验证错误类，支持单字段和多字段错误"""
    
    def __init__(self, message: str, field: str | None = None, 
                 code: str | None = None, params: dict | None = None):
        self.message = message
        self.field = field
        self.code = code
        self.params = params
        self.field_errors: dict[str, list[str]] = {}

# 错误创建函数
def create_validation_error(code: str, field: str | None = None, 
                          params: dict | None = None) -> ValidationError:
    """创建带英文消息的验证错误"""
    messages = {
        "required": "This field is required",
        "min_length": "Ensure this value has at least {min_length} characters",
        "invalid_email": "Enter a valid email address",
        # ... 更多错误消息
    }
    message = messages.get(code, code)
    if params:
        message = message.format(**params)
    return ValidationError(message, field=field, code=code, params=params)
```

#### 3. 验证错误收集器

用于收集多个字段的验证错误：

```python
class ValidationErrorCollector:
    """验证错误收集器，用于批量收集验证错误"""
    
    def __init__(self):
        self._errors: dict[str, list[str]] = {}
    
    def add_error(self, field: str, message: str) -> None:
        """添加字段验证错误"""
        if field not in self._errors:
            self._errors[field] = []
        self._errors[field].append(message)
    
    def raise_if_errors(self) -> None:
        """如果有错误则抛出 ValidationError"""
        if self._errors:
            raise ValidationError("Validation failed", field_errors=self._errors)
```

### 验证器分类

#### 字符串验证器

- **LengthValidator**: 字符串长度验证
- **EmailValidator**: 邮箱格式验证
- **URLValidator**: URL 格式验证
- **RegexValidator**: 正则表达式验证

#### 数值验证器

- **RangeValidator**: 数值范围验证
- **DecimalValidator**: 小数精度和位数验证

#### 选择和格式验证器

- **ChoicesValidator**: 允许值列表验证
- **DateValidator**: 日期格式验证
- **TimeValidator**: 时间格式验证
- **JSONValidator**: JSON 格式验证

#### 文件验证器

- **FileValidator**: 文件类型和大小验证
- **ImageValidator**: 图片文件验证（继承文件验证）

### 与其他模块的集成

#### 与 fields 模块的集成

Validators 模块与 fields 模块紧密集成，为字段提供验证支持：

```python
# fields.py 中使用验证器
from .validators import LengthValidator, EmailValidator, RegexValidator, RangeValidator

# 字段定义时指定验证器
class User(ObjectModel):
    username: Column[str] = str_column(
        length=50,
        validators=[
            LengthValidator(min_length=3, max_length=50),
            RegexValidator(r"^[a-zA-Z0-9_]+$")
        ]
    )
    
    email: Column[str] = str_column(
        length=254,
        validators=[EmailValidator()]
    )
    
    age: Column[int] = int_column(
        validators=[RangeValidator(min_value=0, max_value=150)]
    )
```

#### 与 exceptions 模块的集成

Validators 模块使用 exceptions 模块的错误系统：

```python
# validators.py 导入异常创建函数
from .exceptions import create_validation_error, ValidationError

# 验证器中使用统一的错误创建
class EmailValidator(BaseValidator):
    def __call__(self, value: Any) -> None:
        if not self.pattern.match(value):
            raise create_validation_error("invalid_email")
```

#### Integration with model Module

Validators module integrates closely with ModelMixin in model module:

```python
# Using validators in model module
class ModelMixin:
    def _get_column_validators(self, field_name: str) -> list:
        """Get column validators from the actual instance."""
        model_class = self._get_model_class()
        column_validators = []

        if hasattr(model_class, field_name):
            field_attr = getattr(model_class, field_name)

            if hasattr(field_attr, "_sqlobjects_validators"):
                column_validators = field_attr._sqlobjects_validators or []
            elif hasattr(field_attr, "column") and hasattr(field_attr.column, "info"):
                if "_validators" in field_attr.column.info:
                    column_validators = field_attr.column.info["_validators"]
            elif hasattr(field_attr, "property"):
                if hasattr(field_attr.property, "columns"):
                    for col in field_attr.property.columns:
                        if hasattr(col, "info") and "_validators" in col.info:
                            column_validators = col.info["_validators"]
                            break
                elif hasattr(field_attr.property, "info") and "_validators" in field_attr.property.info:
                    column_validators = field_attr.property.info["_validators"]

        return column_validators
    
    def _temporarily_disable_sqlalchemy_validators(self) -> dict[str, Any]:
        """Temporarily disable SQLAlchemy validators on the model class."""
        model_class = self._get_model_class()
        original_validators = {}

        for attr_name in dir(model_class):
            attr = getattr(model_class, attr_name)
            if hasattr(attr, "__validates__"):
                original_validators[attr_name] = attr
                setattr(model_class, attr_name, lambda _, key, value: value)

        return original_validators
    
    def _restore_sqlalchemy_validators(self, original_validators: dict[str, Any]) -> None:
        """Restore SQLAlchemy validators on the model class."""
        model_class = self._get_model_class()
        for attr_name, original_method in original_validators.items():
            setattr(model_class, attr_name, original_method)
```

#### 模块职责分离

- **validators.py**: 负责验证逻辑、验证器实现、验证器组合
- **exceptions.py**: 负责错误定义、错误消息、错误收集
- **fields.py**: 负责字段定义、验证器集成、字段验证触发
- **model.py**: 负责模型验证、验证器获取、验证执行
- **集成点**: 通过 ValidationError 和验证器接口实现模块协作

## API 参考

### 字符串验证器

```python
# 长度验证
length_validator = LengthValidator(min_length=3, max_length=50)
length_validator("hello")            # 通过验证
length_validator("hi")               # 抛出 ValidationError

# 邮箱验证
email_validator = EmailValidator()
email_validator("user@example.com")  # 通过验证
email_validator("invalid-email")     # 抛出 ValidationError

# URL 验证
url_validator = URLValidator()
url_validator("https://example.com") # 通过验证
url_validator("not-a-url")           # 抛出 ValidationError

# 正则表达式验证
regex_validator = RegexValidator(r"^[a-zA-Z0-9_]+$")
regex_validator("user123")           # 通过验证
regex_validator("user-123")          # 抛出 ValidationError
```

### 数值验证器

```python
# 范围验证
range_validator = RangeValidator(min_value=0, max_value=100)
range_validator(50)                  # 通过验证
range_validator(-10)                 # 抛出 ValidationError

# 小数验证
decimal_validator = DecimalValidator(max_digits=5, decimal_places=2)
decimal_validator("123.45")          # 通过验证
decimal_validator("123.456")         # 抛出 ValidationError（小数位过多）
```

### 选择和格式验证器

```python
# 选择验证
choices_validator = ChoicesValidator(["active", "inactive", "pending"])
choices_validator("active")          # 通过验证
choices_validator("unknown")         # 抛出 ValidationError

# 日期验证
date_validator = DateValidator("%Y-%m-%d")
date_validator("2023-12-25")         # 通过验证
date_validator("12/25/2023")         # 抛出 ValidationError

# 时间验证
time_validator = TimeValidator("%H:%M:%S")
time_validator("14:30:00")           # 通过验证
time_validator("2:30 PM")            # 抛出 ValidationError

# JSON 验证
json_validator = JSONValidator()
json_validator('{"name": "John"}')   # 通过验证
json_validator("{invalid json}")     # 抛出 ValidationError
```

### 文件验证器

```python
# 文件验证
file_validator = FileValidator(
    allowed_extensions=["txt", "pdf", "doc"],
    max_size=1024 * 1024,  # 1MB
    min_size=1024          # 1KB
)
file_validator("/path/to/document.pdf")  # 通过验证

# 图片验证
image_validator = ImageValidator(
    allowed_extensions=["jpg", "png"],
    max_size=5 * 1024 * 1024,  # 5MB
    max_width=1920,
    max_height=1080
)
image_validator("/path/to/image.jpg")    # 通过验证
```

### 验证器组合

```python
# 组合多个验证器
combined_validator = combine_validators(
    LengthValidator(min_length=3, max_length=50),
    RegexValidator(r"^[a-zA-Z0-9_]+$")
)
combined_validator("user123")        # 通过所有验证
combined_validator("ab")             # 抛出 ValidationError（长度不足）
```

### 错误处理

```python
# 验证错误收集
collector = ValidationErrorCollector()
collector.add_error("email", "Email is required")
collector.add_error("age", "Age must be positive")
collector.raise_if_errors()          # 抛出包含所有错误的 ValidationError

# 验证错误处理
try:
    email_validator("invalid-email")
except ValidationError as e:
    print(e.message)                 # "Enter a valid email address"
    print(e.code)                    # "invalid_email"
    print(e.field)                   # None（如果未指定字段）
```

## 使用指南

### 基础用法

```python
from sqlobjects.validators import (
    EmailValidator, LengthValidator, RangeValidator, 
    ChoicesValidator, ValidationError
)

# 单个验证器使用
email_validator = EmailValidator()
try:
    email_validator("user@example.com")  # 验证通过
    email_validator("invalid-email")     # 抛出异常
except ValidationError as e:
    print(f"验证失败: {e.message}")

# 数值范围验证
age_validator = RangeValidator(min_value=0, max_value=150)
age_validator(25)                        # 验证通过
age_validator(-5)                        # 抛出异常

# 字符串长度验证
name_validator = LengthValidator(min_length=2, max_length=50)
name_validator("John")                   # 验证通过
name_validator("J")                      # 抛出异常

# 选择值验证
status_validator = ChoicesValidator(["active", "inactive", "pending"])
status_validator("active")               # 验证通过
status_validator("unknown")              # 抛出异常
```

### 高级用法

```python
from sqlobjects.validators import (
    combine_validators, RegexValidator, DecimalValidator,
    ValidationErrorCollector, BaseValidator
)

# 复杂验证器组合
username_validator = combine_validators(
    LengthValidator(min_length=3, max_length=30),
    RegexValidator(r"^[a-zA-Z0-9_]+$", re.IGNORECASE)
)

password_validator = combine_validators(
    LengthValidator(min_length=8, max_length=128),
    RegexValidator(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]")
)

# 批量验证错误收集
def validate_user_data(data: dict) -> None:
    collector = ValidationErrorCollector()
    
    # 验证用户名
    try:
        username_validator(data.get("username"))
    except ValidationError as e:
        collector.add_error("username", e.message)
    
    # 验证邮箱
    try:
        EmailValidator()(data.get("email"))
    except ValidationError as e:
        collector.add_error("email", e.message)
    
    # 验证年龄
    try:
        RangeValidator(min_value=13, max_value=120)(data.get("age"))
    except ValidationError as e:
        collector.add_error("age", e.message)
    
    # 如果有错误则抛出
    collector.raise_if_errors()

# 自定义验证器
class PasswordStrengthValidator(BaseValidator):
    """密码强度验证器"""
    
    def __call__(self, value: Any) -> None:
        if value is None:
            return
        
        password = str(value)
        score = 0
        
        # 检查长度
        if len(password) >= 8:
            score += 1
        
        # 检查字符类型
        if re.search(r"[a-z]", password):
            score += 1
        if re.search(r"[A-Z]", password):
            score += 1
        if re.search(r"\d", password):
            score += 1
        if re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            score += 1
        
        if score < 3:
            raise create_validation_error(
                "weak_password", 
                params={"score": score, "required": 3}
            )

# 文件验证高级用法
document_validator = FileValidator(
    allowed_extensions=["pdf", "doc", "docx", "txt"],
    max_size=10 * 1024 * 1024,  # 10MB
    min_size=1024               # 1KB
)

image_validator = ImageValidator(
    allowed_extensions=["jpg", "jpeg", "png", "webp"],
    max_width=2048,
    max_height=2048,
    max_size=5 * 1024 * 1024    # 5MB
)

# 条件验证
def validate_user_profile(data: dict) -> None:
    """用户资料验证示例"""
    collector = ValidationErrorCollector()
    
    # 必填字段验证
    required_fields = ["username", "email", "first_name", "last_name"]
    for field in required_fields:
        if not data.get(field):
            collector.add_error(field, "This field is required")
    
    # 用户名验证
    if data.get("username"):
        try:
            combine_validators(
                LengthValidator(min_length=3, max_length=30),
                RegexValidator(r"^[a-zA-Z0-9_]+$")
            )(data["username"])
        except ValidationError as e:
            collector.add_error("username", e.message)
    
    # 邮箱验证
    if data.get("email"):
        try:
            EmailValidator()(data["email"])
        except ValidationError as e:
            collector.add_error("email", e.message)
    
    # 年龄验证（可选字段）
    if data.get("age") is not None:
        try:
            RangeValidator(min_value=13, max_value=120)(data["age"])
        except ValidationError as e:
            collector.add_error("age", e.message)
    
    # 头像验证（可选字段）
    if data.get("avatar"):
        try:
            ImageValidator(
                max_size=2 * 1024 * 1024,  # 2MB
                max_width=500,
                max_height=500
            )(data["avatar"])
        except ValidationError as e:
            collector.add_error("avatar", e.message)
    
    collector.raise_if_errors()

# 使用示例
try:
    validate_user_profile({
        "username": "john_doe",
        "email": "john@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "age": 25
    })
    print("用户资料验证通过")
except ValidationError as e:
    if e.is_multiple:
        print("验证失败，错误详情:")
        for field, errors in e.field_errors.items():
            print(f"  {field}: {', '.join(errors)}")
    else:
        print(f"验证失败: {e.message}")
```
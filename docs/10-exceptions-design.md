# SQLObjects Exceptions 设计说明文档

## 概述

SQLObjects Exceptions 模块提供完整的异常处理系统，包括层次化的异常类、验证错误处理和英文错误消息系统。为 SQLObjects
的所有操作提供统一的错误处理机制。

## 核心特性

### 1. 层次化异常系统

提供清晰的异常继承层次，便于精确的错误处理：

```python
from sqlobjects.exceptions import (
    SQLObjectsError, DoesNotExist, MultipleObjectsReturned,
    ValidationError, DatabaseError, IntegrityError
)

# 异常层次结构
try:
    user = await User.objects.get(User.id == 999)
except DoesNotExist:
    print("用户不存在")
except MultipleObjectsReturned:
    print("找到多个用户")
except SQLObjectsError:
    print("SQLObjects 相关错误")

# 数据库操作异常
try:
    await User.objects.create(email="existing@example.com")
except IntegrityError:
    print("违反数据库约束（如唯一性约束）")
except DatabaseError:
    print("数据库操作错误")
```

### 2. 强大的验证错误系统

支持单字段和多字段验证错误，提供详细的错误信息：

```python
from sqlobjects.exceptions import ValidationError, ValidationErrorCollector

# 单字段验证错误
try:
    user = User(email="invalid-email")
    user.validate_all()
except ValidationError as e:
    print(f"字段: {e.field}")        # "email"
    print(f"错误码: {e.code}")        # "invalid_email"
    print(f"消息: {e.message}")       # "Enter a valid email address"
    print(f"参数: {e.params}")        # {}

# 多字段验证错误
try:
    user = User(name="", email="invalid", age=-5)
    user.validate_all()
except ValidationError as e:
    if e.is_multiple:
        for field, errors in e.field_errors.items():
            print(f"{field}: {', '.join(errors)}")
    
    # 转换为 API 格式
    error_dict = e.to_dict()
    # {
    #     "message": "Validation failed for 3 field(s) with 3 error(s)",
    #     "field_errors": {
    #         "name": ["This field is required"],
    #         "email": ["Enter a valid email address"],
    #         "age": ["Ensure this value is greater than or equal to 0"]
    #     },
    #     "error_count": 3
    # }
```

### 3. 验证错误收集器

提供便捷的多字段验证错误收集机制：

```python
from sqlobjects.exceptions import ValidationErrorCollector

def validate_user_data(data: dict):
    """批量验证用户数据"""
    collector = ValidationErrorCollector()
    
    # 收集各字段的验证错误
    if not data.get("name"):
        collector.add_error("name", "姓名不能为空")
    
    if not data.get("email"):
        collector.add_error("email", "邮箱不能为空")
    elif "@" not in data["email"]:
        collector.add_error("email", "邮箱格式无效")
    
    if data.get("age") and data["age"] < 0:
        collector.add_error("age", "年龄不能为负数")
    
    # 如果有错误则抛出异常
    collector.raise_if_errors()

# 使用示例
try:
    validate_user_data({"name": "", "email": "invalid", "age": -5})
except ValidationError as e:
    print("验证失败，错误详情:")
    for field, errors in e.field_errors.items():
        print(f"  {field}: {', '.join(errors)}")
```

## 模块架构

### 核心组件

#### 1. 异常继承层次

清晰的异常继承结构，支持精确的错误处理：

```python
class SQLObjectsError(Exception):
    """SQLObjects 根异常类"""
    pass

# 查询相关异常
class DoesNotExist(SQLObjectsError):
    """查询无结果异常"""
    pass

class MultipleObjectsReturned(SQLObjectsError):
    """查询返回多个结果异常"""
    pass

# 验证相关异常
class ValidationError(SQLObjectsError):
    """验证错误异常"""
    
    def __init__(self, message: str, field: str | None = None, 
                 code: str | None = None, params: dict | None = None,
                 field_errors: dict[str, list[str]] | None = None):
        self.message = message
        self.field = field
        self.code = code or "invalid"
        self.params = params or {}
        self.field_errors = field_errors or {}
        self.model_class: str | None = None
        self.operation: str | None = None

# 数据库相关异常
class DatabaseError(SQLObjectsError):
    """数据库操作错误"""
    pass

class IntegrityError(DatabaseError):
    """数据库完整性约束错误"""
    pass

class TransactionError(DatabaseError):
    """事务操作错误"""
    pass

# 配置相关异常
class ConfigurationError(SQLObjectsError):
    """配置错误"""
    pass
```

#### 2. ValidationError 功能系统

支持单字段和多字段验证错误的完整功能：

```python
class ValidationError(SQLObjectsError):
    """验证错误类，支持丰富的错误信息"""
    
    @property
    def is_multiple(self) -> bool:
        """检查是否为多字段错误"""
        return bool(self.field_errors)
    
    def add_field_error(self, field: str, message: str) -> None:
        """添加字段错误"""
        if field not in self.field_errors:
            self.field_errors[field] = []
        self.field_errors[field].append(message)
    
    def get_field_errors(self, field: str) -> list[str]:
        """获取特定字段的错误列表"""
        return self.field_errors.get(field, [])
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式，适用于 API 响应"""
        if self.is_multiple:
            return {
                "message": self.message,
                "field_errors": self.field_errors,
                "error_count": sum(len(errors) for errors in self.field_errors.values())
            }
        else:
            result = {"message": self.message, "code": self.code}
            if self.field:
                result["field"] = self.field
            if self.params:
                result["params"] = self.params
            return result
```

#### 3. ValidationErrorCollector 收集器

便捷的验证错误收集和批量处理：

```python
class ValidationErrorCollector:
    """验证错误收集器"""
    
    def __init__(self):
        self._errors: dict[str, list[str]] = {}
    
    def add_error(self, field: str, message: str) -> None:
        """添加字段验证错误"""
        if field not in self._errors:
            self._errors[field] = []
        self._errors[field].append(message)
    
    def has_errors(self) -> bool:
        """检查是否有错误"""
        return bool(self._errors)
    
    def raise_if_errors(self) -> None:
        """如果有错误则抛出 ValidationError"""
        if self.has_errors():
            field_count = len(self._errors)
            total_errors = sum(len(errors) for errors in self._errors.values())
            message = f"Validation failed for {field_count} field(s) with {total_errors} error(s)"
            raise ValidationError(message, field_errors=self._errors)
    
    @property
    def errors(self) -> dict[str, list[str]]:
        """获取所有收集的错误"""
        return self._errors.copy()
```

#### 4. 英文错误消息系统

统一的英文错误消息创建和管理：

```python
# 私有全局错误消息映射
_ERROR_MESSAGES = {
    "required": "This field is required",
    "invalid": "Invalid value",
    "min_length": "Ensure this value has at least {min_length} characters",
    "max_length": "Ensure this value has at most {max_length} characters",
    "min_value": "Ensure this value is greater than or equal to {min_value}",
    "max_value": "Ensure this value is less than or equal to {max_value}",
    "invalid_email": "Enter a valid email address",
    "invalid_url": "Enter a valid URL",
    "invalid_choice": "'{value}' is not a valid choice",
    "invalid_date": "Enter a valid date",
    "invalid_time": "Enter a valid time",
    "invalid_decimal": "Enter a valid decimal number",
    "invalid_json": "Enter valid JSON",
    "file_not_found": "File not found: {path}",
    "file_too_large": "File size {size} exceeds maximum allowed size {max_size}",
    "invalid_file_extension": "File extension '{extension}' not allowed. Allowed: {allowed}",
    "invalid_image_format": "Invalid image format '{extension}'. Allowed: {allowed}"
}

def create_validation_error(
    code: str,
    field: str | None = None,
    params: dict[str, Any] | None = None
) -> ValidationError:
    """创建带英文消息的验证错误"""
    
    # 获取消息模板并格式化
    message = _ERROR_MESSAGES.get(code, code)
    if params:
        try:
            message = message.format(**params)
        except (KeyError, ValueError):
            pass
    
    return ValidationError(message, field=field, code=code, params=params)
```

### 错误消息国际化支持

#### 英文消息标准

所有错误消息都使用标准英文，确保一致性：

```python
# 私有全局英文错误消息映射
_ERROR_MESSAGES = {
    # 基础验证
    "required": "This field is required",
    "invalid": "Invalid value",
    
    # 长度验证
    "min_length": "Ensure this value has at least {min_length} characters",
    "max_length": "Ensure this value has at most {max_length} characters",
    
    # 数值验证
    "min_value": "Ensure this value is greater than or equal to {min_value}",
    "max_value": "Ensure this value is less than or equal to {max_value}",
    
    # 格式验证
    "invalid_email": "Enter a valid email address",
    "invalid_url": "Enter a valid URL",
    "invalid_date": "Enter a valid date",
    "invalid_time": "Enter a valid time",
    "invalid_decimal": "Enter a valid decimal number",
    "invalid_json": "Enter valid JSON",
    
    # 选择验证
    "invalid_choice": "'{value}' is not a valid choice",
    
    # 文件验证
    "file_not_found": "File not found: {path}",
    "file_too_large": "File size {size} exceeds maximum allowed size {max_size}",
    "file_too_small": "File size {size} is below minimum required size {min_size}",
    "invalid_file_extension": "File extension '{extension}' not allowed. Allowed: {allowed}",
    "invalid_image_format": "Invalid image format '{extension}'. Allowed: {allowed}",
    "file_access_error": "Cannot access file: {error}",
    "invalid_file": "Invalid file"
}
```

### 与其他模块的集成

#### 与 validators 模块的集成

Exceptions 模块为 validators 模块提供错误创建和处理支持：

```python
# validators.py 中使用异常系统
from .exceptions import create_validation_error, ValidationError

class EmailValidator(BaseValidator):
    def __call__(self, value: Any) -> None:
        if value is None:
            return
        
        if not isinstance(value, str):
            raise create_validation_error("invalid")
        
        if not self.pattern.match(value):
            raise create_validation_error("invalid_email")

class LengthValidator(BaseValidator):
    def __call__(self, value: Any) -> None:
        if value is None:
            return
        
        length = len(str(value))
        
        if self.min_length and length < self.min_length:
            raise create_validation_error("min_length", params={"min_length": self.min_length})
        
        if self.max_length and length > self.max_length:
            raise create_validation_error("max_length", params={"max_length": self.max_length})
```

#### 与 model 模块的集成

Model 模块使用异常系统进行验证错误处理：

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

#### 与 objects 模块的集成

Objects 模块使用异常系统处理查询和操作错误：

```python
# objects.py 中使用异常系统
from .exceptions import DoesNotExist, MultipleObjectsReturned, ValidationError

class ObjectsManager:
    async def get(self, *args) -> T:
        """获取单个对象，使用标准异常"""
        results = await self.filter(*args).limit(2).all()
        
        if not results:
            raise DoesNotExist(f"{self._model.__name__} matching query does not exist")
        
        if len(results) > 1:
            raise MultipleObjectsReturned(f"Multiple {self._model.__name__} objects returned")
        
        return results[0]
    
    async def create(self, validate=True, **kwargs) -> T:
        """创建对象，增强验证错误信息"""
        try:
            obj = self._model(**kwargs)
            if self._db_or_session:
                await obj.using(self._db_or_session).save(validate=validate)
            else:
                await obj.save(validate=validate)
            return obj
        except ValidationError as e:
            # 增强错误信息
            if not e.is_multiple:
                enhanced_error = ValidationError(
                    f"Failed to create {self._model.__name__}: {e.message}",
                    field=e.field, code=e.code, params=e.params
                )
                enhanced_error.operation = "create"
                enhanced_error.model_class = self._model.__name__
                raise enhanced_error from e
            else:
                enhanced_message = f"Failed to create {self._model.__name__}: {e.message}"
                enhanced_error = ValidationError(enhanced_message, field_errors=e.field_errors)
                enhanced_error.operation = "create"
                enhanced_error.model_class = self._model.__name__
                raise enhanced_error from e
```

#### 模块职责分离

- **exceptions.py**: 负责异常定义、错误消息、错误收集、异常创建
- **validators.py**: 负责验证逻辑，使用异常系统报告错误
- **model.py**: 负责模型验证，使用异常系统收集和处理错误
- **objects.py**: 负责查询操作，使用异常系统处理查询错误
- **集成点**: 通过统一的异常类和错误创建函数实现模块协作

## API 参考

### 异常类

```python
from sqlobjects.exceptions import (
    SQLObjectsError, DoesNotExist, MultipleObjectsReturned,
    ValidationError, DatabaseError, IntegrityError, 
    TransactionError, ConfigurationError
)

# 根异常类
try:
    # SQLObjects 操作
    pass
except SQLObjectsError as e:
    print(f"SQLObjects 错误: {e}")

# 查询异常
try:
    user = await User.objects.get(User.id == 999)
except DoesNotExist:
    print("对象不存在")
except MultipleObjectsReturned:
    print("返回多个对象")

# 数据库异常
try:
    await User.objects.create(email="duplicate@example.com")
except IntegrityError:
    print("违反数据库完整性约束")
except TransactionError:
    print("事务操作失败")
except DatabaseError:
    print("数据库操作错误")

# 配置异常
try:
    # 配置相关操作
    pass
except ConfigurationError:
    print("配置错误")
```

### ValidationError 详细用法

```python
from sqlobjects.exceptions import ValidationError

# 单字段验证错误
error = ValidationError(
    message="Enter a valid email address",
    field="email",
    code="invalid_email"
)

print(error.field)        # "email"
print(error.code)         # "invalid_email"
print(error.message)      # "Enter a valid email address"
print(error.is_multiple)  # False

# 多字段验证错误
field_errors = {
    "name": ["This field is required"],
    "email": ["Enter a valid email address"],
    "age": ["Ensure this value is greater than or equal to 0"]
}
error = ValidationError(
    message="Validation failed for 3 field(s) with 3 error(s)",
    field_errors=field_errors
)

print(error.is_multiple)  # True
print(error.get_field_errors("email"))  # ["Enter a valid email address"]

# 添加字段错误
error.add_field_error("phone", "Invalid phone number format")

# 转换为字典
error_dict = error.to_dict()
# {
#     "message": "Validation failed for 4 field(s) with 4 error(s)",
#     "field_errors": {...},
#     "error_count": 4
# }
```

### ValidationErrorCollector 用法

```python
from sqlobjects.exceptions import ValidationErrorCollector

# 创建收集器
collector = ValidationErrorCollector()

# 添加错误
collector.add_error("name", "This field is required")
collector.add_error("email", "Enter a valid email address")
collector.add_error("email", "Email already exists")  # 同一字段多个错误

# 检查是否有错误
if collector.has_errors():
    print("发现验证错误")

# 获取所有错误
errors = collector.errors
# {
#     "name": ["This field is required"],
#     "email": ["Enter a valid email address", "Email already exists"]
# }

# 如果有错误则抛出异常
try:
    collector.raise_if_errors()
except ValidationError as e:
    print("批量验证失败")
    for field, messages in e.field_errors.items():
        print(f"{field}: {', '.join(messages)}")
```

### 错误创建函数

```python
from sqlobjects.exceptions import create_validation_error

# 创建基础验证错误
error = create_validation_error("required", field="name")
print(error.message)  # "This field is required"

# 创建带参数的验证错误
error = create_validation_error(
    "min_length", 
    field="password",
    params={"min_length": 8}
)
print(error.message)  # "Ensure this value has at least 8 characters"

# 创建选择验证错误
error = create_validation_error(
    "invalid_choice",
    field="status",
    params={"value": "unknown"}
)
print(error.message)  # "'unknown' is not a valid choice"

# 创建文件验证错误
error = create_validation_error(
    "file_too_large",
    field="avatar",
    params={"size": 5242880, "max_size": 2097152}
)
print(error.message)  # "File size 5242880 exceeds maximum allowed size 2097152"
```

## 使用指南

### 基础用法

```python
from sqlobjects.exceptions import (
    SQLObjectsError, DoesNotExist, ValidationError,
    ValidationErrorCollector, create_validation_error
)

# 基础异常处理
try:
    user = await User.objects.get(User.email == "nonexistent@example.com")
except DoesNotExist:
    print("用户不存在")
except SQLObjectsError as e:
    print(f"SQLObjects 操作失败: {e}")

# 验证错误处理
try:
    user = User(name="", email="invalid-email", age=-5)
    user.validate_all()
except ValidationError as e:
    if e.is_multiple:
        print("多字段验证失败:")
        for field, errors in e.field_errors.items():
            print(f"  {field}: {', '.join(errors)}")
    else:
        print(f"单字段验证失败: {e.field} - {e.message}")

# 创建自定义验证错误
def validate_username(username: str):
    if not username:
        raise create_validation_error("required", field="username")
    
    if len(username) < 3:
        raise create_validation_error(
            "min_length", 
            field="username",
            params={"min_length": 3}
        )
    
    if "admin" in username.lower():
        raise create_validation_error(
            "invalid_choice",
            field="username", 
            params={"value": username}
        )

# 使用错误收集器
def validate_user_registration(data: dict):
    collector = ValidationErrorCollector()
    
    # 验证各个字段
    if not data.get("username"):
        collector.add_error("username", "Username is required")
    elif len(data["username"]) < 3:
        collector.add_error("username", "Username must be at least 3 characters")
    
    if not data.get("email"):
        collector.add_error("email", "Email is required")
    elif "@" not in data["email"]:
        collector.add_error("email", "Enter a valid email address")
    
    if not data.get("password"):
        collector.add_error("password", "Password is required")
    elif len(data["password"]) < 8:
        collector.add_error("password", "Password must be at least 8 characters")
    
    # 如果有错误则抛出
    collector.raise_if_errors()

# 使用示例
try:
    validate_user_registration({
        "username": "ab",
        "email": "invalid",
        "password": "123"
    })
except ValidationError as e:
    print("注册数据验证失败:")
    error_dict = e.to_dict()
    print(f"错误数量: {error_dict['error_count']}")
    for field, errors in error_dict["field_errors"].items():
        print(f"  {field}: {', '.join(errors)}")
```

### 高级用法

```python
from sqlobjects.exceptions import ValidationError, ValidationErrorCollector
import logging

# 自定义异常类
class BusinessLogicError(SQLObjectsError):
    """业务逻辑错误"""
    
    def __init__(self, message: str, error_code: str = None, context: dict = None):
        super().__init__(message)
        self.error_code = error_code
        self.context = context or {}

# 复杂验证场景
class UserValidator:
    """用户验证器类"""
    
    def __init__(self):
        self.collector = ValidationErrorCollector()
    
    def validate_basic_info(self, user_data: dict):
        """基础信息验证"""
        if not user_data.get("username"):
            self.collector.add_error("username", "Username is required")
        else:
            self._validate_username(user_data["username"])
        
        if not user_data.get("email"):
            self.collector.add_error("email", "Email is required")
        else:
            self._validate_email(user_data["email"])
    
    def validate_profile_info(self, user_data: dict):
        """个人资料验证"""
        if user_data.get("age") is not None:
            self._validate_age(user_data["age"])
        
        if user_data.get("phone"):
            self._validate_phone(user_data["phone"])
    
    def validate_security_info(self, user_data: dict):
        """安全信息验证"""
        if not user_data.get("password"):
            self.collector.add_error("password", "Password is required")
        else:
            self._validate_password(user_data["password"])
    
    def _validate_username(self, username: str):
        """用户名验证"""
        if len(username) < 3:
            self.collector.add_error("username", "Username must be at least 3 characters")
        elif len(username) > 50:
            self.collector.add_error("username", "Username must be at most 50 characters")
        elif not username.replace("_", "").isalnum():
            self.collector.add_error("username", "Username can only contain letters, numbers and underscores")
    
    def _validate_email(self, email: str):
        """邮箱验证"""
        if "@" not in email:
            self.collector.add_error("email", "Enter a valid email address")
        elif len(email) > 254:
            self.collector.add_error("email", "Email address is too long")
    
    def _validate_age(self, age: int):
        """年龄验证"""
        if age < 0:
            self.collector.add_error("age", "Age cannot be negative")
        elif age > 150:
            self.collector.add_error("age", "Age cannot exceed 150")
    
    def _validate_phone(self, phone: str):
        """手机号验证"""
        if not phone.replace("-", "").replace(" ", "").isdigit():
            self.collector.add_error("phone", "Phone number can only contain digits, spaces and dashes")
    
    def _validate_password(self, password: str):
        """密码验证"""
        errors = []
        
        if len(password) < 8:
            errors.append("Password must be at least 8 characters")
        
        if not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
        
        if not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")
        
        if not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one digit")
        
        if not any(c in "!@#$%^&*(),.?\":{}|<>" for c in password):
            errors.append("Password must contain at least one special character")
        
        for error in errors:
            self.collector.add_error("password", error)
    
    def validate_all(self, user_data: dict):
        """完整验证"""
        self.validate_basic_info(user_data)
        self.validate_profile_info(user_data)
        self.validate_security_info(user_data)
        
        # 如果有错误则抛出
        self.collector.raise_if_errors()

# 异常处理装饰器
def handle_validation_errors(func):
    """验证错误处理装饰器"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValidationError as e:
            # 记录验证错误
            logging.warning(f"Validation error in {func.__name__}: {e.message}")
            
            # 可以在这里添加额外的错误处理逻辑
            if e.is_multiple:
                logging.debug(f"Field errors: {e.field_errors}")
            
            # 重新抛出异常
            raise
        except SQLObjectsError as e:
            # 记录 SQLObjects 错误
            logging.error(f"SQLObjects error in {func.__name__}: {e}")
            raise
    
    return wrapper

# API 错误响应格式化
class APIErrorFormatter:
    """API 错误响应格式化器"""
    
    @staticmethod
    def format_validation_error(error: ValidationError) -> dict:
        """格式化验证错误为 API 响应"""
        if error.is_multiple:
            return {
                "error": "validation_failed",
                "message": "Validation failed",
                "details": error.field_errors,
                "error_count": sum(len(errors) for errors in error.field_errors.values())
            }
        else:
            return {
                "error": "validation_failed",
                "message": error.message,
                "field": error.field,
                "code": error.code
            }
    
    @staticmethod
    def format_not_found_error(error: DoesNotExist) -> dict:
        """格式化未找到错误为 API 响应"""
        return {
            "error": "not_found",
            "message": str(error)
        }
    
    @staticmethod
    def format_integrity_error(error: IntegrityError) -> dict:
        """格式化完整性错误为 API 响应"""
        return {
            "error": "integrity_constraint_violation",
            "message": "The operation violates database constraints",
            "details": str(error)
        }

# 使用示例
async def create_user_endpoint(user_data: dict):
    """用户创建端点示例"""
    try:
        # 验证用户数据
        validator = UserValidator()
        validator.validate_all(user_data)
        
        # 创建用户
        user = await User.objects.create(**user_data)
        
        return {"success": True, "user_id": user.id}
        
    except ValidationError as e:
        return APIErrorFormatter.format_validation_error(e)
    
    except IntegrityError as e:
        return APIErrorFormatter.format_integrity_error(e)
    
    except SQLObjectsError as e:
        logging.error(f"Unexpected SQLObjects error: {e}")
        return {
            "error": "internal_error",
            "message": "An internal error occurred"
        }

# 批量操作错误处理
async def bulk_create_users(users_data: list[dict]):
    """批量创建用户示例"""
    results = []
    errors = []
    
    for i, user_data in enumerate(users_data):
        try:
            validator = UserValidator()
            validator.validate_all(user_data)
            
            user = await User.objects.create(**user_data)
            results.append({"index": i, "success": True, "user_id": user.id})
            
        except ValidationError as e:
            error_info = {
                "index": i,
                "success": False,
                "error": APIErrorFormatter.format_validation_error(e)
            }
            errors.append(error_info)
            results.append(error_info)
        
        except IntegrityError as e:
            error_info = {
                "index": i,
                "success": False,
                "error": APIErrorFormatter.format_integrity_error(e)
            }
            errors.append(error_info)
            results.append(error_info)
    
    return {
        "total": len(users_data),
        "successful": len(results) - len(errors),
        "failed": len(errors),
        "results": results
    }

# 使用示例
# result = await create_user_endpoint({
#     "username": "john_doe",
#     "email": "john@example.com",
#     "password": "SecurePass123!",
#     "age": 25
# })
```
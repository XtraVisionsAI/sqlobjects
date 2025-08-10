# SQLObjects Signals 设计说明文档

## 概述

SQLObjects Signals 模块提供基于 SQLAlchemy 事件系统的模型生命周期信号处理机制，支持同步和异步信号处理器，实现数据库操作的自动化响应。

所有 ObjectModel 都自动继承了 SignalMixin 的信号处理能力，通过 `ObjectModel(DeclarativeBase, ModelMixin)` 和
`ModelMixin(SignalMixin)` 的继承链实现。

## 核心特性

### 1. 生命周期集成

信号系统与模型生命周期深度集成，自动触发相应的信号处理器：

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import Column, str_column
from datetime import datetime

class User(ObjectModel):
    name: Column[str] = str_column(length=50)
    
    async def before_save(self, context: SignalContext) -> None:
        # 保存前自动调用
        self.updated_at = datetime.now()
    
    async def after_save(self, context: SignalContext) -> None:
        # 保存后自动调用
        await self.send_notification()
```

### 2. 异步信号支持

原生支持异步信号处理器，避免阻塞数据库操作：

```python
from sqlobjects.base import ObjectModel

class User(ObjectModel):
    def before_save(self, context: SignalContext) -> None:
        # 同步处理器
        self.name = self.name.strip().title()
    
    async def after_save(self, context: SignalContext) -> None:
        # 异步处理器
        await self.send_email_notification()
```

### 3. 批量操作信号

支持批量操作的类级信号处理：

```python
from sqlobjects.base import ObjectModel

class User(ObjectModel):
    @classmethod
    async def before_update(cls, context: SignalContext) -> None:
        # 批量更新前处理
        if context.affected_count > 100:
            await cls.log_bulk_operation(context)
```

### 4. 丰富的上下文信息

提供完整的操作上下文信息：

```python
@dataclass
class SignalContext:
    operation: Operation              # 操作类型
    session: AsyncSession             # 数据库会话
    model_class: Any                  # 模型类
    instance: Any | None = None       # 实例对象
    affected_count: int | None = None # 影响行数
```

## 模块架构

### 核心组件

- **Operation 枚举**：定义支持的数据库操作类型（SAVE、DELETE、UPDATE）
- **SignalContext 数据类**：封装操作上下文信息
- **SignalMixin 混入类**：为模型提供信号处理能力

### 信号处理模式

#### 实例级信号

用于单个对象的操作处理：

```python
class User(ObjectModel):
    async def before_save(self, context: SignalContext) -> None:
        # 实例保存前处理
        self.validate_business_rules()
    
    async def after_delete(self, context: SignalContext) -> None:
        # 实例删除后处理
        await self.cleanup_related_data()
```

#### 类级信号

用于批量操作的处理：

```python
class User(ObjectModel):
    @classmethod
    async def before_update(cls, context: SignalContext) -> None:
        # 批量更新前处理
        await cls.log_bulk_operation(context)
    
    @classmethod
    async def after_update(cls, context: SignalContext) -> None:
        # 批量更新后处理
        await cls.invalidate_cache()
```

### 与其他模块的集成

#### ObjectModel 集成

所有 ObjectModel 自动具备信号处理能力：

```python
from sqlobjects.base import ObjectModel

class User(ObjectModel):
    # 自动继承 SignalMixin，具备信号处理能力
    pass
```

#### Queries 模块集成

信号处理器可以使用完整的 QuerySet API：

```python
from sqlobjects.base import ObjectModel

class User(ObjectModel):
    async def after_save(self, context: SignalContext) -> None:
        # 使用 QuerySet 进行相关操作
        related_users = await User.objects.filter(
            department_id=self.department_id,
            session=context.session
        ).all()
```

#### 模块职责分离

- **signals.py**: 负责信号系统核心组件、上下文管理、信号触发机制
- **集成点**: 通过 SignalMixin 与 ObjectModel 集成，通过 session 参数与 Queries 模块协作

## API 参考

### 信号处理器方法

```python
# 实例级信号处理器
async def before_save(self, context: SignalContext) -> None
async def after_save(self, context: SignalContext) -> None
async def before_delete(self, context: SignalContext) -> None
async def after_delete(self, context: SignalContext) -> None

# 类级信号处理器
@classmethod
async def before_update(cls, context: SignalContext) -> None
@classmethod
async def after_update(cls, context: SignalContext) -> None
```

### SignalContext 属性

```python
context.operation       # 操作类型（Operation 枚举）
context.session         # 数据库会话
context.model_class     # 模型类
context.instance        # 实例对象（单实例操作）
context.affected_count  # 影响行数（批量操作）
context.update_data     # 更新数据（批量更新）

# 便捷属性
context.is_single       # 是否为单实例操作
context.is_bulk         # 是否为批量操作
```

### SQLAlchemy 事件集成

```python
from sqlobjects.signals import event

@event.listens_for(User, "before_insert")
def before_insert_handler(mapper, connection, target):
    # SQLAlchemy 原生事件处理
    pass
```

## 使用指南

### 基础用法

```python
from sqlobjects.base import ObjectModel
from sqlobjects.fields import Column, str_column
from datetime import datetime

class User(ObjectModel):
    name: Column[str] = str_column(length=50)
    email: Column[str] = str_column(length=100)
    
    async def before_save(self, context: SignalContext) -> None:
        # 保存前处理
        self.updated_at = datetime.now()
    
    async def after_save(self, context: SignalContext) -> None:
        # 保存后处理
        await self.send_welcome_email()
```

### 高级用法

#### 条件信号处理

```python
from sqlobjects.base import ObjectModel

class User(ObjectModel):
    async def before_save(self, context: SignalContext) -> None:
        # 根据操作类型和上下文进行条件处理
        if context.is_single:
            await self.validate_unique_constraints()
        elif context.is_bulk:
            await self.prepare_bulk_validation()
```

#### 批量操作信号

```python
from sqlobjects.base import ObjectModel

class User(ObjectModel):
    @classmethod
    async def before_update(cls, context: SignalContext) -> None:
        # 批量更新前处理
        if context.affected_count > 1000:
            logger.info(f"Large bulk update: {context.affected_count} users")
        
        # 状态变更前验证
        if 'status' in context.update_data:
            await cls.validate_status_change(context.update_data['status'])
```

#### 信号处理器中的查询操作

```python
from sqlobjects.base import ObjectModel
from sqlobjects.queries import Q
from datetime import datetime

class User(ObjectModel):
    async def after_save(self, context: SignalContext) -> None:
        # 使用 Q 对象构建复杂查询
        related_users = await User.objects.filter(
            Q(department_id=self.department_id) & Q(is_active=True),
            session=context.session
        ).exclude(id=self.id).all()
        
        # 批量更新相关数据
        await User.objects.filter(
            department_id=self.department_id,
            session=context.session
        ).update(values={"last_department_update": datetime.now()})
```

#### 错误处理

```python
from sqlobjects.base import ObjectModel
from sqlobjects.exceptions import ValidationError
import logging

class User(ObjectModel):
    async def before_save(self, context: SignalContext) -> None:
        try:
            await self.validate_business_rules()
        except ValidationError as e:
            # 信号处理器中的异常会阻止操作继续
            raise e
        except Exception as e:
            # 记录错误但不阻止操作
            logger.error(f"Signal handler error: {e}")
```
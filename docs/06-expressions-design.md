# SQLObjects Expressions 设计说明文档

## 概述

SQLObjects Expressions 模块基于 SQLAlchemy 原生表达式系统，提供类型安全、高性能的数据库表达式支持。

## 核心特性

### 1. 类型安全表达式

提供编译时类型检查和 IDE 支持：

```python
# 类型安全的字段引用
User.name.upper()                    # IDE 提示和类型检查
User.age >= 18                       # 字段存在性验证
```

### 2. 链式函数调用

支持字段上的链式函数调用：

```python
# 链式调用
User.name.upper().trim()             # 字符串处理链
User.birth_date.year().month()       # 日期提取链
User.score.round(2).abs()            # 数值处理链
```

### 3. 智能子查询

自动类型推断和转换：

```python
# 自动类型推断
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery()  # 推断为 scalar
active_users = User.objects.filter(is_active=True).subquery()            # 推断为 table
```

## 模块架构

### 核心组件

- **func 对象**：提供所有数据库函数
- **表达式构建器**：and_, or_, not_, exists, text, literal
- **SubqueryExpression**：智能子查询支持
- **函数混入系统**：StringFunctionMixin, NumericFunctionMixin, DateTimeFunctionMixin
- **FunctionResult**：链式调用结果类

### 函数混入系统

通过混入类实现函数功能的模块化组织：

```python
class FunctionMixin:
    """函数方法混入基类"""
    
    def _get_expression(self):
        return self.expr
    
    def _create_result(self, func_call):
        return FunctionResult(func_call)

class StringFunctionMixin(FunctionMixin):
    """字符串函数混入"""
    
    def upper(self) -> FunctionResult:
        return self._create_result(func.upper(self._get_expression()))
    
    def trim(self) -> FunctionResult:
        return self._create_result(func.trim(self._get_expression()))
```

### 子查询系统

智能子查询表达式，支持自动类型推断：

```python
class SubqueryExpression:
    """智能子查询表达式"""
    
    def _infer_type(self) -> str:
        """自动推断子查询类型"""
        # 规则 1: 单列 + 聚合 + LIMIT 1 → scalar
        # 规则 2: 单列聚合查询 → scalar
        # 规则 3: 多列查询 → table
        # 规则 4: 单列非聚合 → table (用于 IN 条件)
    
    def as_scalar(self) -> "SubqueryExpression":
        return SubqueryExpression(self.query, self.name, "scalar")
    
    def as_exists(self) -> "SubqueryExpression":
        return SubqueryExpression(self.query, self.name, "exists")
    
    def as_table(self) -> "SubqueryExpression":
        return SubqueryExpression(self.query, self.name, "table")
```

### 与其他模块的集成

#### 与 fields 模块的集成

Expressions 模块为 fields 模块提供函数系统支持：

```python
# fields 模块使用 expressions 模块的函数系统
from .expressions import (
    DateTimeFunctionMixin, 
    FunctionResult, 
    NumericFunctionMixin, 
    StringFunctionMixin
)

# 增强类型继承函数混入
class EnhancedStringComparator(String.Comparator, StringFunctionMixin):
    """字符串比较器，继承 expressions 模块的字符串函数"""
    pass

class EnhancedIntegerComparator(Integer.Comparator, NumericFunctionMixin):
    """数值比较器，继承 expressions 模块的数值函数"""
    pass
```

#### 与 queries 模块的集成

Expressions 模块为 queries 模块提供表达式和子查询支持：

```python
# queries 模块使用 expressions 模块的核心组件
from .expressions import (
    func, and_, or_, not_, exists, text, literal,
    SubqueryExpression
)

class QuerySet:
    """查询集，使用 expressions 模块的表达式系统"""
    
    def filter(self, *args, **kwargs):
        # 支持 expressions 模块的所有表达式类型
        # User.age >= 18, and_(condition1, condition2), func.upper(User.name)
        pass
    
    def subquery(self, name=None, query_type=None):
        # 返回 SubqueryExpression 实例
        return SubqueryExpression(self, name, query_type)
    
    def annotate(self, **kwargs):
        # 支持 func 对象和字段链式调用
        # .annotate(full_name=func.concat(User.first_name, ' ', User.last_name))
        # .annotate(upper_name=User.name.upper())
        pass
```

#### 模块职责分离

- **expressions.py**: 负责函数系统、链式调用、表达式处理、子查询支持
- **fields.py**: 负责字段定义、类型系统、增强类型实现
- **queries.py**: 负责查询构建、过滤条件、聚合操作
- **集成点**: 通过 Mixin 类继承和直接导入实现功能共享

## API 参考

### 核心表达式

```python
# 导入核心组件
from sqlobjects.expressions import (
    func, and_, or_, not_, exists, text, literal,
    SubqueryExpression
)

# 基础表达式操作
User.age >= 18                       # 比较操作
User.name.like('%admin%')            # 模式匹配
User.salary.between(5000, 10000)     # 范围查询

# 逻辑组合
condition = and_(
    User.age >= 18,
    or_(User.role == 'admin', User.is_staff == True)
)
```

### 函数调用

```python
# func 对象 - 多字段操作
func.concat(User.first_name, ' ', User.last_name)  # 字符串连接
func.coalesce(User.nickname, User.username)        # 空值处理
func.extract('year', User.created_at)              # 日期提取

# 字段链式调用 - 单字段操作
User.name.upper().trim()                           # 字符串处理链
User.birth_date.year()                             # 日期组件提取
User.salary.round(2)                               # 数值格式化
```

### 子查询操作

```python
# 自动类型推断
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery()  # 推断为 scalar
active_users = User.objects.filter(is_active=True).subquery()            # 推断为 table

# 显式类型指定
scalar_subq = User.objects.aggregate(count=func.count()).subquery(query_type="scalar")
exists_subq = Post.objects.filter(author_id=F("id")).subquery(query_type="exists")

# 类型转换
table_subq = scalar_subq.as_table()
exists_subq = table_subq.as_exists()

# 在查询中使用
high_earners = User.objects.filter(User.salary > avg_salary_subq)
users_with_posts = User.objects.filter(has_posts_subq)
```

## 使用指南

### 基础用法

```python
# 基础表达式操作
User.age >= 18                       # 比较操作
User.name.like('%admin%')            # 模式匹配
User.salary.between(5000, 10000)     # 范围查询

# 逻辑组合
condition = and_(
    User.age >= 18,
    or_(User.role == 'admin', User.is_staff == True)
)

# 字段链式调用
User.name.upper().trim()             # 字符串处理链
User.birth_date.year()               # 日期组件提取
User.salary.round(2)                 # 数值格式化

# func 对象使用
func.concat(User.first_name, ' ', User.last_name)  # 字符串连接
func.coalesce(User.nickname, User.username)        # 空值处理
func.extract('year', User.created_at)              # 日期提取
```

### 高级用法

```python
# 智能子查询
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery()  # 自动推断为 scalar
active_users = User.objects.filter(is_active=True).subquery()            # 自动推断为 table

# 显式类型指定
scalar_subq = User.objects.aggregate(count=func.count()).subquery(query_type="scalar")
exists_subq = Post.objects.filter(author_id=User.id).subquery(query_type="exists")

# 类型转换
table_as_scalar = active_users.as_scalar()
exists_as_table = exists_subq.as_table()

# 复杂子查询组合
dept_avg_salary = Employee.objects.filter(
    department_id=User.department_id
).aggregate(
    avg_salary=func.avg(Employee.salary)
).subquery(query_type="scalar")

high_performers = User.objects.filter(
    User.salary > dept_avg_salary * 1.2
).annotate(
    performance_ratio=User.salary / dept_avg_salary
)

# 窗口函数
user_rankings = User.objects.annotate(
    salary_rank=func.rank().over(partition_by='department_id', order_by='-salary'),
    running_total=func.sum(User.salary).over(partition_by='department_id', order_by='hire_date')
).all()

# 条件表达式
user_grades = User.objects.annotate(
    grade=func.case(
        (User.score >= 90, 'A'),
        (User.score >= 80, 'B'),
        (User.score >= 70, 'C'),
        else_='F'
    )
).all()

# 存在性查询
has_posts = exists().where(Post.author_id == User.id)
active_authors = User.objects.filter(has_posts).all()

# 原生 SQL 支持
condition = text("age > :min_age")
users = User.objects.filter(condition).params(min_age=18).all()
```
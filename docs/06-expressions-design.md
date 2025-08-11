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

智能子查询表达式，支持自动类型推断和多种子查询类型。SubqueryExpression 类提供统一的子查询接口，自动分析查询结构并选择最适合的子查询类型：

```python
class SubqueryExpression:
    """智能子查询表达式，支持多种 SQLAlchemy 子查询类型"""
    
    def __init__(self, query: Select, name: str | None = None, query_type: str = "auto"):
        self.query = query
        self.name = name
        self.query_type = self._infer_type() if query_type == "auto" else query_type
    
    def _infer_type(self) -> str:
        """智能类型推断，基于查询结构分析"""
        structure = self._analyze_query_structure()
        
        # 规则 1: 明确的标量查询特征
        if (structure["has_single_column"] and structure["has_aggregates"] 
            and (structure["has_limit_one"] or structure["is_count_query"])):
            return "scalar"
        
        # 规则 2: 单列聚合查询（常用于比较）
        if structure["has_single_column"] and structure["has_aggregates"]:
            return "scalar"
        
        # 规则 3: 多列查询默认为表子查询
        if structure["column_count"] > 1:
            return "table"
        
        # 规则 4: 单列非聚合查询（如 ID 列表）
        return "table"
    
    def _analyze_query_structure(self) -> dict:
        """分析查询结构以提供推断依据"""
        analysis = {
            "select_columns": [],
            "has_aggregates": False,
            "has_single_column": False,
            "has_limit_one": False,
            "column_count": 0,
            "is_count_query": False,
        }
        
        # 分析 SELECT 列
        if hasattr(self.query, "selected_columns"):
            analysis["select_columns"] = list(self.query.selected_columns)
            analysis["column_count"] = len(analysis["select_columns"])
            analysis["has_single_column"] = analysis["column_count"] == 1
        
        # 检测聚合函数
        query_str = str(self.query).lower()
        aggregate_keywords = ["count(", "sum(", "avg(", "max(", "min("]
        analysis["has_aggregates"] = any(keyword in query_str for keyword in aggregate_keywords)
        
        # 检测 LIMIT 子句
        analysis["has_limit_one"] = (
            hasattr(self.query, "_limit") and self.query._limit == 1
        )
        
        # 检测计数查询
        analysis["is_count_query"] = "count(" in query_str
        
        return analysis
    
    def resolve(self, model_class=None) -> Any:
        """解析为适当的 SQLAlchemy 对象"""
        if self.query_type == "scalar":
            return self._get_scalar_subquery()
        elif self.query_type == "exists":
            return self._get_exists_subquery()
        else:  # 'table'
            return self._get_table_subquery()
    
    # 类型转换方法
    def as_scalar(self) -> "SubqueryExpression":
        return SubqueryExpression(self.query, self.name, "scalar")
    
    def as_exists(self) -> "SubqueryExpression":
        return SubqueryExpression(self.query, self.name, "exists")
    
    def as_table(self) -> "SubqueryExpression":
        return SubqueryExpression(self.query, self.name, "table")
    
    # 操作符重载，支持自动类型适配
    def __eq__(self, other):
        if self.query_type == "table":
            return self.as_scalar().resolve() == other
        return self.resolve() == other
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
# 自动类型推断（推荐使用）
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery()  # 自动推断为 scalar
active_users = User.objects.filter(is_active=True).subquery()            # 自动推断为 table
user_count = User.objects.aggregate(count=func.count()).subquery()       # 自动推断为 scalar

# 显式类型指定（高级用法）
scalar_subq = User.objects.aggregate(count=func.count()).subquery(query_type="scalar")
table_subq = User.objects.filter(is_active=True).subquery(query_type="table")
exists_subq = Post.objects.filter(author_id=User.id).subquery(query_type="exists")

# 类型转换（灵活切换）
scalar_as_table = scalar_subq.as_table()    # 标量子查询转为表子查询
table_as_scalar = table_subq.as_scalar()    # 表子查询转为标量子查询
exists_check = table_subq.as_exists()       # 表子查询转为存在性检查

# 在查询中使用子查询
# 标量子查询用于比较
high_earners = User.objects.filter(User.salary > avg_salary_subq)

# 表子查询用于 JOIN
posts_with_active_authors = Post.objects.join(
    active_users, Post.author_id == active_users.c.id
)

# 存在性子查询用于布尔条件
users_with_posts = User.objects.filter(has_posts_subq)

# 复杂子查询组合
dept_avg_salary = Employee.objects.filter(
    department_id=User.department_id
).aggregate(
    avg_salary=func.avg(Employee.salary)
).subquery()  # 自动推断为 scalar

high_performers = User.objects.filter(
    User.salary > dept_avg_salary * 1.2
).annotate(
    performance_ratio=User.salary / dept_avg_salary
)

# 子查询别名
named_subq = active_users.alias("active_users_subq")

# 访问表子查询的列
user_ids = active_users.c.id  # 访问 active_users 子查询的 id 列
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
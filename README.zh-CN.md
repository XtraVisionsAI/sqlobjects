# SQLObjects

[English](README.md) | [中文](README.zh-CN.md)

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Type checked: pyright](https://img.shields.io/badge/type%20checked-pyright-blue.svg)](https://github.com/microsoft/pyright)

一个现代化的、Django 风格的异步 ORM 库，基于 SQLAlchemy Core 构建，支持链式查询、Q 对象和关系加载。SQLObjects 将熟悉的 Django
ORM API 与 SQLAlchemy Core 的性能和灵活性相结合。

## ✨ 核心特性

- **🚀 Django 风格 API** - 为 Django 开发者提供熟悉直观的接口
- **⚡ 异步优先设计** - 为现代异步 Python 应用而构建
- **🔗 链式查询** - 流畅的查询构建和方法链
- **🎯 类型安全** - 完整的类型注解和运行时验证
- **📊 高性能** - 基于 SQLAlchemy Core 实现最佳性能
- **🔄 智能操作** - 自动 CREATE/UPDATE 检测和批量操作
- **🎣 生命周期钩子** - 全面的数据库操作信号系统
- **🗄️ 多数据库支持** - 无缝的多数据库配置和路由

## 🚀 快速开始

### 安装

```bash
pip install sqlobjects
```

### 基本用法

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn
from sqlobjects.database import init_db, create_tables

# 定义模型
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100, unique=True)
    age: Column[int] = IntegerColumn(nullable=True)
    is_active: Column[bool] = BooleanColumn(default=True)

# 初始化数据库
await init_db("sqlite+aiosqlite:///app.db")
await create_tables(ObjectModel)

# 创建和查询数据
user = await User.objects.create(
    username="alice", 
    email="alice@example.com", 
    age=25
)

# Django 风格的链式查询
active_users = await User.objects.filter(
    User.is_active == True
).order_by("-age").limit(10).all()

# 使用 Q 对象的复杂查询
from sqlobjects.queries import Q

users = await User.objects.filter(
    Q(User.age >= 18) & (Q(User.username.like("%admin%")) | Q(User.is_active == True))
).all()
```

## 📚 核心概念

### 模型定义

SQLObjects 使用 Django 风格的模型定义，支持自动表生成：

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, DateTimeColumn, foreign_key
from datetime import datetime

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    content: Column[str] = StringColumn(type="text")
    author_id: Column[int] = foreign_key("users.id")
    created_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)
    
    class Config:
        table_name = "blog_posts"  # 自定义表名
        ordering = ["-created_at"]  # 默认排序
```

### 查询构建

使用链式方法构建复杂查询：

```python
# 基本过滤和排序
posts = await Post.objects.filter(
    Post.title.like("%python%")
).order_by("-created_at").limit(5).all()

# 聚合和注解
from sqlobjects.expressions import func

user_stats = await User.objects.annotate(
    post_count=func.count(User.posts),
    latest_post=func.max(User.posts.created_at)
).filter(User.post_count > 0).all()

# 关系加载
posts = await Post.objects.select_related("author").prefetch_related("comments").all()
```

### 批量操作

针对大数据集的高性能批量操作：

```python
# 批量创建（比单个创建快 10-100 倍）
users_data = [
    {"username": f"user{i}", "email": f"user{i}@example.com"} 
    for i in range(1000)
]
await User.objects.bulk_create(users_data, batch_size=500)

# 批量更新
mappings = [
    {"id": 1, "is_active": False},
    {"id": 2, "is_active": True},
]
await User.objects.bulk_update(mappings, match_fields=["id"])

# 批量删除
user_ids = [1, 2, 3, 4, 5]
await User.objects.bulk_delete(user_ids, id_field="id")
```

### 会话管理

灵活的会话和事务管理：

```python
from sqlobjects.session import ctx_session, ctx_sessions

# 单数据库事务
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="bob")
    posts = await user.posts.using(session).all()
    # 成功时自动提交，出错时自动回滚

# 多数据库事务
async with ctx_sessions("main", "analytics") as sessions:
    user = await User.objects.using(sessions["main"]).create(username="alice")
    await Log.objects.using(sessions["analytics"]).create(message="User created")
```

### 生命周期钩子

全面的数据库操作信号系统：

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
    async def before_save(self, context):
        """在任何保存操作之前调用"""
        self.updated_at = datetime.now()
    
    async def after_create(self, context):
        """仅在创建后调用"""
        await self.send_welcome_email()
    
    async def before_delete(self, context):
        """在删除之前调用"""
        await self.cleanup_related_data()
```

## 🏗️ 架构

SQLObjects 建立在坚实的基础之上，具有清晰的架构原则：

- **SQLAlchemy Core** - 最大化性能和 SQL 生成控制
- **异步优先** - 整个库原生支持 async/await
- **类型安全** - 全面的类型注解和运行时验证
- **模块化设计** - 清晰的关注点分离和可扩展架构

## 📖 文档

### AI 助手规则（快速参考）

为 AI 编码助手优化的最佳实践和使用模式：

- [AI 规则概览](docs/rules/README.md) - 快速导航和用途
- [数据库和会话指南](docs/rules/01-database-session-guide.md) - 连接管理和事务
- [模型定义指南](docs/rules/02-model-definition-guide.md) - 模型创建和字段配置
- [查询操作指南](docs/rules/03-query-operations-guide.md) - 过滤、排序和数据检索
- [CRUD 操作指南](docs/rules/04-crud-operations-guide.md) - 创建、读取、更新、删除操作
- [关系指南](docs/rules/05-relationships-guide.md) - 模型关系和加载策略
- [验证和信号指南](docs/rules/06-validation-signals-guide.md) - 数据验证和生命周期钩子
- [性能指南](docs/rules/07-performance-guide.md) - 优化技术和最佳实践

**安装**: 
```bash
# 安装包
pip install sqlobjects

# 为你的 AI 助手安装规则
sqlobjects-install-rules amazonq  # 或 cursor, claude, kiro
```

### 功能文档

- [数据库设置](docs-zh/features/01-database-setup.md) - 数据库配置和连接管理
- [模型定义](docs-zh/features/02-model-definition.md) - 模型创建、字段和验证
- [数据查询](docs-zh/features/03-querying-data.md) - 查询构建、过滤和聚合
- [CRUD 操作](docs-zh/features/04-crud-operations.md) - 创建、读取、更新、删除操作
- [关系](docs-zh/features/05-relationships.md) - 模型关系和加载策略
- [验证和信号](docs-zh/features/06-validation-signals.md) - 数据验证和生命周期钩子
- [性能优化](docs-zh/features/07-performance-optimization.md) - 性能调优和最佳实践

### 设计文档

- [核心架构](docs-zh/design/01-core-architecture.md) - 系统架构和设计原则
- [数据操作](docs-zh/design/02-data-operations.md) - 查询执行和数据处理
- [字段系统](docs-zh/design/03-field-system.md) - 字段类型和类型系统
- [关系](docs-zh/design/04-relationships.md) - 关系实现细节
- [扩展](docs-zh/design/05-extensions.md) - 扩展点和自定义

## 🔧 高级功能

### 多数据库支持

```python
from sqlobjects.database import init_dbs

# 配置多个数据库
main_db, analytics_db = await init_dbs({
    "main": {"url": "postgresql+asyncpg://user:pass@localhost/main"},
    "analytics": {"url": "sqlite+aiosqlite:///analytics.db"}
}, default="main")

# 使用特定数据库
user = await User.objects.using("analytics").create(username="analyst")
```

### 性能优化

```python
# 大数据集的内存高效迭代
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)

# 字段选择性能优化
users = await User.objects.only("id", "username", "email").all()  # 只加载必要字段
live_data = await User.objects.defer("bio", "profile_image").all()  # 延迟加载重字段

# 字段级性能优化
class User(ObjectModel):
    bio: Column[str] = column(type="text", deferred=True)  # 延迟加载
    profile_image: Column[bytes] = column(type="binary", deferred=True)
```

### 高级查询

```python
# 子查询和复杂条件
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery(query_type="scalar")
older_users = await User.objects.filter(User.age > avg_age).all()

# 手动连接和锁定
posts = await Post.objects.join(
    User,  # 使用 Model 类（推荐）
    Post.author_id == User.id
).select_for_update(nowait=True).all()

# 需要时使用原生 SQL
users = await User.objects.raw(
    "SELECT * FROM users WHERE age > :age", 
    {"age": 18}
)
```

## 🧪 测试

SQLObjects 包含全面的测试覆盖：

```bash
# 运行所有测试
uv run pytest

# 运行特定测试类别
uv run pytest tests/unit/          # 单元测试
uv run pytest tests/integration/   # 集成测试
uv run pytest tests/performance/   # 性能测试

# 运行覆盖率测试
uv run pytest --cov=sqlobjects
```

## 🤝 贡献

我们欢迎贡献！请查看我们的开发指南：

1. **设计优先方法** - 所有更改都从设计分析开始
2. **类型安全** - 维护全面的类型注解
3. **测试覆盖** - 为所有新功能包含测试
4. **文档** - 为任何 API 更改更新文档

### 开发设置

```bash
# 克隆仓库
git clone https://github.com/XtraVisionsAI/sqlobjects.git
cd sqlobjects

# 安装开发依赖
uv sync --group dev --group test

# 运行预提交钩子
uv run pre-commit install

# 运行测试
uv run pytest
```

## 📋 路线图

查看我们的 [TODO.md](TODO.md) 了解计划功能：

- **v2.0**: 数据库健康检查、窗口函数、高级批量操作
- **v2.1**: 高级字段优化、查询性能工具
- **v2.2+**: CTE 支持、高级 SQL 函数

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- 基于优秀的 [SQLAlchemy](https://www.sqlalchemy.org/) 库构建
- 受 [Django ORM](https://docs.djangoproject.com/en/stable/topics/db/) API 设计启发
- 感谢所有贡献者和 Python 异步生态系统

---

**SQLObjects** - 适用于 Python 3.12+ 的现代异步 ORM
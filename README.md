# SQLObjects

[English](README.md) | [中文](README.zh-CN.md)

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Type checked: pyright](https://img.shields.io/badge/type%20checked-pyright-blue.svg)](https://github.com/microsoft/pyright)

A modern, Django-style async ORM library built on SQLAlchemy Core with chainable queries, Q objects, and relationship
loading. SQLObjects combines the familiar Django ORM API with the performance and flexibility of SQLAlchemy Core.

## ✨ Key Features

- **🚀 Django-style API** - Familiar and intuitive interface for Django developers
- **⚡ Async-first design** - Built for modern async Python applications
- **🔗 Chainable queries** - Fluent query building with method chaining
- **🎯 Type safety** - Full type annotations and runtime validation
- **📊 High performance** - Built on SQLAlchemy Core for optimal performance
- **🔄 Smart operations** - Automatic CREATE/UPDATE detection and bulk operations
- **🎣 Lifecycle hooks** - Comprehensive signal system for database operations
- **🗄️ Multi-database support** - Seamless multi-database configuration and routing

## 🚀 Quick Start

### Installation

```bash
pip install sqlobjects
```

### Basic Usage

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, IntegerColumn, BooleanColumn
from sqlobjects.database import init_db, create_tables

# Define your models
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50, unique=True)
    email: Column[str] = StringColumn(length=100, unique=True)
    age: Column[int] = IntegerColumn(nullable=True)
    is_active: Column[bool] = BooleanColumn(default=True)

# Initialize database
await init_db("sqlite+aiosqlite:///app.db")
await create_tables(ObjectModel)

# Create and query data
user = await User.objects.create(
    username="alice", 
    email="alice@example.com", 
    age=25
)

# Chainable queries with Django-style API
active_users = await User.objects.filter(
    User.is_active == True
).order_by("-age").limit(10).all()

# Complex queries with Q objects
from sqlobjects.queries import Q

users = await User.objects.filter(
    Q(User.age >= 18) & (Q(User.username.like("%admin%")) | Q(User.is_active == True))
).all()
```

## 📚 Core Concepts

### Model Definition

SQLObjects uses a Django-style model definition with automatic table generation:

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
        table_name = "blog_posts"  # Custom table name
        ordering = ["-created_at"]  # Default ordering
```

### Query Building

Build complex queries with chainable methods:

```python
# Basic filtering and ordering
posts = await Post.objects.filter(
    Post.title.like("%python%")
).order_by("-created_at").limit(5).all()

# Aggregation and annotation
from sqlobjects.expressions import func

user_stats = await User.objects.annotate(
    post_count=func.count(User.posts),
    latest_post=func.max(User.posts.created_at)
).filter(User.post_count > 0).all()

# Relationship loading
posts = await Post.objects.select_related("author").prefetch_related("comments").all()
```

### Bulk Operations

High-performance bulk operations for large datasets:

```python
# Bulk create (10-100x faster than individual creates)
users_data = [
    {"username": f"user{i}", "email": f"user{i}@example.com"} 
    for i in range(1000)
]
await User.objects.bulk_create(users_data, batch_size=500)

# Bulk update
mappings = [
    {"id": 1, "is_active": False},
    {"id": 2, "is_active": True},
]
await User.objects.bulk_update(mappings, match_fields=["id"])

# Bulk delete
user_ids = [1, 2, 3, 4, 5]
await User.objects.bulk_delete(user_ids, id_field="id")
```

### Session Management

Flexible session and transaction management:

```python
from sqlobjects.session import ctx_session, ctx_sessions

# Single database transaction
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="bob")
    posts = await user.posts.using(session).all()
    # Automatic commit on success, rollback on error

# Multi-database transactions
async with ctx_sessions("main", "analytics") as sessions:
    user = await User.objects.using(sessions["main"]).create(username="alice")
    await Log.objects.using(sessions["analytics"]).create(message="User created")
```

### Lifecycle Hooks

Comprehensive signal system for database operations:

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
    async def before_save(self, context):
        """Called before any save operation"""
        self.updated_at = datetime.now()
    
    async def after_create(self, context):
        """Called only after creation"""
        await self.send_welcome_email()
    
    async def before_delete(self, context):
        """Called before deletion"""
        await self.cleanup_related_data()
```

## 🏗️ Architecture

SQLObjects is built on a solid foundation with clear architectural principles:

- **SQLAlchemy Core** - Maximum performance and control over SQL generation
- **Async-first** - Native async/await support throughout the library
- **Type safety** - Comprehensive type annotations and runtime validation
- **Modular design** - Clean separation of concerns and extensible architecture

## 📖 Documentation

### Feature Documentation

- [Database Setup](docs/features/01-database-setup.md) - Database configuration and connection management
- [Model Definition](docs/features/02-model-definition.md) - Model creation, fields, and validation
- [Querying Data](docs/features/03-querying-data.md) - Query building, filtering, and aggregation
- [CRUD Operations](docs/features/04-crud-operations.md) - Create, read, update, delete operations
- [Relationships](docs/features/05-relationships.md) - Model relationships and loading strategies
- [Validation & Signals](docs/features/06-validation-signals.md) - Data validation and lifecycle hooks
- [Performance Optimization](docs/features/07-performance-optimization.md) - Performance tuning and best practices

### Design Documentation

- [Core Architecture](docs/design/01-core-architecture.md) - System architecture and design principles
- [Data Operations](docs/design/02-data-operations.md) - Query execution and data processing
- [Field System](docs/design/03-field-system.md) - Field types and type system
- [Relationships](docs/design/04-relationships.md) - Relationship implementation details
- [Extensions](docs/design/05-extensions.md) - Extension points and customization

## 🔧 Advanced Features

### Multi-Database Support

```python
from sqlobjects.database import init_dbs

# Configure multiple databases
main_db, analytics_db = await init_dbs({
    "main": {"url": "postgresql+asyncpg://user:pass@localhost/main"},
    "analytics": {"url": "sqlite+aiosqlite:///analytics.db"}
}, default="main")

# Use specific databases
user = await User.objects.using("analytics").create(username="analyst")
```

### Performance Optimization

```python
# Memory-efficient iteration for large datasets
async for user in User.objects.iterator(chunk_size=1000):
    await process_user(user)

# Field selection for performance
users = await User.objects.only("id", "username", "email").all()  # Load only needed fields
live_data = await User.objects.defer("bio", "profile_image").all()  # Defer heavy fields

# Field-level performance optimization
class User(ObjectModel):
    bio: Column[str] = column(type="text", deferred=True)  # Lazy loading
    profile_image: Column[bytes] = column(type="binary", deferred=True)
```

### Advanced Querying

```python
# Subqueries and complex conditions
avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery(query_type="scalar")
older_users = await User.objects.filter(User.age > avg_age).all()

# Manual joins and locking
posts = await Post.objects.join(
    User.__table__, 
    Post.author_id == User.id
).select_for_update(nowait=True).all()

# Raw SQL when needed
users = await User.objects.raw(
    "SELECT * FROM users WHERE age > :age", 
    {"age": 18}
)
```

## 🧪 Testing

SQLObjects includes comprehensive test coverage:

```bash
# Run all tests
uv run pytest

# Run specific test categories
uv run pytest tests/unit/          # Unit tests
uv run pytest tests/integration/   # Integration tests
uv run pytest tests/performance/   # Performance tests

# Run with coverage
uv run pytest --cov=sqlobjects
```

## 🤝 Contributing

We welcome contributions! Please see our development guidelines:

1. **Design-first approach** - All changes start with design analysis
2. **Type safety** - Maintain comprehensive type annotations
3. **Test coverage** - Include tests for all new functionality
4. **Documentation** - Update docs for any API changes

### Development Setup

```bash
# Clone the repository
git clone https://github.com/XtraVisionsAI/sqlobjects.git
cd sqlobjects

# Install development dependencies
uv sync --group dev --group test

# Run pre-commit hooks
uv run pre-commit install

# Run tests
uv run pytest
```

## 📋 Roadmap

See our [TODO.md](TODO.md) for planned features:

- **v2.0**: Database health checks, window functions, advanced bulk operations
- **v2.1**: Advanced field optimization, query performance tools
- **v2.2+**: CTE support, advanced SQL functions

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built on the excellent [SQLAlchemy](https://www.sqlalchemy.org/) library
- Inspired by [Django ORM](https://docs.djangoproject.com/en/stable/topics/db/) API design
- Thanks to all contributors and the Python async ecosystem

---

**SQLObjects** - Modern async ORM for Python 3.12+
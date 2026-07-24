# SQLObjects Relationship Processing Design Document

## Overview

The SQLObjects relationship processing module provides comprehensive model relationship support through a unified
relationship() function and Column descriptor integration. It achieves high-performance relational data access through
RelatedObject/RelatedCollection lazy loading, QuerySet-integrated select_related/prefetch_related, and custom QuerySet configuration.

## Core Features

### 1. Unified relationship() Definition

Supports multiple relationship types through unified relationship() function and Column descriptor integration:

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, column
from sqlobjects.fields.relations import relationship, Related
from sqlalchemy import ForeignKey

class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=100)
    author_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
  
    # Relationship field - returns Related container
    author: Related[User] = relationship("User", foreign_keys="author_id")

# relationship() returns Related container:
# - Related wraps RelationshipProperty
# - ModelProcessor extracts RelationshipDescriptor from Related
# - RelationshipDescriptor returns RelatedObject or RelatedCollection proxies

class Tag(ObjectModel):
    name: Column[str] = StringColumn(length=50)

# Many-to-many relationship - using secondary parameter
class PostTag(ObjectModel):
    post_id: Column[int] = column(type="integer", foreign_key=ForeignKey("posts.id"))
    tag_id: Column[int] = column(type="integer", foreign_key=ForeignKey("tags.id"))

# Dynamically add relationship fields
Post.tags = relationship("Tag", secondary="post_tags")
Tag.posts = relationship("Post", secondary="post_tags")
```

### 2. JOIN Query Optimization

Intelligent JOIN query construction with support for nested relationships and alias handling:

```python
# Single-level relationship preloading
posts = await Post.objects.select_related("author").all()

# Multi-level relationship preloading
comments = await Comment.objects.select_related(
    "post__author", "user__profile"
).all()

# Multiple relationships preloaded simultaneously
posts = await Post.objects.select_related(
    "author", "category"
).all()
```

### 3. Advanced Prefetch Loading Strategy

QuerySet-integrated prefetch_related with support for custom QuerySet configuration and RelatedObject/RelatedCollection lazy loading:

```python
# Simple prefetch - using default QuerySet
users = await User.objects.prefetch_related("posts").all()

# Advanced prefetch configuration - passing custom QuerySet
users = await User.objects.prefetch_related(
    published_posts=Post.objects.filter(Post.is_published == True)
                               .order_by("-created_at")
                               .limit(5)
).all()

# Hybrid usage - supports both strings and QuerySet configurations
users = await User.objects.prefetch_related(
    "profile",  # Simple prefetch
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=30)
    ).order_by("-created_at")
).all()

# QueryExecutor handles prefetch:
# 1. Concurrently executes all prefetch queries
# 2. Groups results by foreign key relationships
# 3. Associates results with main instances

# RelatedCollection lazy loading
user = await User.objects.first()
# user.posts returns RelatedCollection proxy
# await user.posts.fetch() actually loads the data
```

### 4. Many-to-Many Relationships

Complete many-to-many relationship support, including intermediate table management and relationship operations:

```python
# Many-to-many relationship definition
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, column
from sqlobjects.fields.relations import relationship, Related
from sqlalchemy import ForeignKey
from datetime import datetime

class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)

class Role(ObjectModel):
    name: Column[str] = StringColumn(length=50)

# Intermediate table
class UserRole(ObjectModel):
    user_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
    role_id: Column[int] = column(type="integer", foreign_key=ForeignKey("roles.id"))
    assigned_at: Column[datetime] = column(type="datetime", default_factory=datetime.now)

User.roles = relationship("Role", secondary="user_roles")

# Relationship operations
user = await User.objects.get(User.id == 1)
roles = await user.roles.fetch()  # Get user roles
```

### 5. Cascade Strategy

SQLObjects unifies cascade behavior across two cooperating levels (`sqlobjects/cascade.py`):

**Database level — `ondelete` / `onupdate`.** Foreign-key constraint behaviors enforced by the database
engine. Configured on the FK itself via `foreign_key(..., ondelete="CASCADE")` (or the `OnDelete` /
`OnUpdate` enums, whose values are `CASCADE`, `SET NULL`, `RESTRICT`, `NO ACTION`). These require no ORM
round-trips: the database removes or nulls dependent rows on its own.

**ORM level — `cascade`.** Application-layer cascade configured on `relationship(cascade=...)`. Options are
modeled by `CascadeOption` (`save-update`, `merge`, `delete`, `delete-orphan`, `refresh-expire`, `all`) with
convenient bundles in `CascadePresets` (e.g. `ALL_DELETE_ORPHAN = "all, delete-orphan"`). ORM cascades run
through the ORM so they emit lifecycle signals and can traverse relationships the database has no constraint for.

**Automatic detection and dispatch.** `Model.delete(cascade=None)` auto-detects whether cascade handling is
needed by calling `_has_on_delete_relations()` (`model.py`), which inspects the model's relationships for a
`cascade` string containing `delete`/`all` or an `on_delete` other than `NO ACTION`. When cascade is needed
(or forced with `cascade=True`), the delete is dispatched to `CascadeExecutor.execute_delete_operation()`;
otherwise a direct `_delete_internal()` runs. `cascade=False` always skips cascade.

**Components.**

- **OnDelete / OnUpdate**: Enums for database-level FK constraint behaviors.
- **CascadeOption / CascadePresets**: ORM-level cascade options and preset combinations; `CascadeType` and
  the `normalize_*` helpers coerce enum/str/set inputs into SQLAlchemy cascade strings.
- **DependencyResolver**: Orders instances for cascade save via topological sort, with DFS cycle detection
  (`CyclicDependencyError` on circular dependencies).
- **CascadeExecutor**: Executes save/delete/update cascades with session management and signal compatibility.
  For QuerySet deletes it picks a strategy automatically (`full` when delete signals are present, `fast` when
  cascade-delete relations exist, `none` otherwise).

## Module Architecture

### Core Components

**Relationship Definition Layer**

- **relationship()**: Unified relationship definition function, returns Related container
- **Related**: Container wrapping RelationshipProperty for type hints
- **RelationshipDescriptor**: Relationship descriptor, handles relationship field access and proxying
- **RelationshipProperty**: Relationship property definition, stores relationship metadata

**Lazy Loading Layer**

- **RelatedObject**: Proxy for single relationship fields (ForeignKey, OneToOne)
- **RelatedCollection**: Proxy for collection relationships (OneToMany, ManyToMany)
- **FieldCacheMixin**: Integrated in ObjectModel, automatically handles proxy objects

**Query Integration Layer**

- **QuerySet.select_related()**: JOIN preloading, supports strings and field expressions
- **QuerySet.prefetch_related()**: Separate query prefetch, supports custom QuerySet configuration
- **QueryExecutor**: Unified handling of prefetch query execution and result association

**Cascade Layer (`cascade.py`)**

- **OnDelete / OnUpdate**: Database-level FK constraint behaviors
- **CascadeOption / CascadePresets**: ORM-level cascade options and presets
- **DependencyResolver**: Topological ordering and cycle detection for cascade save
- **CascadeExecutor**: Executes cascade save/delete/update; auto-selects the delete strategy for QuerySets

### Design Philosophy

**Unified Integration**: relationship() function returns Related container, ModelProcessor extracts descriptor
**Lazy Loading**: RelatedObject and RelatedCollection provide transparent lazy loading and caching
**Flexible Prefetch**: prefetch_related supports hybrid usage of strings and custom QuerySets
**Concurrent Optimization**: QueryExecutor concurrently executes multiple prefetch queries for improved performance
**Automatic Association**: Automatically groups and associates prefetch results based on foreign key relationships
**Error Tolerance**: Returns empty lists when prefetch fails, doesn't affect main query

### Integration with Other Modules

**Core Architecture Module**: Registers relationship definitions through ModelProcessor
**Data Operations Module**: Integrates select_related and prefetch_related methods
**Field System Module**: Supports expression operations on relationship fields

## API Reference

### Relationship Definition

```python
# Full signature (sqlobjects/fields/relations/utils.py)
relationship(
    argument,                  # target model class or its string name
    *,
    foreign_keys=None,         # FK field name(s) on this model (many-to-one side)
    remote_fields=None,        # FK field name(s) on the related model (one-to-many/one-to-one side)
    back_populates=None,       # name of the reverse relationship attribute
    backref=None,              # auto-create the reverse relationship (mutually exclusive with back_populates)
    lazy="select",             # loading strategy
    uselist=None,              # whether the relationship returns a collection
    secondary=None,            # M2M association table name or M2MTable instance
    primaryjoin=None,
    secondaryjoin=None,
    order_by=None,             # default ordering for collections
    cascade=None,              # ORM-level cascade behavior (see Cascade Strategy)
    passive_deletes=False,
    **kwargs
)

# Many-to-one / foreign key relationship
author: Related[User] = relationship("User", foreign_keys="author_id", back_populates="posts")

# One-to-many (reverse) relationship
posts: Related[list[Post]] = relationship("Post", back_populates="author")

# Many-to-many relationship
tags: Related[list[Tag]] = relationship("Tag", secondary="post_tags", back_populates="posts")

# One-to-one relationship
# There is no `unique=` parameter on relationship(). A one-to-one is expressed with
# uselist=False on the parent side plus a UNIQUE foreign key on the child side.
#   User side:    profile: Related[Profile] = relationship("Profile", back_populates="user", uselist=False)
#   Profile side: user_id: Column[int] = foreign_key("User.id", unique=True)
#                 user = relationship("User", back_populates="profile")
```

### Relationship Loading

```python
# JOIN preloading
.select_related(*fields)  # Use strings to specify relationship fields

# Separate query prefetch
.prefetch_related(*fields, **queryset_configs)  # Supports strings and custom QuerySets

# Relationship filtering
.filter(Model.relation__field == value)
```

### Relationship Operations

```python
# Relationship access
instance.relation_name  # Get relationship proxy (RelatedObject or RelatedCollection)
await instance.relation_name.fetch()  # Fetch related data

# Collection operations
await instance.relation_name.count()  # Count related objects

# Relationship modification
await instance.relation_name.add(related_instance)
await instance.relation_name.remove(related_instance)
await instance.relation_name.clear()
```

## Usage Guide

### Basic Usage

```python
# Basic relationship definition
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, column
from sqlobjects.fields.relations import relationship, Related
from sqlalchemy import ForeignKey

class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=100)
    author_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
  
    author: Related[User] = relationship("User", foreign_keys="author_id")

# Relationship queries
posts = await Post.objects.select_related("author").all()
for post in posts:
    print(f"{post.title} by {post.author.name}")

# Reverse relationship
User.posts: Related[list[Post]] = relationship("Post", foreign_keys="Post.author_id")
user = await User.objects.get(User.id == 1)
user_posts = await user.posts.fetch()
```

### Advanced Usage

```python
# Complex relationship structure
class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)

class Category(ObjectModel):
    name: Column[str] = StringColumn(length=50)

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=100)
    author_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
    category_id: Column[int] = column(type="integer", foreign_key=ForeignKey("categories.id"))
  
    author: Related[User] = relationship("User", foreign_keys="author_id")
    category: Related[Category] = relationship("Category", foreign_keys="category_id")

class Comment(ObjectModel):
    content: Column[str] = StringColumn(length=500)
    post_id: Column[int] = column(type="integer", foreign_key=ForeignKey("posts.id"))
    user_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
  
    post: Related[Post] = relationship("Post", foreign_keys="post_id")
    user: Related[User] = relationship("User", foreign_keys="user_id")

# Multi-level relationship preloading
comments = await Comment.objects.select_related(
    "post__author",      # Comment -> Post -> Author
    "post__category",    # Comment -> Post -> Category
    "user"               # Comment -> User
).all()

# Advanced prefetch configuration
users = await User.objects.prefetch_related(
    # Simple prefetch
    "profile",
  
    # Custom prefetch query
    published_posts=Post.objects.filter(
        Post.is_published == True
    ).select_related("category").order_by("-created_at").limit(5),
  
    # Nested prefetch
    recent_comments=Comment.objects.filter(
        Comment.created_at >= datetime.now() - timedelta(days=7)
    ).select_related("post").order_by("-created_at")
).all()

# Many-to-many relationships
class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)

class Role(ObjectModel):
    name: Column[str] = StringColumn(length=50)
    permissions: Column[list[str]] = JsonColumn(default=list)

class UserRole(ObjectModel):
    user_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
    role_id: Column[int] = column(type="integer", foreign_key=ForeignKey("roles.id"))
    assigned_at: Column[datetime] = column(type="datetime", default_factory=datetime.now)
    assigned_by: Column[int] = column(type="integer")

User.roles: Related[list[Role]] = relationship("Role", secondary="user_roles")
Role.users: Related[list[User]] = relationship("User", secondary="user_roles")

# Many-to-many operations
user = await User.objects.get(User.id == 1)
admin_role = await Role.objects.get(Role.name == "admin")

# Add relationship
await UserRole.objects.create(
    user_id=user.id,
    role_id=admin_role.id,
    assigned_by=current_user.id
)

# Query many-to-many relationships
users_with_roles = await User.objects.prefetch_related("roles").all()
for user in users_with_roles:
    roles = await user.roles.fetch()
    print(f"{user.name}: {[role.name for role in roles]}")

# Complex relationship queries
# Find users with specific roles
admin_users = await User.objects.filter(
    User.roles__name == "admin"
).distinct().all()

# Find recently active users and their posts
active_users = await User.objects.filter(
    User.posts__created_at >= datetime.now() - timedelta(days=30)
).prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=30)
    ).order_by("-created_at")
).distinct().all()
```
# SQLObjects Relationship Processing Design Document

## Overview

The SQLObjects relationship processing module provides comprehensive model relationship support through a unified
relationship() function and Column descriptor integration. It achieves high-performance relational data access through
RelationFieldProxy lazy loading, QuerySet-integrated select_related/prefetch_related, and custom QuerySet configuration.

## Core Features

### 1. Unified relationship() Definition

Supports multiple relationship types through unified relationship() function and Column descriptor integration:

```python
class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=100)
    author_id: Column[int] = foreign_key("users.id")  # Foreign key field
  
    # Relationship field - unified processing with Column descriptor
    author: Column[User] = relationship("User", foreign_keys="author_id")

# Column descriptor automatically recognizes relationship fields:
# - Sets _is_relationship = True
# - Uses RelationshipDescriptor for access handling
# - Integrates into ModelProcessor's _relationships dictionary

class Tag(ObjectModel):
    name: Column[str] = StringColumn(length=50)

# Many-to-many relationship - using through parameter
class PostTag(ObjectModel):
    post_id: Column[int] = foreign_key("posts.id")
    tag_id: Column[int] = foreign_key("tags.id")

# Dynamically add relationship fields
Post.tags = relationship("Tag", through="PostTag")
Tag.posts = relationship("Post", through="PostTag")
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

QuerySet-integrated prefetch_related with support for custom QuerySet configuration and RelationFieldProxy lazy loading:

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

# RelationFieldProxy lazy loading
user = await User.objects.first()
# user.posts returns RelationFieldProxy
# await user.posts.fetch() actually loads the data
```

### 4. Many-to-Many Relationships

Complete many-to-many relationship support, including intermediate table management and relationship operations:

```python
# Many-to-many relationship definition
class User(ObjectModel):
    name: str = str_column(length=50)

class Role(ObjectModel):
    name: str = str_column(length=50)

# Intermediate table
class UserRole(ObjectModel):
    user_id: int = int_column()
    role_id: int = int_column()
    assigned_at: datetime = datetime_column(default=datetime.now)

User.roles = relationship("Role", through="UserRole")

# Relationship operations
user = await User.objects.get(User.id == 1)
roles = await user.roles.all()  # Get user roles
```

## Module Architecture

### Core Components

**Relationship Definition Layer**

- **relationship()**: Unified relationship definition function, returns Column descriptor
- **RelationshipDescriptor**: Relationship descriptor, handles relationship field access and proxying
- **RelationshipProperty**: Relationship property definition, stores relationship metadata

**Lazy Loading Layer**

- **RelationFieldProxy**: Relationship field proxy, supports lazy loading and caching
- **FieldCacheMixin**: Integrated in ObjectModel, automatically handles proxy objects

**Query Integration Layer**

- **QuerySet.select_related()**: JOIN preloading, supports strings and field expressions
- **QuerySet.prefetch_related()**: Separate query prefetch, supports custom QuerySet configuration
- **QueryExecutor**: Unified handling of prefetch query execution and result association

### Design Philosophy

**Unified Integration**: relationship() function unified with Column descriptors, simplifying API design
**Lazy Loading**: RelationFieldProxy provides transparent lazy loading and caching mechanism
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
# Foreign key relationship
relationship(target_model, foreign_keys=None, back_populates=None)

# Many-to-many relationship
relationship(target_model, through=None, back_populates=None)

# One-to-one relationship
relationship(target_model, foreign_keys=None, unique=True)
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
instance.relation_name  # Get relationship object
await instance.relation_name.all()  # Get relationship list

# Relationship modification
await instance.relation_name.add(related_instance)
await instance.relation_name.remove(related_instance)
await instance.relation_name.clear()
```

## Usage Guide

### Basic Usage

```python
# Basic relationship definition
class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=100)
    author_id: Column[int] = IntegerColumn()
  
    author = relationship("User", foreign_keys="author_id")

# Relationship queries
posts = await Post.objects.select_related("author").all()
for post in posts:
    print(f"{post.title} by {post.author.name}")

# Reverse relationship
User.posts = relationship("Post", foreign_keys="Post.author_id")
user = await User.objects.get(User.id == 1)
user_posts = await user.posts.all()
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
    author_id: Column[int] = IntegerColumn()
    category_id: Column[int] = IntegerColumn()
  
    author = relationship("User", foreign_keys="author_id")
    category = relationship("Category", foreign_keys="category_id")

class Comment(ObjectModel):
    content: Column[str] = StringColumn(length=500)
    post_id: Column[int] = IntegerColumn()
    user_id: Column[int] = IntegerColumn()
  
    post = relationship("Post", foreign_keys="post_id")
    user = relationship("User", foreign_keys="user_id")

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
    user_id: Column[int] = IntegerColumn()
    role_id: Column[int] = IntegerColumn()
    assigned_at: Column[datetime] = DateTimeColumn(default=datetime.now)
    assigned_by: Column[int] = IntegerColumn()

User.roles = relationship("Role", through="UserRole")
Role.users = relationship("User", through="UserRole")

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
    roles = await user.roles.all()
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
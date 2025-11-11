# Relations and Joins

## Overview

SQLObjects provides comprehensive relationship support, including automatic JOIN optimization, lazy and eager loading
strategies, and intuitive relationship traversal syntax.

## Quick Start

### Basic Relations

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, TextColumn, column
from sqlobjects.fields.relations import relationship, Related
from sqlalchemy import ForeignKey

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    content: Column[str] = TextColumn()
    author_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))

    # Define relationships using unified relationship() function
    author: Related[User] = relationship("User", foreign_keys="author_id")

# Add reverse relationship to User
User.posts: Related[list[Post]] = relationship("Post", foreign_keys="Post.author_id")
```

### Using Relations

```python
# Access related objects
post = await Post.objects.get(Post.id == 1)
author = await post.author.fetch()  # Lazy loading via RelatedObject proxy

# Reverse relationship
user = await User.objects.get(User.id == 1)
user_posts = await user.posts.fetch()  # Fetch via RelatedCollection proxy
```

## Relationship Types

### One-to-Many (Foreign Key)

```python
class Department(ObjectModel):
    name: Column[str] = StringColumn(length=100)

class Employee(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    department_id: Column[int] = column(type="integer", foreign_key=ForeignKey("departments.id"))

    # Many-to-one relationship
    department: Related[Department] = relationship("Department", foreign_keys="department_id")

# Add reverse relationship to Department
Department.employees: Related[list[Employee]] = relationship("Employee", foreign_keys="Employee.department_id")

# Usage
employee = await Employee.objects.get(Employee.id == 1)
dept = await employee.department.fetch()  # Single object via RelatedObject

department = await Department.objects.get(Department.id == 1)
employees = await department.employees.fetch()  # List via RelatedCollection
```

### One-to-One

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)

class Profile(ObjectModel):
    bio: Column[str] = TextColumn()
    user_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"), unique=True)

    # One-to-one relationship
    user: Related[User] = relationship("User", foreign_keys="user_id")

# Add reverse one-to-one relationship to User
User.profile: Related[Profile] = relationship("Profile", foreign_keys="Profile.user_id", uselist=False)

# Usage
profile = await Profile.objects.get(Profile.id == 1)
user = await profile.user.fetch()  # Single object via RelatedObject

user = await User.objects.get(User.id == 1)
profile = await user.profile.fetch()  # Single object (or None) via RelatedObject
```

### Many-to-Many

```python
class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)

class Tag(ObjectModel):
    name: Column[str] = StringColumn(length=50)

# Association table
class PostTag(ObjectModel):
    post_id: Column[int] = column(type="integer", foreign_key=ForeignKey("posts.id"), primary_key=True)
    tag_id: Column[int] = column(type="integer", foreign_key=ForeignKey("tags.id"), primary_key=True)

# Add many-to-many relationships using secondary parameter
Post.tags: Related[list[Tag]] = relationship("Tag", secondary="post_tags")
Tag.posts: Related[list[Post]] = relationship("Post", secondary="post_tags")

# Usage
post = await Post.objects.get(Post.id == 1)
tags = await post.tags.fetch()  # List of tags via ManyToManyRelation

tag = await Tag.objects.get(Tag.id == 1)
posts = await tag.posts.fetch()  # List of posts via ManyToManyRelation
```

## Loading Strategies

### Lazy Loading (Default)

```python
# Lazy loading - queries database when accessed
post = await Post.objects.get(Post.id == 1)
author = await post.author.fetch()  # Executes separate query here

# N+1 query problem example
posts = await Post.objects.all()
for post in posts:
    author = await post.author.fetch()  # Executes N additional queries!
```

### Eager Loading with select_related

```python
# Use select_related for foreign key relationships (JOIN)
posts = await Post.objects.select_related("author").all()
for post in posts:
    author = post.author  # No additional queries - already loaded

# Multiple relationships
posts = await Post.objects.select_related("author", "category").all()

# Nested relationships
comments = await Comment.objects.select_related("post__author").all()

# String path syntax (Django-style)
posts = await Post.objects.select_related("author").all()
```

### Eager Loading with prefetch_related

```python
# Use prefetch_related for reverse foreign keys and many-to-many relationships
users = await User.objects.prefetch_related("posts").all()
for user in users:
    posts = await user.posts.fetch()  # No additional queries

# Many-to-many relationships
posts = await Post.objects.prefetch_related("tags").all()
for post in posts:
    tags = await post.tags.fetch()  # No additional queries

# Multiple prefetches
users = await User.objects.prefetch_related("posts", "groups", "permissions").all()

# String path syntax (Django-style)
users = await User.objects.prefetch_related("posts").all()
```

### Advanced Prefetch Configuration

```python
# Advanced prefetch with filtering and ordering
users = await User.objects.prefetch_related(
    published_posts=Post.objects.filter(Post.is_published == True)
                               .order_by('-created_at')
                               .limit(5)
).all()

# Multiple advanced configurations
users = await User.objects.prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=30)
    ).order_by('-created_at'),
    popular_posts=Post.objects.filter(Post.view_count > 1000)
                             .order_by('-view_count')
                             .limit(3)
).all()

# Mix simple and advanced prefetches
users = await User.objects.prefetch_related(
    'profile',  # Simple prefetch
    recent_comments=Comment.objects.filter(
        Comment.created_at >= datetime.now() - timedelta(days=7)
    ).order_by('-created_at')
).all()

# Access prefetched data
for user in users:
    # Advanced prefetch results are directly accessible
    recent_posts = user.recent_posts  # Filtered/ordered post list
    popular_posts = user.popular_posts  # Popular post list
```

### Combining Loading Strategies

```python
# Combine select_related and prefetch_related
posts = await Post.objects.select_related("author").prefetch_related("tags", "comments").all()

for post in posts:
    author = post.author  # From JOIN (select_related)
    tags = await post.tags.all()  # From prefetch (prefetch_related)
    comments = await post.comments.all()  # From prefetch
```

## Advanced Relationship Queries

### Filtering by Related Fields

```python
# Filter by foreign key fields
posts = await Post.objects.filter(Post.author.username == "john").all()

# Filter by reverse relationships
users = await User.objects.filter(User.posts.title.like("%python%")).all()

# Multiple relationship filters
posts = await Post.objects.filter(
    Post.author.is_active == True,
    Post.category.name == "Technology"
).all()
```

### Annotations on Relations

```python
from sqlobjects.expressions import func

# Count related objects
users = await User.objects.annotate(
    post_count=func.count(User.posts)
).all()

# Aggregate related fields
users = await User.objects.annotate(
    latest_post=func.max(User.posts.created_at),
    avg_post_length=func.avg(func.length(User.posts.content))
).all()

# Filter by aggregated values
active_authors = await User.objects.annotate(
    post_count=func.count(User.posts)
).filter(
    User.post_count > 5
).all()
```

### Subqueries on Relations

```python
# Exists subquery
has_posts = Post.objects.filter(Post.author_id == User.id).subquery(query_type="exists")
authors = await User.objects.filter(has_posts).all()

# Scalar subquery
latest_post_date = Post.objects.filter(
    Post.author_id == User.id
).aggregate(
    latest=func.max(Post.created_at)
).subquery(query_type="scalar")

active_authors = await User.objects.annotate(
    latest_post_date=latest_post_date
).filter(
    User.latest_post_date >= datetime.now() - timedelta(days=30)
).all()
```

## Manual Joins

### Explicit JOIN Operations

```python
# Inner join
posts_with_authors = await Post.objects.join(
    User, Post.author_id == User.id
).all()

# Left join
all_posts = await Post.objects.leftjoin(
    User, Post.author_id == User.id
).all()

# Multiple joins
posts_with_details = await Post.objects.join(
    User, Post.author_id == User.id
).join(
    Category, Post.category_id == Category.id
).all()
```

### JOIN with Subqueries

```python
# Join with subquery
active_users = User.objects.filter(User.is_active == True).subquery("active_users")
posts = await Post.objects.join(
    active_users, 
    Post.author_id == active_users.c.id
).all()
```

## Relationship Management

### Adding Related Objects

```python
# Create related objects
user = await User.objects.create(username="author")
post = await Post.objects.create(
    title="My Post",
    author_id=user.id  # Set foreign key
)

# Many-to-many relationships
post = await Post.objects.get(Post.id == 1)
tag = await Tag.objects.get(Tag.id == 1)

# Add to many-to-many (requires manual association table management)
await PostTag.objects.create(post_id=post.id, tag_id=tag.id)
```

### Bulk Relationship Operations

```python
# Bulk create with relationships
posts_data = [
    {"title": "Post 1", "author_id": 1, "category_id": 1},
    {"title": "Post 2", "author_id": 1, "category_id": 2},
    {"title": "Post 3", "author_id": 2, "category_id": 1},
]
posts = await Post.objects.bulk_create(posts_data)

# Bulk many-to-many associations
associations = [
    {"post_id": 1, "tag_id": 1},
    {"post_id": 1, "tag_id": 2},
    {"post_id": 2, "tag_id": 1},
]
await PostTag.objects.bulk_create(associations)
```

## Performance Optimization

### Best Practices for Relationship Loading

```python
# Good: Use select_related for foreign keys
posts = await Post.objects.select_related("author", "category").all()

# Good: Use prefetch_related for reverse relationships
users = await User.objects.prefetch_related("posts", "comments").all()

# Avoid: N+1 queries
posts = await Post.objects.all()
for post in posts:
    author = await post.author.fetch()  # N additional queries!

# Good: Combine loading strategies
posts = await Post.objects.select_related("author").prefetch_related("tags").all()
```

### Selective Field Loading

```python
# Load only needed fields from related objects
posts = await Post.objects.select_related("author").only(
    "title", "content", "author__username", "author__email"
).all()

# Defer heavy fields from related objects
posts = await Post.objects.select_related("author").defer(
    "content", "author__bio"
).all()
```

### Relationship Counting

```python
# Efficient counting without loading objects
user_count = await User.objects.filter(User.posts__isnull=False).distinct().count()

# Counting with annotations
users_with_counts = await User.objects.annotate(
    post_count=func.count(User.posts),
    comment_count=func.count(User.comments)
).all()
```

## Complex Relationship Patterns

### Self-Referencing Relations

```python
class Category(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    parent_id: Column[int] = column(type="integer", foreign_key=ForeignKey("categories.id"), nullable=True)

    # Self-referencing relationships
    parent: Related["Category"] = relationship("Category", foreign_keys="parent_id", uselist=False)
    children: Related[list["Category"]] = relationship("Category", foreign_keys="Category.parent_id")

# Usage
category = await Category.objects.get(Category.id == 1)
parent = await category.parent.fetch()
children = await category.children.fetch()
```

### Polymorphic Relations

```python
class Content(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    content_type: Column[str] = StringColumn(length=50)

class Article(Content):
    body: Column[str] = TextColumn()

class Video(Content):
    duration: Column[int] = IntegerColumn()
    video_url: Column[str] = StringColumn(length=500)

# Query polymorphic relationships
contents = await Content.objects.filter(Content.content_type == "article").all()
```

### Through Model Relations

```python
class Membership(ObjectModel):
    user_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"), primary_key=True)
    group_id: Column[int] = column(type="integer", foreign_key=ForeignKey("groups.id"), primary_key=True)
    role: Column[str] = StringColumn(length=50, default="member")
    joined_at: Column[datetime] = column(type="datetime", default_factory=datetime.now)

class User(ObjectModel):
    groups: Related[list["Group"]] = relationship(
        "Group",
        secondary="memberships",
        back_populates="users"
    )

class Group(ObjectModel):
    users: Related[list["User"]] = relationship(
        "User",
        secondary="memberships", 
        back_populates="groups"
    )

# Access through model data
memberships = await Membership.objects.filter(
    Membership.user_id == 1,
    Membership.role == "admin"
).all()
```

## Best Practices

### Relationship Design

```python
# Use descriptive relationship names
class Order(ObjectModel):
    customer_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
    customer: Related["User"] = relationship("User", back_populates="orders")

class User(ObjectModel):
    orders: Related[list["Order"]] = relationship("Order", back_populates="customer")
```

### Loading Strategy Selection

```python
# Use select_related for:
# - Foreign key relationships (many-to-one)
# - One-to-one relationships
posts = await Post.objects.select_related("author", "category").all()

# Use prefetch_related for:
# - Reverse foreign key relationships (one-to-many)
# - Many-to-many relationships
users = await User.objects.prefetch_related("posts", "groups").all()
```

### Error Handling

```python
from sqlobjects.exceptions import DoesNotExist

# Handle missing related objects
try:
    post = await Post.objects.get(Post.id == 1)
    author = await post.author.fetch()
except DoesNotExist:
    # Handle case where author was deleted
    author = None

# Check for null relationships
user = await User.objects.get(User.id == 1)
profile = await user.profile.fetch()  # May be None for one-to-one relationships
if profile:
    bio = profile.bio
```
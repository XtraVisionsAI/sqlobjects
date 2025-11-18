# Relationships Guide

## Core Concepts

- **relationship()**: Unified relationship definition for all relationship types
- **select_related**: JOIN-based loading for foreign keys (single query)
- **prefetch_related**: Separate query loading for reverse relationships (N+1 prevention)
- **Lazy Loading**: Load relationships on demand
- **Cascade Operations**: Automatic save/delete of related objects

## Common Usage

### Defining Relationships

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, foreign_key, relationship, Related

# One-to-Many (Foreign Key)
class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    author_id: Column[int] = foreign_key("users.id")
    author: Related["User"] = relationship("User", back_populates="posts")

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    posts: Related[list["Post"]] = relationship("Post", back_populates="author")

# One-to-One
class UserProfile(ObjectModel):
    user_id: Column[int] = foreign_key("users.id", unique=True)
    user: Related["User"] = relationship("User", back_populates="profile")

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    profile: Related["UserProfile"] = relationship("UserProfile", back_populates="user")

# Many-to-Many
class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    tags: Related[list["Tag"]] = relationship("Tag", secondary="post_tags")

class Tag(ObjectModel):
    name: Column[str] = StringColumn(length=50)
    posts: Related[list["Post"]] = relationship("Post", secondary="post_tags")
```

### Loading Strategies

```python
# select_related (JOIN) - for foreign keys
posts = await Post.objects.select_related("author").all()
for post in posts:
    print(post.author.username)  # No additional query

# prefetch_related (separate query) - for reverse relationships
users = await User.objects.prefetch_related("posts").all()
for user in users:
    posts = await user.posts.fetch()  # No N+1 queries

# Combined loading
posts = await Post.objects.select_related("author").prefetch_related("comments").all()

# Nested relationships
comments = await Comment.objects.select_related("post__author").all()
```

### Advanced prefetch_related

```python
# Custom QuerySet for filtering and ordering
users = await User.objects.prefetch_related(
    published_posts=Post.objects.filter(Post.is_published == True)
                               .order_by('-created_at')
                               .limit(5)
).all()

# Access prefetched data
for user in users:
    recent_posts = await user.published_posts.fetch()

# Multiple advanced prefetch configurations
users = await User.objects.prefetch_related(
    active_posts=Post.objects.filter(Post.status == "active"),
    draft_posts=Post.objects.filter(Post.status == "draft"),
    recent_comments=Comment.objects.order_by('-created_at').limit(10)
).all()
```

### Accessing Relationships

```python
# Lazy loading (loads on access)
post = await Post.objects.get(Post.id == 1)
author = await post.author.fetch()  # Loads author

# Prefetched data (no additional query)
posts = await Post.objects.select_related("author").all()
for post in posts:
    author = post.author  # Already loaded

# Reverse relationships
user = await User.objects.get(User.id == 1)
posts = await user.posts.fetch()  # Loads all posts
```

## Best Practices

### ✅ Do

- **Use select_related** for foreign keys and one-to-one
- **Use prefetch_related** for reverse relationships and many-to-many
- **Combine loading strategies** for complex queries
- **Use field expressions** in select_related/prefetch_related
- **Filter prefetched data** with custom QuerySets

```python
# Good: select_related for foreign keys
posts = await Post.objects.select_related("author", "category").all()

# Good: prefetch_related for reverse relationships
users = await User.objects.prefetch_related("posts", "comments").all()

# Good: Combined strategies
posts = await Post.objects.select_related("author").prefetch_related("tags").all()

# Good: Using field expressions
posts = await Post.objects.select_related(Post.author).all()

# Good: Filtered prefetch
users = await User.objects.prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=7)
    ).order_by('-created_at')
).all()
```

### ❌ Don't

- **Don't use select_related** for reverse relationships (use prefetch_related)
- **Don't forget to fetch()** lazy-loaded relationships
- **Don't cause N+1 queries** by not using loading strategies
- **Don't mix loading strategies** incorrectly

```python
# Bad: N+1 query problem
posts = await Post.objects.all()
for post in posts:
    author = await post.author.fetch()  # N additional queries!

# Good: Use select_related
posts = await Post.objects.select_related("author").all()
for post in posts:
    author = post.author  # No additional query

# Bad: select_related for reverse relationship
users = await User.objects.select_related("posts").all()  # Wrong!

# Good: prefetch_related for reverse relationship
users = await User.objects.prefetch_related("posts").all()
```

## Relationship Patterns

### One-to-Many

```python
class Author(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    books: Related[list["Book"]] = relationship("Book", back_populates="author")

class Book(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    author_id: Column[int] = foreign_key("authors.id")
    author: Related["Author"] = relationship("Author", back_populates="books")

# Usage
author = await Author.objects.prefetch_related("books").get(Author.id == 1)
books = await author.books.fetch()
```

### One-to-One

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    profile: Related["Profile"] = relationship("Profile", back_populates="user")

class Profile(ObjectModel):
    user_id: Column[int] = foreign_key("users.id", unique=True)
    bio: Column[str] = column(type="text")
    user: Related["User"] = relationship("User", back_populates="profile")

# Usage
user = await User.objects.select_related("profile").get(User.id == 1)
bio = user.profile.bio  # No additional query
```

### Many-to-Many

```python
class Student(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    courses: Related[list["Course"]] = relationship("Course", secondary="enrollments")

class Course(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    students: Related[list["Student"]] = relationship("Student", secondary="enrollments")

# Usage
student = await Student.objects.prefetch_related("courses").get(Student.id == 1)
courses = await student.courses.fetch()
```

### Self-Referential

```python
class Category(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    parent_id: Column[int] = foreign_key("categories.id", nullable=True)
    parent: Related["Category"] = relationship("Category", back_populates="children")
    children: Related[list["Category"]] = relationship("Category", back_populates="parent")

# Usage
category = await Category.objects.select_related("parent").prefetch_related("children").get(Category.id == 1)
```

## Performance Tips

### N+1 Query Prevention

```python
# Bad: N+1 queries (1 + N queries)
posts = await Post.objects.all()  # 1 query
for post in posts:
    author = await post.author.fetch()  # N queries

# Good: Single JOIN query
posts = await Post.objects.select_related("author").all()  # 1 query
for post in posts:
    author = post.author  # No additional query
```

### Relationship Query Optimization

```python
# Optimize with field selection
users = await User.objects.select_related("department").only(
    "id", "username", "department__name"
).all()

# Defer heavy fields in relationships
posts = await Post.objects.select_related("author").defer(
    "content",           # Heavy field from main model
    "author__bio"        # Heavy field from related model
).all()

# Filter prefetched relationships
users = await User.objects.prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=7)
    ).order_by('-created_at').limit(10)
).all()
```

### Bulk Relationship Operations

```python
# Bulk create with relationships
posts_data = [
    {"title": "Post 1", "author_id": 1, "category_id": 1},
    {"title": "Post 2", "author_id": 1, "category_id": 2},
]
await Post.objects.bulk_create(posts_data, batch_size=1000)

# Bulk many-to-many associations
associations = [
    {"post_id": 1, "tag_id": 1},
    {"post_id": 1, "tag_id": 2},
]
await PostTag.objects.bulk_create(associations, batch_size=1000)
```

## Troubleshooting

### N+1 Query Problem

**Problem**: Too many database queries

**Solution**:
```python
# Use select_related for foreign keys
posts = await Post.objects.select_related("author").all()

# Use prefetch_related for reverse relationships
users = await User.objects.prefetch_related("posts").all()
```

### Relationship Not Loaded

**Problem**: `AttributeError` when accessing relationship

**Solution**:
```python
# Use fetch() for lazy-loaded relationships
post = await Post.objects.get(Post.id == 1)
author = await post.author.fetch()  # Explicit load

# Or use select_related
post = await Post.objects.select_related("author").get(Post.id == 1)
author = post.author  # Already loaded
```

### Wrong Loading Strategy

**Problem**: select_related doesn't work for reverse relationships

**Solution**:
```python
# Use prefetch_related for reverse relationships
users = await User.objects.prefetch_related("posts").all()  # Correct

# Not: users = await User.objects.select_related("posts").all()  # Wrong!
```

### Circular Import

**Problem**: `NameError: name 'Model' is not defined`

**Solution**:
```python
# Use string references for forward declarations
class Post(ObjectModel):
    author: Related["User"] = relationship("User", back_populates="posts")

# Or use TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .user import User

class Post(ObjectModel):
    author: Related[User] = relationship("User", back_populates="posts")
```

## Complete Example

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, foreign_key, relationship, Related
from datetime import datetime, timedelta

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    posts: Related[list["Post"]] = relationship("Post", back_populates="author")
    comments: Related[list["Comment"]] = relationship("Comment", back_populates="author")

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    content: Column[str] = column(type="text")
    author_id: Column[int] = foreign_key("users.id")
    author: Related["User"] = relationship("User", back_populates="posts")
    comments: Related[list["Comment"]] = relationship("Comment", back_populates="post")
    tags: Related[list["Tag"]] = relationship("Tag", secondary="post_tags")

class Comment(ObjectModel):
    content: Column[str] = column(type="text")
    post_id: Column[int] = foreign_key("posts.id")
    author_id: Column[int] = foreign_key("users.id")
    post: Related["Post"] = relationship("Post", back_populates="comments")
    author: Related["User"] = relationship("User", back_populates="comments")

class Tag(ObjectModel):
    name: Column[str] = StringColumn(length=50)
    posts: Related[list["Post"]] = relationship("Post", secondary="post_tags")

# Usage
# Prevent N+1 queries with select_related
posts = await Post.objects.select_related("author").all()

# Prefetch reverse relationships
users = await User.objects.prefetch_related("posts", "comments").all()

# Combined loading strategies
posts = await Post.objects.select_related("author").prefetch_related("comments", "tags").all()

# Advanced prefetch with filtering
users = await User.objects.prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=7)
    ).order_by('-created_at').limit(5)
).all()

for user in users:
    recent_posts = await user.recent_posts.fetch()
```

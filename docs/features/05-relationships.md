# Relationships

> 📝 This document is based on the Chinese version. For the latest Chinese version, see [docs-zh/features/05-relationships.md](../../docs-zh/features/05-relationships.md)

SQLObjects provides comprehensive relationship support with optimized loading strategies, intuitive APIs, and high-performance relationship operations.

## Relationship Types

### One-to-Many (Foreign Key)

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
    # Reverse relationship
    posts = relationship("Post", back_populates="author")

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    author_id: Column[int] = foreign_key("users.id")
    
    # Forward relationship
    author = relationship("User", back_populates="posts")
```

### One-to-One

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
    # One-to-one relationship
    profile = relationship("Profile", back_populates="user", uselist=False)

class Profile(ObjectModel):
    user_id: Column[int] = foreign_key("users.id", unique=True)
    bio: Column[str] = StringColumn(type="text")
    
    # Back reference
    user = relationship("User", back_populates="profile")
```

### Many-to-Many

```python
# Association table
class PostTag(ObjectModel):
    post_id: Column[int] = foreign_key("posts.id", primary_key=True)
    tag_id: Column[int] = foreign_key("tags.id", primary_key=True)

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    
    # Many-to-many relationship
    tags = relationship("Tag", secondary="post_tags", back_populates="posts")

class Tag(ObjectModel):
    name: Column[str] = StringColumn(length=50, unique=True)
    
    # Back reference
    posts = relationship("Post", secondary="post_tags", back_populates="tags")
```

## Relationship Loading

### select_related (JOIN Strategy)

Use for foreign key and one-to-one relationships:

```python
# Single relationship - both syntaxes supported
posts = await Post.objects.select_related("author").all()        # String syntax
posts = await Post.objects.select_related(Post.author).all()     # Expression syntax

# Multiple relationships
posts = await Post.objects.select_related("author", "category").all()
posts = await Post.objects.select_related(Post.author, Post.category).all()

# Nested relationships
comments = await Comment.objects.select_related("post__author").all()

# Access without additional queries
for post in posts:
    print(post.author.username)  # No additional query
```

### prefetch_related (Separate Query Strategy)

Use for reverse foreign key and many-to-many relationships:

```python
# Reverse foreign key relationships - both syntaxes supported
users = await User.objects.prefetch_related("posts").all()       # String syntax
users = await User.objects.prefetch_related(User.posts).all()    # Expression syntax

# Many-to-many relationships
posts = await Post.objects.prefetch_related("tags").all()
posts = await Post.objects.prefetch_related(Post.tags).all()

# Multiple prefetch relationships
users = await User.objects.prefetch_related("posts", "comments", "groups").all()

# Access prefetched data
for user in users:
    posts = await user.posts.all()  # Uses prefetched data
    for post in posts:
        tags = await post.tags.all()  # Additional query if not prefetched
```

### Combined Loading Strategies

```python
# Optimize complex relationship queries
posts = await Post.objects.select_related("author").prefetch_related("tags", "comments").all()

for post in posts:
    # From JOIN (select_related)
    author = post.author
    print(f"Author: {author.username}")
    
    # From prefetch (prefetch_related)
    tags = await post.tags.all()
    comments = await post.comments.all()
```

## Relationship Queries

### Filtering by Related Fields

```python
# Filter by foreign key relationship
posts = await Post.objects.filter(Post.author.username == "alice").all()

# Filter by reverse relationship
users = await User.objects.filter(User.posts.title.like("%python%")).all()

# Multiple relationship levels
comments = await Comment.objects.filter(
    Comment.post.author.username == "alice"
).all()

# Complex relationship filtering
active_authors = await User.objects.filter(
    User.posts.created_at > datetime.now() - timedelta(days=30),
    User.posts.is_published == True
).distinct().all()
```

### Relationship Aggregation

```python
from sqlobjects.expressions import func

# Count related objects
users = await User.objects.annotate(
    post_count=func.count(User.posts)
).all()

# Aggregate related data
users = await User.objects.annotate(
    post_count=func.count(User.posts),
    latest_post=func.max(User.posts.created_at),
    avg_post_length=func.avg(func.length(User.posts.content))
).all()

# Filter by aggregated relationship data
prolific_authors = await User.objects.annotate(
    post_count=func.count(User.posts)
).filter(User.post_count > 10).all()
```

### Relationship Existence

```python
# Users who have posts
authors = await User.objects.filter(User.posts.exists()).all()

# Users who don't have posts
non_authors = await User.objects.filter(~User.posts.exists()).all()

# Complex existence queries
recent_authors = await User.objects.filter(
    User.posts.filter(
        Post.created_at > datetime.now() - timedelta(days=7)
    ).exists()
).all()
```

## Relationship Operations

### Creating Related Objects

```python
# Create with foreign key
user = await User.objects.create(username="alice")
post = await Post.objects.create(
    title="My First Post",
    author_id=user.id  # Set foreign key
)

# Create through relationship
user = await User.objects.create(username="bob")
post = await user.posts.create(title="Bob's Post")  # Automatic foreign key setting
```

### Managing Many-to-Many Relationships

```python
# Create objects
post = await Post.objects.create(title="Python Tutorial")
tag1 = await Tag.objects.create(name="python")
tag2 = await Tag.objects.create(name="tutorial")

# Add relationships
await post.tags.add(tag1, tag2)

# Remove relationships
await post.tags.remove(tag1)

# Set relationships (replace all)
await post.tags.set([tag2])

# Clear all relationships
await post.tags.clear()

# Check relationship existence
has_python_tag = await post.tags.filter(Tag.name == "python").exists()
```

### Bulk Relationship Operations

```python
# Bulk create with relationships
posts_data = [
    {"title": "Post 1", "author_id": 1},
    {"title": "Post 2", "author_id": 1},
    {"title": "Post 3", "author_id": 2},
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

## Advanced Relationship Features

### Custom Relationship Managers

```python
class PublishedPostManager:
    def get_queryset(self):
        return super().get_queryset().filter(is_published=True)

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
    # All posts
    posts = relationship("Post", back_populates="author")
    
    # Only published posts
    published_posts = relationship(
        "Post", 
        back_populates="author",
        primaryjoin="and_(User.id == Post.author_id, Post.is_published == True)"
    )
```

### Relationship Ordering

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
    # Posts ordered by creation date (newest first)
    posts = relationship(
        "Post", 
        back_populates="author",
        order_by="Post.created_at.desc()"
    )
    
    # Recent posts only
    recent_posts = relationship(
        "Post",
        back_populates="author",
        primaryjoin="and_(User.id == Post.author_id, Post.created_at > func.now() - interval('30 days'))"
    )
```

### Lazy Loading Control

```python
class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    author_id: Column[int] = foreign_key("users.id")
    
    # Different loading strategies
    author = relationship("User", lazy="select")      # Load on access
    category = relationship("Category", lazy="joined") # Always JOIN
    tags = relationship("Tag", lazy="subquery")       # Use subquery
    comments = relationship("Comment", lazy="dynamic") # Return query object
```

## Performance Optimization

### N+1 Query Prevention

```python
# ❌ N+1 query problem
posts = await Post.objects.all()
for post in posts:
    author = await post.author  # N additional queries!

# ✅ Use select_related for foreign keys
posts = await Post.objects.select_related("author").all()
for post in posts:
    author = post.author  # No additional query

# ✅ Use prefetch_related for reverse relationships
users = await User.objects.prefetch_related("posts").all()
for user in users:
    posts = await user.posts.all()  # No additional queries
```

### Relationship Loading Optimization

```python
# Optimize complex relationship loading
posts = await Post.objects.select_related(
    "author",      # Foreign key - use JOIN
    "category"     # Foreign key - use JOIN
).prefetch_related(
    "tags",        # Many-to-many - separate query
    "comments"     # Reverse FK - separate query
).all()

# Access all relationships efficiently
for post in posts:
    print(f"Post: {post.title}")
    print(f"Author: {post.author.username}")      # From JOIN
    print(f"Category: {post.category.name}")      # From JOIN
    
    tags = await post.tags.all()                  # From prefetch
    comments = await post.comments.all()          # From prefetch
```

### Relationship Caching

```python
# Optimize relationship queries
users = await User.objects.prefetch_related("posts").all()

# Load relationships with filtering
live_posts = await Post.objects.select_related("author").filter(
    Post.created_at > datetime.now() - timedelta(minutes=5)
).all()
```

## Relationship Validation

### Foreign Key Validation

```python
class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    author_id: Column[int] = foreign_key("users.id")
    
    def validate(self):
        # Validate foreign key exists
        if self.author_id:
            author_exists = await User.objects.filter(
                User.id == self.author_id
            ).exists()
            if not author_exists:
                raise ValidationError("Invalid author ID")
```

### Relationship Constraints

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    
    async def before_delete(self, context):
        # Prevent deletion if user has posts
        post_count = await self.posts.count()
        if post_count > 0:
            raise ValidationError("Cannot delete user with existing posts")
```

## Testing Relationships

### Relationship Testing Patterns

```python
import pytest

class TestUserPostRelationship:
    async def test_user_can_have_multiple_posts(self, test_session):
        # Create user
        user = await User.objects.using(test_session).create(username="testuser")
        
        # Create posts
        post1 = await Post.objects.using(test_session).create(
            title="Post 1", author_id=user.id
        )
        post2 = await Post.objects.using(test_session).create(
            title="Post 2", author_id=user.id
        )
        
        # Test relationship
        posts = await user.posts.using(test_session).all()
        assert len(posts) == 2
        assert post1 in posts
        assert post2 in posts
    
    async def test_select_related_prevents_n_plus_one(self, test_session):
        # Create test data
        users = await User.objects.using(test_session).bulk_create([
            {"username": f"user{i}"} for i in range(10)
        ])
        
        posts = await Post.objects.using(test_session).bulk_create([
            {"title": f"Post {i}", "author_id": users[i % len(users)].id}
            for i in range(100)
        ])
        
        # Test select_related prevents N+1 queries
        with query_counter() as counter:
            posts = await Post.objects.using(test_session).select_related("author").all()
            for post in posts:
                _ = post.author.username  # Should not trigger additional queries
        
        # Should use only 1 query (JOIN), not N+1 queries
        assert counter.count == 1
```

## Best Practices

### Relationship Design

1. **Use appropriate relationship types**: Choose the right relationship for your data model
2. **Define back_populates**: Always define bidirectional relationships
3. **Use meaningful names**: Choose clear, descriptive relationship names
4. **Consider cascade behavior**: Define appropriate cascade rules for deletions

### Performance Guidelines

```python
# ✅ Good: Use select_related for foreign keys
posts = await Post.objects.select_related("author", "category").all()

# ✅ Good: Use prefetch_related for reverse relationships
users = await User.objects.prefetch_related("posts", "comments").all()

# ✅ Good: Combine strategies for optimal loading
posts = await Post.objects.select_related("author").prefetch_related("tags").all()

# ❌ Bad: Don't load relationships you don't need
posts = await Post.objects.select_related("author", "category", "editor").all()
# Only load what you actually use

# ✅ Good: Use exists() for existence checks
has_posts = await User.objects.filter(User.posts.exists()).exists()

# ❌ Bad: Don't count for existence checks
has_posts = await user.posts.count() > 0  # Less efficient
```

### Relationship Maintenance

```python
# ✅ Good: Clean up relationships on deletion
class User(ObjectModel):
    async def before_delete(self, context):
        # Handle related data appropriately
        await self.posts.update(author_id=None)  # Nullify foreign keys
        await self.profile.delete()              # Delete dependent data

# ✅ Good: Use transactions for relationship operations
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="alice")
    profile = await Profile.objects.using(session).create(
        user_id=user.id, bio="Alice's profile"
    )
    # Both operations committed together
```
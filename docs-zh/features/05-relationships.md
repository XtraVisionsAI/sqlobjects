# 关系和连接

## 概述

SQLObjects 提供了全面的关系支持，包括自动 JOIN 优化、延迟和急切加载策略，以及直观的关系遍历语法。

## 快速开始

### 基础关系

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, TextColumn, foreign_key
from sqlobjects.relations import relationship

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    content: Column[str] = TextColumn()
    author_id: Column[int] = foreign_key("users.id")  # 外键约束
  
    # 使用统一的 relationship() 函数定义关系
    author = relationship("User", foreign_keys="author_id")

# 向 User 添加反向关系
User.posts = relationship("Post", foreign_keys="Post.author_id")
```

### 使用关系

```python
# 访问相关对象
post = await Post.objects.get(Post.id == 1)
author = await post.author  # 延迟加载

# 反向关系
user = await User.objects.get(User.id == 1)
user_posts = await user.posts.all()  # 反向关系的查询集
```

## 关系类型

### 一对多（外键）

```python
class Department(ObjectModel):
    name: Column[str] = StringColumn(length=100)

class Employee(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    department_id: Column[int] = foreign_key("departments.id")  # 创建外键约束
  
    # 多对一关系
    department = relationship("Department", foreign_keys="department_id")

# 向 Department 添加反向关系
Department.employees = relationship("Employee", foreign_keys="Employee.department_id")

# 用法
employee = await Employee.objects.get(Employee.id == 1)
dept = await employee.department  # 单个对象

department = await Department.objects.get(Department.id == 1)
employees = await department.employees.all()  # 对象列表
```

### 一对一

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)

class Profile(ObjectModel):
    bio: Column[str] = TextColumn()
    user_id: Column[int] = foreign_key("users.id", unique=True)  # 唯一约束
  
    # 一对一关系
    user = relationship("User", foreign_keys="user_id")

# 向 User 添加反向一对一关系
User.profile = relationship("Profile", foreign_keys="Profile.user_id", unique=True)

# 用法
profile = await Profile.objects.get(Profile.id == 1)
user = await profile.user  # 单个对象

user = await User.objects.get(User.id == 1)
profile = await user.profile  # 单个对象（或 None）
```

### 多对多

```python
class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)

class Tag(ObjectModel):
    name: Column[str] = StringColumn(length=50)

# 关联表（自动创建）
class PostTag(ObjectModel):
    post_id: Column[int] = foreign_key("posts.id", primary_key=True)
    tag_id: Column[int] = foreign_key("tags.id", primary_key=True)

# 使用 through 参数添加多对多关系
Post.tags = relationship("Tag", through="PostTag")
Tag.posts = relationship("Post", through="PostTag")

# 用法
post = await Post.objects.get(Post.id == 1)
tags = await post.tags.all()  # 标签列表

tag = await Tag.objects.get(Tag.id == 1)
posts = await tag.posts.all()  # 文章列表
```

## 加载策略

### 延迟加载（默认）

```python
# 延迟加载 - 访问时查询数据库
post = await Post.objects.get(Post.id == 1)
author = await post.author  # 在此处执行单独查询

# N+1 查询问题示例
posts = await Post.objects.all()
for post in posts:
    author = await post.author  # 执行 N 次额外查询！
```

### 使用 select_related 的急切加载

```python
# 对外键关系使用 select_related（JOIN）
posts = await Post.objects.select_related("author").all()
for post in posts:
    author = post.author  # 无额外查询 - 已经加载

# 多个关系
posts = await Post.objects.select_related("author", "category").all()

# 嵌套关系
comments = await Comment.objects.select_related("post__author").all()

# 字符串路径语法（Django 风格）
posts = await Post.objects.select_related("author").all()
```

### 使用 prefetch_related 的急切加载

```python
# 对反向外键和多对多关系使用 prefetch_related
users = await User.objects.prefetch_related("posts").all()
for user in users:
    posts = await user.posts.all()  # 无额外查询

# 多对多关系
posts = await Post.objects.prefetch_related("tags").all()
for post in posts:
    tags = await post.tags.all()  # 无额外查询

# 多个预取
users = await User.objects.prefetch_related("posts", "groups", "permissions").all()

# 字符串路径语法（Django 风格）
users = await User.objects.prefetch_related("posts").all()
```

### 高级预取配置

```python
# 带有过滤和排序的高级预取
users = await User.objects.prefetch_related(
    published_posts=Post.objects.filter(Post.is_published == True)
                               .order_by('-created_at')
                               .limit(5)
).all()

# 多个高级配置
users = await User.objects.prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=30)
    ).order_by('-created_at'),
    popular_posts=Post.objects.filter(Post.view_count > 1000)
                             .order_by('-view_count')
                             .limit(3)
).all()

# 混合简单和高级预取
users = await User.objects.prefetch_related(
    'profile',  # 简单预取
    recent_comments=Comment.objects.filter(
        Comment.created_at >= datetime.now() - timedelta(days=7)
    ).order_by('-created_at')
).all()

# 访问预取的数据
for user in users:
    # 高级预取结果可直接访问
    recent_posts = user.recent_posts  # 过滤/排序后的文章列表
    popular_posts = user.popular_posts  # 热门文章列表
```

### 组合加载策略

```python
# 组合 select_related 和 prefetch_related
posts = await Post.objects.select_related("author").prefetch_related("tags", "comments").all()

for post in posts:
    author = post.author  # 来自 JOIN (select_related)
    tags = await post.tags.all()  # 来自预取 (prefetch_related)
    comments = await post.comments.all()  # 来自预取
```

## 高级关系查询

### 按相关字段过滤

```python
# 按外键字段过滤
posts = await Post.objects.filter(Post.author.username == "john").all()

# 按反向关系过滤
users = await User.objects.filter(User.posts.title.like("%python%")).all()

# 多个关系过滤器
posts = await Post.objects.filter(
    Post.author.is_active == True,
    Post.category.name == "Technology"
).all()
```

### 关系的注解

```python
from sqlobjects.expressions import func

# 计算相关对象
users = await User.objects.annotate(
    post_count=func.count(User.posts)
).all()

# 聚合相关字段
users = await User.objects.annotate(
    latest_post=func.max(User.posts.created_at),
    avg_post_length=func.avg(func.length(User.posts.content))
).all()

# 按聚合值过滤
active_authors = await User.objects.annotate(
    post_count=func.count(User.posts)
).filter(
    User.post_count > 5
).all()
```

### 关系的子查询

```python
# 存在子查询
has_posts = Post.objects.filter(Post.author_id == User.id).subquery(query_type="exists")
authors = await User.objects.filter(has_posts).all()

# 标量子查询
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

## 手动连接

### 显式 JOIN 操作

```python
# 内连接
posts_with_authors = await Post.objects.join(
    User, Post.author_id == User.id
).all()

# 左连接
all_posts = await Post.objects.leftjoin(
    User, Post.author_id == User.id
).all()

# 多个连接
posts_with_details = await Post.objects.join(
    User, Post.author_id == User.id
).join(
    Category, Post.category_id == Category.id
).all()
```

### 子查询的 JOIN

```python
# 与子查询连接
active_users = User.objects.filter(User.is_active == True).subquery("active_users")
posts = await Post.objects.join(
    active_users, 
    Post.author_id == active_users.c.id
).all()
```

## 关系管理

### 添加相关对象

```python
# 创建相关对象
user = await User.objects.create(username="author")
post = await Post.objects.create(
    title="My Post",
    author_id=user.id  # 设置外键
)

# 多对多关系
post = await Post.objects.get(Post.id == 1)
tag = await Tag.objects.get(Tag.id == 1)

# 添加到多对多（需要手动管理关联表）
await PostTag.objects.create(post_id=post.id, tag_id=tag.id)
```

### 批量关系操作

```python
# 带关系的批量创建
posts_data = [
    {"title": "Post 1", "author_id": 1, "category_id": 1},
    {"title": "Post 2", "author_id": 1, "category_id": 2},
    {"title": "Post 3", "author_id": 2, "category_id": 1},
]
posts = await Post.objects.bulk_create(posts_data)

# 批量多对多关联
associations = [
    {"post_id": 1, "tag_id": 1},
    {"post_id": 1, "tag_id": 2},
    {"post_id": 2, "tag_id": 1},
]
await PostTag.objects.bulk_create(associations)
```

## 性能优化

### 关系加载最佳实践

```python
# 好的做法：对外键使用 select_related
posts = await Post.objects.select_related("author", "category").all()

# 好的做法：对反向关系使用 prefetch_related
users = await User.objects.prefetch_related("posts", "comments").all()

# 避免：N+1 查询
posts = await Post.objects.all()
for post in posts:
    author = await post.author  # N 次额外查询！

# 好的做法：组合加载策略
posts = await Post.objects.select_related("author").prefetch_related("tags").all()
```

### 选择性字段加载

```python
# 只从相关对象加载需要的字段
posts = await Post.objects.select_related("author").only(
    "title", "content", "author__username", "author__email"
).all()

# 延迟相关对象的重字段
posts = await Post.objects.select_related("author").defer(
    "content", "author__bio"
).all()
```

### 关系计数

```python
# 高效计数不加载对象
user_count = await User.objects.filter(User.posts__isnull=False).distinct().count()

# 带注解的计数
users_with_counts = await User.objects.annotate(
    post_count=func.count(User.posts),
    comment_count=func.count(User.comments)
).all()
```

## 复杂关系模式

### 自引用关系

```python
class Category(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    parent_id: Column[int] = foreign_key("categories.id", nullable=True)
  
    # 自引用关系
    parent: Column["Category"] = relationship("Category", remote_side="id", back_populates="children")
    children: Column[list["Category"]] = relationship("Category", back_populates="parent")

# 用法
category = await Category.objects.get(Category.id == 1)
parent = await category.parent
children = await category.children.all()
```

### 多态关系

```python
class Content(ObjectModel):
    title: Column[str] = StringColumn(length=200)
    content_type: Column[str] = StringColumn(length=50)

class Article(Content):
    body: Column[str] = TextColumn()

class Video(Content):
    duration: Column[int] = IntegerColumn()
    video_url: Column[str] = StringColumn(length=500)

# 查询多态关系
contents = await Content.objects.filter(Content.content_type == "article").all()
```

### 通过模型的关系

```python
class Membership(ObjectModel):
    user_id: Column[int] = foreign_key("users.id", primary_key=True)
    group_id: Column[int] = foreign_key("groups.id", primary_key=True)
    role: Column[str] = StringColumn(length=50, default="member")
    joined_at: Column[datetime] = DateTimeColumn(default_factory=datetime.now)

class User(ObjectModel):
    groups: Column[list["Group"]] = relationship(
        "Group",
        secondary="memberships",
        back_populates="users"
    )

class Group(ObjectModel):
    users: Column[list["User"]] = relationship(
        "User",
        secondary="memberships", 
        back_populates="groups"
    )

# 访问通过模型的数据
memberships = await Membership.objects.filter(
    Membership.user_id == 1,
    Membership.role == "admin"
).all()
```

## 最佳实践

### 关系设计

```python
# 使用描述性的关系名称
class Order(ObjectModel):
    customer_id: Column[int] = foreign_key("users.id")
    customer: Column["User"] = relationship("User", back_populates="orders")

class User(ObjectModel):
    orders: Column[list["Order"]] = relationship("Order", back_populates="customer")
```

### 加载策略选择

```python
# 在以下情况使用 select_related：
# - 外键关系（多对一）
# - 一对一关系
posts = await Post.objects.select_related("author", "category").all()

# 在以下情况使用 prefetch_related：
# - 反向外键关系（一对多）
# - 多对多关系
users = await User.objects.prefetch_related("posts", "groups").all()
```

### 错误处理

```python
from sqlobjects.exceptions import DoesNotExist

# 处理缺失的相关对象
try:
    post = await Post.objects.get(Post.id == 1)
    author = await post.author
except DoesNotExist:
    # 处理作者被删除的情况
    author = None

# 检查空关系
user = await User.objects.get(User.id == 1)
profile = await user.profile  # 对于一对一关系可能为 None
if profile:
    bio = profile.bio
```
# 关系和连接

## 概述

SQLObjects 提供全面的关系支持，包括自动 JOIN 优化、延迟和预加载策略以及直观的关系遍历语法。

## 快速开始

### 基本关系

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
    # 也可使用简写 foreign_key() 函数，支持类名引用：
    # author_id: Column[int] = foreign_key("User.id")    # 类名（自动解析）
    # author_id: Column[int] = foreign_key("users.id")   # 表名（同样可用）

    # 使用统一的 relationship() 函数定义关系
    author: Related[User] = relationship("User", foreign_keys="author_id")

# 向 User 添加反向关系
User.posts: Related[list[Post]] = relationship("Post", foreign_keys="Post.author_id")
```

### 使用关系

```python
# 访问关联对象
post = await Post.objects.get(Post.id == 1)
author = await post.author.fetch()  # 通过 RelatedObject 代理延迟加载

# 反向关系
user = await User.objects.get(User.id == 1)
user_posts = await user.posts.fetch()  # 通过 RelatedCollection 代理获取

# 统一写法：无论是否已预加载都可用
author = await post.load_relation("author")
user_posts = await user.load_relation("posts")
```

未预加载时，关系属性是代理对象，可以 `await proxy.fetch()`。经 `prefetch_related()`
预加载后，关系属性直接是实体对象列表（单值关系为实体对象），不再是代理；经
`select_related()` 加载后，属性是实体对象，不能再对它调用 `.fetch()`。因此推荐统一使用
`await obj.load_relation("name")`：它对代理执行查询，对已加载的值直接返回。

## 关系类型

### 一对多（外键）

```python
class Department(ObjectModel):
    name: Column[str] = StringColumn(length=100)

class Employee(ObjectModel):
    name: Column[str] = StringColumn(length=100)
    department_id: Column[int] = column(type="integer", foreign_key=ForeignKey("departments.id"))

    # 多对一关系
    department: Related[Department] = relationship("Department", foreign_keys="department_id")

# 向 Department 添加反向关系
Department.employees: Related[list[Employee]] = relationship("Employee", foreign_keys="Employee.department_id")

# 使用
employee = await Employee.objects.get(Employee.id == 1)
dept = await employee.department.fetch()  # 通过 RelatedObject 获取单个对象

department = await Department.objects.get(Department.id == 1)
employees = await department.employees.fetch()  # 通过 RelatedCollection 获取列表
```

### 一对一

```python
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)

class Profile(ObjectModel):
    bio: Column[str] = TextColumn()
    user_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"), unique=True)

    # 一对一关系
    user: Related[User] = relationship("User", foreign_keys="user_id")

# 向 User 添加反向一对一关系
User.profile: Related[Profile] = relationship("Profile", foreign_keys="Profile.user_id", uselist=False)

# 使用
profile = await Profile.objects.get(Profile.id == 1)
user = await profile.user.fetch()  # 通过 RelatedObject 获取单个对象

user = await User.objects.get(User.id == 1)
profile = await user.profile.fetch()  # 通过 RelatedObject 获取单个对象（或 None）
```

### 多对多

```python
class Post(ObjectModel):
    title: Column[str] = StringColumn(length=200)

class Tag(ObjectModel):
    name: Column[str] = StringColumn(length=50)

# 关联表
class PostTag(ObjectModel):
    post_id: Column[int] = column(type="integer", foreign_key=ForeignKey("posts.id"), primary_key=True)
    tag_id: Column[int] = column(type="integer", foreign_key=ForeignKey("tags.id"), primary_key=True)

# 使用 secondary 参数添加多对多关系
Post.tags: Related[list[Tag]] = relationship("Tag", secondary="post_tags")
Tag.posts: Related[list[Post]] = relationship("Post", secondary="post_tags")

# 使用
post = await Post.objects.get(Post.id == 1)
tags = await post.tags.fetch()  # 通过 ManyToManyRelation 获取标签列表

tag = await Tag.objects.get(Tag.id == 1)
posts = await tag.posts.fetch()  # 通过 ManyToManyRelation 获取帖子列表
```

## 加载策略

### 延迟加载（默认）

```python
# 延迟加载 - 访问时查询数据库
post = await Post.objects.get(Post.id == 1)
author = await post.author.fetch()  # 在此处执行单独查询

# N+1 查询问题示例
posts = await Post.objects.all()
for post in posts:
    author = await post.author.fetch()  # 执行 N 个额外查询！
```

### 动态集合查询

一对多、多对多关系可设置 `lazy="dynamic"`，按需构建带父对象条件的 QuerySet。
访问属性和构造查询都不会执行 SQL。

```python
from sqlobjects.fields import Column, RelatedQuerySet, foreign_key, identity, relationship

class User(ObjectModel):
    id: Column[int] = identity()
    posts: RelatedQuerySet["Post"] = relationship(
        "Post", remote_fields="author_id", lazy="dynamic", order_by="-id"
    )

class Post(ObjectModel):
    id: Column[int] = identity()
    author_id: Column[int] = foreign_key("users.id")

user = await User.objects.get(id=1)
count = await user.posts.filter(Post.id > 100).count()
page = await user.posts.order_by("id")[:20].all()
ids = await user.posts.values_list("id", flat=True)

async for post in user.posts:
    print(post.id)

rows = await user.posts.fetch()  # 每次执行新查询，不缓存列表
```

动态关系支持普通异步 QuerySet 的筛选、排序、投影、分页、计数和流式读取。
关系的 `order_by` 作为初始排序，查询上的 `order_by()` 可以覆盖它。
对于 `lazy="dynamic"` 的关系，`fetch()` 和 `load_relation()` 返回新的列表，关系属性始终
保留为查询代理，不会缓存结果（其他加载策略下，预加载后的属性是实体对象列表）。
请显式使用 `await relation.count()` 和 `await relation.exists()`；同步迭代、
`len()`、`bool()` 会抛出 `TypeError`。

新建查询使用父对象当前的关联键及数据库别名或绑定 session；已经构造的 QuerySet
保留构造时的条件和绑定。可以通过 `.using(...)` 覆盖数据库，但关联条件仍然保留。
查询结果具有正常的持久化状态和数据库别名，可以继续保存。

反向外键使用真实引用列，支持复合外键及非主键引用。多对多使用已存在的中间表，
支持显式 `M2MTable` 列映射，重复关联不会造成目标对象重复返回。关联模型在父对象
所属的注册表中解析。

- 父对象必须具有完整主键，否则抛出 `PrimaryKeyError`；引用值为 `None` 时返回空查询。
- 延迟加载的关联键必须先用 `await parent.load_deferred_field("字段名")` 显式加载。
- 仅支持集合关系；单对象关系和自定义 `primaryjoin` / `secondaryjoin` 会明确报错。
- `select_related()`、`prefetch_related()` 不接受动态关系路径，包括嵌套路径和自定义
  预加载查询。需要预加载时请定义普通集合关系。
- `update()`、`delete()` 修改或删除关联的目标行，遵循普通事务和级联规则；多对多
  目标行的删除不等于解除中间表关联。该代理不提供 `add()`、`remove()`、`set()` 或
  manager 的创建方法。

自引用的子集合请同时指定 `remote_fields` 和 `uselist=True`。可空数字外键可以标注
`Column[int | None]`，自动推断会保留整数 SQL 类型。

### 使用 select_related 预加载

```python
# 对外键关系使用 select_related（JOIN）
posts = await Post.objects.select_related("author").all()
for post in posts:
    author = post.author  # 无额外查询 - 已加载

# 多个关系
posts = await Post.objects.select_related("author", "category").all()

# 嵌套关系
comments = await Comment.objects.select_related("post__author").all()

# 字符串路径语法（Django 风格）
posts = await Post.objects.select_related("author").all()
```

### 使用 prefetch_related 预加载

```python
# 对反向外键和多对多关系使用 prefetch_related
users = await User.objects.prefetch_related("posts").all()
for user in users:
    posts = await user.load_relation("posts")  # 无额外查询

# 多对多关系
posts = await Post.objects.prefetch_related("tags").all()
for post in posts:
    tags = await post.load_relation("tags")  # 无额外查询

# 多个预取
users = await User.objects.prefetch_related("posts", "groups", "permissions").all()

# 字符串路径语法（Django 风格）
users = await User.objects.prefetch_related("posts").all()
```

### 高级预取配置

配置项的 key 必须是模型上已声明的关系名。自定义查询集支持过滤和排序；不支持
按父对象的 LIMIT/OFFSET，也不支持任意输出别名。带切片的查询集会抛出错误，
而不是截断整个预取结果。

```python
# 带过滤和排序的高级预取
users = await User.objects.prefetch_related(
    posts=Post.objects.filter(Post.is_published == True).order_by('-created_at')
).all()

for user in users:
    published_posts = await user.load_relation("posts")  # 已缓存的过滤列表

# 混合简单和高级预取
users = await User.objects.prefetch_related(
    'profile',  # 简单预取
    posts=Post.objects.filter(
        Post.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
    ).order_by('-created_at')
).all()
```

### 组合加载策略

```python
# 组合 select_related 和 prefetch_related
posts = await Post.objects.select_related("author").prefetch_related("tags", "comments").all()

for post in posts:
    author = post.author  # 来自 JOIN（select_related）
    tags = await post.load_relation("tags")  # 来自预取（prefetch_related）
    comments = await post.load_relation("comments")  # 来自预取
```

## 高级关系查询

### 按关联字段过滤

```python
# 按外键字段过滤
posts = await Post.objects.filter(Post.author.username == "john").all()

# 按反向关系过滤
users = await User.objects.filter(User.posts.title.like("%python%")).all()

# 多个关系过滤
posts = await Post.objects.filter(
    Post.author.is_active == True,
    Post.category.name == "Technology"
).all()
```

### 关系上的注解

```python
from sqlobjects.expressions import func

# 计数关联对象
users = await User.objects.annotate(
    post_count=func.count(User.posts)
).all()

# 聚合关联字段
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

### 关系上的子查询

```python
# EXISTS 子查询
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
    User.latest_post_date >= datetime.now(timezone.utc) - timedelta(days=30)
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

### 带子查询的 JOIN

```python
# 与子查询连接
active_users = User.objects.filter(User.is_active == True).subquery("active_users")
posts = await Post.objects.join(
    active_users, 
    Post.author_id == active_users.c.id
).all()
```

## 关系管理

### 添加关联对象

```python
# 创建关联对象
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
# 好：对外键使用 select_related
posts = await Post.objects.select_related("author", "category").all()

# 好：对反向关系使用 prefetch_related
users = await User.objects.prefetch_related("posts", "comments").all()

# 避免：N+1 查询
posts = await Post.objects.all()
for post in posts:
    author = await post.author.fetch()  # N 个额外查询！

# 好：组合加载策略
posts = await Post.objects.select_related("author").prefetch_related("tags").all()
```

### 选择性字段加载

```python
# 仅从关联对象加载需要的字段
posts = await Post.objects.select_related("author").only(
    "title", "content", "author__username", "author__email"
).all()

# 从关联对象延迟重字段
posts = await Post.objects.select_related("author").defer(
    "content", "author__bio"
).all()
```

### 关系计数

```python
# 高效计数而不加载对象
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
    parent_id: Column[int] = column(type="integer", foreign_key=ForeignKey("categories.id"), nullable=True)

    # 自引用关系
    parent: Related["Category"] = relationship("Category", foreign_keys="parent_id", uselist=False)
    children: Related[list["Category"]] = relationship("Category", foreign_keys="Category.parent_id")

# 使用
category = await Category.objects.get(Category.id == 1)
parent = await category.parent.fetch()
children = await category.children.fetch()
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

### 通过模型关系

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

# 访问通过模型数据
memberships = await Membership.objects.filter(
    Membership.user_id == 1,
    Membership.role == "admin"
).all()
```

## 级联操作

SQLObjects 在两个独立层面支持级联删除和更新：**数据库层**（由数据库引擎强制执行的外键引用动作）和 **ORM 层**（保存或删除实例时由 SQLObjects 处理的关系级联）。两者可单独使用，也可同时使用。

### 数据库层级联（foreign_key）

`foreign_key()` 字段描述符接受 `ondelete` 和 `onupdate` 引用动作。它们通过生成的 `FOREIGN KEY` 约束由数据库强制执行。传入 `OnDelete` / `OnUpdate` 枚举成员或等价的字符串（`"CASCADE"`、`"SET NULL"`、`"RESTRICT"`、`"NO ACTION"`）。

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, TextColumn, foreign_key
from sqlobjects import OnDelete

class Comment(ObjectModel):
    body: Column[str] = TextColumn()

    # 当被引用的 post 被删除时，数据库同时删除该 comment。
    post_id: Column[int] = foreign_key("Post.id", ondelete=OnDelete.CASCADE)

    # 将外键置为 NULL 而不是删除该行。
    author_id: Column[int] = foreign_key(
        "User.id", nullable=True, ondelete=OnDelete.SET_NULL
    )
```

`OnDelete` 从顶层 `sqlobjects` 包导出。引用动作的字符串取值为 `CASCADE`、`SET NULL`、`RESTRICT` 和 `NO ACTION`。

### ORM 层级联（relationship）

`relationship()` 函数接受 `cascade` 选项和 `passive_deletes` 标志。ORM 级联决定 SQLObjects 如何在内存中加载的关联实例之间传播保存/删除操作。

```python
from sqlobjects import relationship, CascadePresets
from sqlobjects.fields.relations import Related

class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)

# 删除 User 会级联到它的 posts（孤立的 posts 也会被移除）。
User.posts: Related[list["Post"]] = relationship(
    "Post",
    foreign_keys="Post.author_id",
    cascade=CascadePresets.ALL_DELETE_ORPHAN,
    passive_deletes=True,  # 让数据库处理实际的行删除
)
```

当数据库已经通过 `ondelete=OnDelete.CASCADE` 外键执行级联时，设置 `passive_deletes=True`，这样 SQLObjects 就不会再逐行发出删除。

### 级联预设

`CascadePresets` 为常见场景提供现成的级联字符串（`cascade` 参数也接受原始字符串、`CascadeOption` 或 `CascadeOption` 值的集合）：

| 预设 | 展开为 |
| --- | --- |
| `CascadePresets.NONE` | `""` |
| `CascadePresets.SAVE_UPDATE` | `"save-update"` |
| `CascadePresets.DELETE` | `"delete"` |
| `CascadePresets.ALL` | `"save-update, merge, refresh-expire"` |
| `CascadePresets.ALL_DELETE_ORPHAN` | `"all, delete-orphan"` |
| `CascadePresets.SAVE_DELETE` | `"save-update, delete"` |

```python
from sqlobjects import CascadePresets, CascadeOption

# 使用预设
posts = relationship("Post", foreign_keys="Post.author_id",
                     cascade=CascadePresets.SAVE_DELETE)

# 使用一组独立选项
posts = relationship("Post", foreign_keys="Post.author_id",
                     cascade={CascadeOption.SAVE_UPDATE, CascadeOption.DELETE})
```

### delete() 上的自动级联检测

`Model.delete(cascade=None)`（默认）通过检查模型的关系自动检测是否需要级联处理。你也可以显式强制其行为：

```python
user = await User.objects.get(User.id == 1)

await user.delete()                # cascade=None → 从关系自动检测
await user.delete(cascade=True)    # 强制 ORM 级联处理
await user.delete(cascade=False)   # 直接删除，跳过级联
```

对于批量删除，`QuerySet.delete()` 改为接受字符串策略：`"auto"`（默认）、`"full"`、`"fast"` 或 `"none"`（参见 [CRUD 操作](04-crud-operations.md#批量删除)）。

```python
# auto 策略：根据模型的删除信号和关系选择
deleted = await Comment.objects.filter(Comment.post_id == 1).delete()

# 不带 ORM 级联处理的直接 SQL 删除
deleted = await Comment.objects.filter(Comment.post_id == 1).delete(cascade="none")
```

## 最佳实践

### 关系设计

```python
# 使用描述性关系名称
class Order(ObjectModel):
    customer_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
    customer: Related["User"] = relationship("User", back_populates="orders")

class User(ObjectModel):
    orders: Related[list["Order"]] = relationship("Order", back_populates="customer")
```

### 加载策略选择

```python
# 使用 select_related 用于：
# - 外键关系（多对一）
# - 一对一关系
posts = await Post.objects.select_related("author", "category").all()

# 使用 prefetch_related 用于：
# - 反向外键关系（一对多）
# - 多对多关系
users = await User.objects.prefetch_related("posts", "groups").all()
```

### 错误处理

```python
from sqlobjects.exceptions import DoesNotExist

# 处理缺失的关联对象
try:
    post = await Post.objects.get(Post.id == 1)
    author = await post.author.fetch()
except DoesNotExist:
    # 处理作者被删除的情况
    author = None

# 检查空关系
user = await User.objects.get(User.id == 1)
profile = await user.profile.fetch()  # 一对一关系可能为 None
if profile:
    bio = profile.bio
```

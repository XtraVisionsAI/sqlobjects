# SQLObjects 关系处理设计文档

## 概述

SQLObjects 关系处理模块通过统一的 relationship() 函数和 Column 描述符集成，提供完整的模型关系支持。通过 RelatedObject/RelatedCollection 延迟加载、QuerySet 集成的 select_related/prefetch_related 和自定义 QuerySet 配置，实现高性能的关系数据访问。

## 核心功能

### 1. 统一 relationship() 定义

通过统一的 relationship() 函数和 Column 描述符集成支持多种关系类型：

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
  
    # 关系字段 - 返回 Related 容器
    author: Related[User] = relationship("User", foreign_keys="author_id")

# relationship() 返回 Related 容器：
# - Related 包装 RelationshipProperty
# - ModelProcessor 从 Related 中提取 RelationshipDescriptor
# - RelationshipDescriptor 返回 RelatedObject 或 RelatedCollection 代理

class Tag(ObjectModel):
    name: Column[str] = StringColumn(length=50)

# 多对多关系 - 使用 secondary 参数
class PostTag(ObjectModel):
    post_id: Column[int] = column(type="integer", foreign_key=ForeignKey("posts.id"))
    tag_id: Column[int] = column(type="integer", foreign_key=ForeignKey("tags.id"))

# 动态添加关系字段
Post.tags = relationship("Tag", secondary="post_tags")
Tag.posts = relationship("Post", secondary="post_tags")
```

### 2. JOIN 查询优化

智能 JOIN 查询构建，支持嵌套关系和别名处理：

```python
# 单层关系预加载
posts = await Post.objects.select_related("author").all()

# 多层关系预加载
comments = await Comment.objects.select_related(
    "post__author", "user__profile"
).all()

# 同时预加载多个关系
posts = await Post.objects.select_related(
    "author", "category"
).all()
```

### 3. 高级预取加载策略

QuerySet 集成的 prefetch_related，支持自定义 QuerySet 配置和 RelatedObject/RelatedCollection 延迟加载：

```python
# 简单预取 - 使用默认 QuerySet
users = await User.objects.prefetch_related("posts").all()

# 高级预取配置 - 传递自定义 QuerySet
users = await User.objects.prefetch_related(
    published_posts=Post.objects.filter(Post.is_published == True)
                               .order_by("-created_at")
                               .limit(5)
).all()

# 混合使用 - 支持字符串和 QuerySet 配置
users = await User.objects.prefetch_related(
    "profile",  # 简单预取
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
    ).order_by("-created_at")
).all()

# QueryExecutor 处理预取：
# 1. 并发执行所有预取查询
# 2. 按外键关系分组结果
# 3. 将结果关联到主实例

# RelatedCollection 延迟加载
user = await User.objects.first()
# user.posts 返回 RelatedCollection 代理
# await user.posts.fetch() 实际加载数据
```

### 4. 多对多关系

完整的多对多关系支持，包括中间表管理和关系操作：

```python
# 多对多关系定义
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, StringColumn, column
from sqlobjects.fields.relations import relationship, Related
from sqlalchemy import ForeignKey
from datetime import datetime, timezone

class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)

class Role(ObjectModel):
    name: Column[str] = StringColumn(length=50)

# 中间表
class UserRole(ObjectModel):
    user_id: Column[int] = column(type="integer", foreign_key=ForeignKey("users.id"))
    role_id: Column[int] = column(type="integer", foreign_key=ForeignKey("roles.id"))
    assigned_at: Column[datetime] = column(type="datetime", default_factory=datetime.now)

User.roles = relationship("Role", secondary="user_roles")

# 关系操作
user = await User.objects.get(User.id == 1)
roles = await user.roles.fetch()  # 获取用户角色
```

### 5. 级联策略

SQLObjects 在两个协作层面统一级联行为（`sqlobjects/cascade.py`）：

**数据库层 —— `ondelete` / `onupdate`。** 由数据库引擎强制执行的外键约束行为。通过 `foreign_key(..., ondelete="CASCADE")`（或 `OnDelete` / `OnUpdate` 枚举，其取值为 `CASCADE`、`SET NULL`、`RESTRICT`、`NO ACTION`）在外键本身上配置。这些行为无需 ORM 往返：数据库自行删除或置空依赖行。

**ORM 层 —— `cascade`。** 应用层级联，在 `relationship(cascade=...)` 上配置。选项由 `CascadeOption` 建模（`save-update`、`merge`、`delete`、`delete-orphan`、`refresh-expire`、`all`），并在 `CascadePresets` 中提供便捷组合（如 `ALL_DELETE_ORPHAN = "all, delete-orphan"`）。ORM 级联通过 ORM 运行，因此会发射生命周期信号，且能遍历数据库没有约束的关系。

**自动检测与分派。** `Model.delete(cascade=None)` 通过调用 `_has_on_delete_relations()`（`model.py`）自动检测是否需要级联处理，该方法检查模型关系中是否有包含 `delete`/`all` 的 `cascade` 字符串，或非 `NO ACTION` 的 `on_delete`。当需要级联（或用 `cascade=True` 强制）时，删除会分派到 `CascadeExecutor.execute_delete_operation()`；否则执行直接的 `_delete_internal()`。`cascade=False` 始终跳过级联。

**组件。**

- **OnDelete / OnUpdate**: 数据库层外键约束行为的枚举。
- **CascadeOption / CascadePresets**: ORM 层级联选项及预设组合；`CascadeType` 和 `normalize_*` 辅助函数将枚举/字符串/集合输入强制转换为 SQLAlchemy 级联字符串。
- **DependencyResolver**: 通过拓扑排序为级联保存排序实例，并进行 DFS 环检测（循环依赖时抛出 `CyclicDependencyError`）。
- **CascadeExecutor**: 执行保存/删除/更新级联，包含会话管理与信号兼容。对于 QuerySet 删除，它自动选择策略（存在删除信号时用 `full`，存在级联删除关系时用 `fast`，否则用 `none`）。

## 模块架构

### 核心组件

**关系定义层**

- **relationship()**: 统一关系定义函数，返回 Related 容器
- **Related**: 包装 RelationshipProperty 的容器，用于类型提示
- **RelationshipDescriptor**: 关系描述符，处理关系字段访问和代理
- **RelationshipProperty**: 关系属性定义，存储关系元数据

**延迟加载层**

- **RelatedObject**: 单个关系字段的代理（ForeignKey、OneToOne）
- **RelatedCollection**: 集合关系的代理（OneToMany、ManyToMany）
- **FieldCacheMixin**: 集成在 ObjectModel 中，自动处理代理对象

**查询集成层**

- **QuerySet.select_related()**: JOIN 预加载，支持字符串和字段表达式
- **QuerySet.prefetch_related()**: 分离查询预取，支持自定义 QuerySet 配置
- **QueryExecutor**: 统一处理预取查询执行和结果关联

**级联层 (`cascade.py`)**

- **OnDelete / OnUpdate**: 数据库层外键约束行为
- **CascadeOption / CascadePresets**: ORM 层级联选项及预设
- **DependencyResolver**: 级联保存的拓扑排序与环检测
- **CascadeExecutor**: 执行级联保存/删除/更新；为 QuerySet 自动选择删除策略

### 设计理念

**统一集成**: relationship() 函数返回 Related 容器，ModelProcessor 提取描述符
**延迟加载**: RelatedObject 和 RelatedCollection 提供透明的延迟加载和缓存
**灵活预取**: prefetch_related 支持字符串和自定义 QuerySet 的混合使用
**并发优化**: QueryExecutor 并发执行多个预取查询，提高性能
**自动关联**: 根据外键关系自动分组和关联预取结果
**容错处理**: 预取失败时返回空列表，不影响主查询

### 与其他模块的集成

**核心架构模块**: 通过 ModelProcessor 注册关系定义
**数据操作模块**: 集成 select_related 和 prefetch_related 方法
**字段系统模块**: 支持关系字段的表达式操作

## API 参考

### 关系定义

```python
# 完整签名（sqlobjects/fields/relations/utils.py）
relationship(
    argument,                  # 目标模型类或其字符串名称
    *,
    foreign_keys=None,         # 本模型上的外键字段名（多对一侧）
    remote_fields=None,        # 关联模型上的外键字段名（一对多/一对一侧）
    back_populates=None,       # 反向关系属性的名称
    backref=None,              # 自动创建反向关系（与 back_populates 互斥）
    lazy="select",             # 加载策略
    uselist=None,              # 关系是否返回集合
    secondary=None,            # 多对多关联表名或 M2MTable 实例
    primaryjoin=None,
    secondaryjoin=None,
    order_by=None,             # 集合的默认排序
    cascade=None,              # ORM 层级联行为（参见级联策略）
    passive_deletes=False,
    **kwargs
)

# 多对一 / 外键关系
author: Related[User] = relationship("User", foreign_keys="author_id", back_populates="posts")

# 一对多（反向）关系
posts: Related[list[Post]] = relationship("Post", back_populates="author")

# 多对多关系
tags: Related[list[Tag]] = relationship("Tag", secondary="post_tags", back_populates="posts")

# 一对一关系
# relationship() 没有 `unique=` 参数。一对一通过父侧的
# uselist=False 加上子侧的 UNIQUE 外键来表达。
#   User 侧:    profile: Related[Profile] = relationship("Profile", back_populates="user", uselist=False)
#   Profile 侧: user_id: Column[int] = foreign_key("User.id", unique=True)
#              user = relationship("User", back_populates="profile")
```

### 关系加载

```python
# JOIN 预加载
.select_related(*fields)  # 使用字符串指定关系字段

# 分离查询预取
.prefetch_related(*fields, **queryset_configs)  # 支持字符串和自定义 QuerySet

# 关系过滤
.filter(Model.relation__field == value)
```

### 关系操作

```python
# 关系访问
instance.relation_name  # 获取关系代理（RelatedObject 或 RelatedCollection）
await instance.relation_name.fetch()  # 获取关联数据

# 集合操作
await instance.relation_name.count()  # 计数关联对象

# 关系修改
await instance.relation_name.add(related_instance)
await instance.relation_name.remove(related_instance)
await instance.relation_name.clear()
```

## 使用指南

### 基础使用

```python
# 基本关系定义
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

# 关系查询
posts = await Post.objects.select_related("author").all()
for post in posts:
    print(f"{post.title} by {post.author.name}")

# 反向关系
User.posts: Related[list[Post]] = relationship("Post", foreign_keys="Post.author_id")
user = await User.objects.get(User.id == 1)
user_posts = await user.posts.fetch()
```

### 高级使用

```python
# 复杂关系结构
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

# 多层关系预加载
comments = await Comment.objects.select_related(
    "post__author",      # Comment -> Post -> Author
    "post__category",    # Comment -> Post -> Category
    "user"               # Comment -> User
).all()

# 高级预取配置
users = await User.objects.prefetch_related(
    # 简单预取
    "profile",
  
    # 自定义预取查询
    published_posts=Post.objects.filter(
        Post.is_published == True
    ).select_related("category").order_by("-created_at").limit(5),
  
    # 嵌套预取
    recent_comments=Comment.objects.filter(
        Comment.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
    ).select_related("post").order_by("-created_at")
).all()

# 多对多关系
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

# 多对多操作
user = await User.objects.get(User.id == 1)
admin_role = await Role.objects.get(Role.name == "admin")

# 添加关系
await UserRole.objects.create(
    user_id=user.id,
    role_id=admin_role.id,
    assigned_by=current_user.id
)

# 查询多对多关系
users_with_roles = await User.objects.prefetch_related("roles").all()
for user in users_with_roles:
    roles = await user.roles.fetch()
    print(f"{user.name}: {[role.name for role in roles]}")

# 复杂关系查询
# 查找具有特定角色的用户
admin_users = await User.objects.filter(
    User.roles__name == "admin"
).distinct().all()

# 查找最近活跃的用户及其帖子
active_users = await User.objects.filter(
    User.posts__created_at >= datetime.now(timezone.utc) - timedelta(days=30)
).prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
    ).order_by("-created_at")
).distinct().all()
```

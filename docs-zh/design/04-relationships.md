# SQLObjects 关系处理设计文档

## 概述

SQLObjects 关系处理模块通过统一的 relationship() 函数和 Column 描述符集成，提供完整的模型关系支持。通过 RelationFieldProxy 延迟加载、QuerySet 集成的 select_related/prefetch_related 和自定义 QuerySet 配置，实现高性能的关系数据访问。

## 核心特性

### 1. 统一 relationship() 定义

通过统一的 relationship() 函数和 Column 描述符集成，支持多种关系类型：

```python
class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=100)
    author_id: Column[int] = foreign_key("users.id")  # 外键字段
    
    # 关系字段 - 使用 Column 描述符统一处理
    author: Column[User] = relationship("User", foreign_keys="author_id")

# Column 描述符自动识别关系字段：
# - 设置 _is_relationship = True
# - 使用 RelationshipDescriptor 处理访问
# - 集成到 ModelProcessor 的 _relationships 字典

class Tag(ObjectModel):
    name: Column[str] = StringColumn(length=50)

# 多对多关系 - 使用 through 参数
class PostTag(ObjectModel):
    post_id: Column[int] = foreign_key("posts.id")
    tag_id: Column[int] = foreign_key("tags.id")

# 动态添加关系字段
Post.tags = relationship("Tag", through="PostTag")
Tag.posts = relationship("Post", through="PostTag")
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

# 多个关系同时预加载
posts = await Post.objects.select_related(
    "author", "category"
).all()
```

### 3. 高级预取加载策略

QuerySet 集成的 prefetch_related 支持自定义 QuerySet 配置和 RelationFieldProxy 延迟加载：

```python
# 简单预取 - 使用默认 QuerySet
users = await User.objects.prefetch_related("posts").all()

# 高级预取配置 - 传入自定义 QuerySet
users = await User.objects.prefetch_related(
    published_posts=Post.objects.filter(Post.is_published == True)
                               .order_by("-created_at")
                               .limit(5)
).all()

# 混合使用 - 支持字符串和 QuerySet 配置
users = await User.objects.prefetch_related(
    "profile",  # 简单预取
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=30)
    ).order_by("-created_at")
).all()

# QueryExecutor 处理预取：
# 1. 并发执行所有预取查询
# 2. 根据外键关系分组结果
# 3. 将结果关联到主实例

# RelationFieldProxy 延迟加载
user = await User.objects.first()
# user.posts 返回 RelationFieldProxy
# await user.posts.fetch() 才真正加载数据
```

### 4. 多对多关系

完整的多对多关系支持，包括中间表管理和关系操作：

```python
# 多对多关系定义
class User(ObjectModel):
    name: str = str_column(length=50)

class Role(ObjectModel):
    name: str = str_column(length=50)

# 中间表
class UserRole(ObjectModel):
    user_id: int = int_column()
    role_id: int = int_column()
    assigned_at: datetime = datetime_column(default=datetime.now)

User.roles = relationship("Role", through="UserRole")

# 关系操作
user = await User.objects.get(User.id == 1)
roles = await user.roles.all()  # 获取用户角色
```

## 模块架构

### 核心组件

**关系定义层**
- **relationship()**: 统一关系定义函数，返回 Column 描述符
- **RelationshipDescriptor**: 关系描述符，处理关系字段访问和代理
- **RelationshipProperty**: 关系属性定义，存储关系元数据

**延迟加载层**
- **RelationFieldProxy**: 关系字段代理，支持延迟加载和缓存
- **FieldCacheMixin**: 集成在 ObjectModel 中，自动处理代理对象

**查询集成层**
- **QuerySet.select_related()**: JOIN 预加载，支持字符串和字段表达式
- **QuerySet.prefetch_related()**: 分离查询预取，支持自定义 QuerySet 配置
- **QueryExecutor**: 统一处理预取查询执行和结果关联

### 设计理念

**统一集成**: relationship() 函数与 Column 描述符统一，简化 API 设计
**延迟加载**: RelationFieldProxy 提供透明的延迟加载和缓存机制
**灵活预取**: prefetch_related 支持字符串和自定义 QuerySet 的混合使用
**并发优化**: QueryExecutor 并发执行多个预取查询，提高性能
**自动关联**: 根据外键关系自动分组和关联预取结果
**错误容错**: 预取失败时返回空列表，不影响主查询

### 与其他模块的集成

**核心架构模块**: 通过 ModelProcessor 注册关系定义
**数据操作模块**: 集成 select_related 和 prefetch_related 方法
**字段系统模块**: 支持关系字段的表达式操作

## API 参考

### 关系定义

```python
# 外键关系
relationship(target_model, foreign_keys=None, back_populates=None)

# 多对多关系
relationship(target_model, through=None, back_populates=None)

# 一对一关系
relationship(target_model, foreign_keys=None, unique=True)
```

### 关系加载

```python
# JOIN 预加载
.select_related(*fields)  # 使用字符串指定关系字段

# 分离查询预取
.prefetch_related(*fields, **queryset_configs)  # 支持字符串和自定义QuerySet

# 关系过滤
.filter(Model.relation__field == value)
```

### 关系操作

```python
# 关系访问
instance.relation_name  # 获取关系对象
await instance.relation_name.all()  # 获取关系列表

# 关系修改
await instance.relation_name.add(related_instance)
await instance.relation_name.remove(related_instance)
await instance.relation_name.clear()
```

## 使用指南

### 基础用法

```python
# 基础关系定义
class User(ObjectModel):
    name: Column[str] = StringColumn(length=50)

class Post(ObjectModel):
    title: Column[str] = StringColumn(length=100)
    author_id: Column[int] = IntegerColumn()
    
    author = relationship("User", foreign_keys="author_id")

# 关系查询
posts = await Post.objects.select_related("author").all()
for post in posts:
    print(f"{post.title} by {post.author.name}")

# 反向关系
User.posts = relationship("Post", foreign_keys="Post.author_id")
user = await User.objects.get(User.id == 1)
user_posts = await user.posts.all()
```

### 高级用法

```python
# 复杂关系结构
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

# 多层关系预加载
comments = await Comment.objects.select_related(
    "post__author",      # 评论 -> 文章 -> 作者
    "post__category",    # 评论 -> 文章 -> 分类
    "user"               # 评论 -> 用户
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
        Comment.created_at >= datetime.now() - timedelta(days=7)
    ).select_related("post").order_by("-created_at")
).all()

# 多对多关系
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
    roles = await user.roles.all()
    print(f"{user.name}: {[role.name for role in roles]}")

# 复杂关系查询
# 查找有特定角色的用户
admin_users = await User.objects.filter(
    User.roles__name == "admin"
).distinct().all()

# 查找最近活跃的用户及其文章
active_users = await User.objects.filter(
    User.posts__created_at >= datetime.now() - timedelta(days=30)
).prefetch_related(
    recent_posts=Post.objects.filter(
        Post.created_at >= datetime.now() - timedelta(days=30)
    ).order_by("-created_at")
).distinct().all()
```
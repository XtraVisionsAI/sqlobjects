# 自定义字段类型

## 概述

通过自定义数据库特定的字段类型来扩展 SQLObjects，支持全文搜索、向量相似度或其他数据库特定功能等专业用例。

## 注册自定义类型

### 基础注册

```python
from sqlalchemy.types import UserDefinedType
from sqlobjects.fields.types.registry import register_field_type
from sqlobjects.fields.types.comparators import DefaultComparator

# 定义 SQLAlchemy 类型
class TSVECTOR(UserDefinedType):
    cache_ok = True
    
    def get_col_spec(self, **kw):
        return "TSVECTOR"

# 注册到全局注册表
# Use register_field_type() to register custom types
register_field_type(TSVECTOR, "tsvector", comparator=DefaultComparator)
```

### 使用自定义操作

```python
from sqlobjects.fields.types.comparators import DefaultComparator

# 为类型特定操作定义自定义比较器
class TSVectorComparator(DefaultComparator):
    def match(self, query: str):
        """全文搜索匹配操作符。
        
        Args:
            query: tsquery 字符串（例如 "python & programming"）
        
        Returns:
            用于过滤的布尔表达式
        """
        from sqlalchemy import func
        return func.to_tsquery(query).op('@@')(self)

# 使用自定义比较器注册
register_field_type(TSVECTOR, "tsvector", comparator=TSVectorComparator)
```

### 使用构造函数参数

```python
class PGVECTOR(UserDefinedType):
    cache_ok = True
    
    def __init__(self, dimensions: int = 1536):
        self.dimensions = dimensions
    
    def get_col_spec(self, **kw):
        return f"VECTOR({self.dimensions})"

register_field_type(
    PGVECTOR, 
    "pgvector", 
    PGVectorComparator,
    default_params={"dimensions": 1536}
)
```

## PostgreSQL 示例

### 全文搜索（tsvector）

**类型定义：**
```python
from sqlalchemy.types import UserDefinedType
from sqlobjects.fields.types.comparators import DefaultComparator
from sqlobjects.fields.types.registry import register_field_type

class TSVECTOR(UserDefinedType):
    cache_ok = True
    
    def get_col_spec(self, **kw):
        return "TSVECTOR"

class TSVectorComparator(DefaultComparator):
    def match(self, query: str):
        """使用 @@ 操作符进行全文搜索。"""
        from sqlalchemy import func
        return func.to_tsquery(query).op('@@')(self)

# 注册
# Use register_field_type() to register custom types
register_field_type(TSVECTOR, "tsvector", comparator=TSVectorComparator)
```

**模型使用：**
```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column

class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(type="text")
    content_vector: Column = column(type="tsvector")
    
    class Config:
        table_name = "documents"
```

**查询示例：**
```python
# 简单全文搜索
docs = await Document.objects.filter(
    Document.content_vector.match("python")
).all()

# 使用 AND/OR 的复杂查询
docs = await Document.objects.filter(
    Document.content_vector.match("python & programming")
).all()

# 带排序和分页
docs = await Document.objects.filter(
    Document.content_vector.match("database | sql")
).order_by("-created_at").limit(10).all()
```

### 向量相似度搜索（pgvector）

**类型定义：**
```python
class PGVECTOR(UserDefinedType):
    cache_ok = True
    
    def __init__(self, dimensions: int = 1536):
        self.dimensions = dimensions
    
    def get_col_spec(self, **kw):
        return f"VECTOR({self.dimensions})"

class PGVectorComparator(DefaultComparator):
    def l2_distance(self, other):
        """L2（欧几里得）距离：<-> 操作符。"""
        return self.op('<->')(other)
    
    def cosine_distance(self, other):
        """余弦距离：<=> 操作符。"""
        return self.op('<=>')(other)
    
    def inner_product(self, other):
        """内积：<#> 操作符。"""
        return self.op('<#>')(other)

# 注册
register_field_type(PGVECTOR, "pgvector", comparator=PGVectorComparator)
```

**模型使用：**
```python
class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(type="text")
    embedding: Column = column(type="pgvector", dimensions=1536)
    
    class Config:
        table_name = "documents"
```

**查询示例：**
```python
# 使用 L2 距离查找相似文档
query_vector = [0.1, 0.2, 0.3, ...]  # 1536 维

similar_docs = await Document.objects.annotate(
    distance=Document.embedding.l2_distance(query_vector)
).order_by("distance").limit(5).all()

# 使用余弦距离
similar_docs = await Document.objects.annotate(
    distance=Document.embedding.cosine_distance(query_vector)
).order_by("distance").limit(5).all()

# 按距离阈值过滤
nearby_docs = await Document.objects.filter(
    Document.embedding.l2_distance(query_vector) < 0.5
).all()
```

## 完整示例

```python
# custom_types.py
from sqlalchemy.types import UserDefinedType
from sqlobjects.fields.types.registry import register_field_type
from sqlobjects.fields.types.comparators import DefaultComparator

# 类型定义
class TSVECTOR(UserDefinedType):
    cache_ok = True
    def get_col_spec(self, **kw):
        return "TSVECTOR"

class PGVECTOR(UserDefinedType):
    cache_ok = True
    def __init__(self, dimensions: int = 1536):
        self.dimensions = dimensions
    def get_col_spec(self, **kw):
        return f"VECTOR({self.dimensions})"

# 比较器
class TSVectorComparator(DefaultComparator):
    def match(self, query: str):
        from sqlalchemy import func
        return func.to_tsquery(query).op('@@')(self)

class PGVectorComparator(DefaultComparator):
    def l2_distance(self, other):
        return self.op('<->')(other)
    def cosine_distance(self, other):
        return self.op('<=>')(other)

# 注册类型
# Use register_field_type() to register custom types
register_field_type(TSVECTOR, "tsvector", comparator=TSVectorComparator)
register_field_type(PGVECTOR, "pgvector", comparator=PGVectorComparator)
```

```python
# models.py
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column
from .custom_types import TSVECTOR, PGVECTOR  # 触发注册

class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(type="text")
    content_vector: Column = column(type="tsvector")
    embedding: Column = column(type="pgvector", dimensions=1536)
```

```python
# usage.py
from sqlobjects.database import init_db, create_tables

async def main():
    # 初始化数据库
    await init_db("postgresql+asyncpg://user:pass@localhost/db")
    await create_tables(ObjectModel)
    
    # 全文搜索
    docs = await Document.objects.filter(
        Document.content_vector.match("python & programming")
    ).all()
    
    # 向量相似度搜索
    query_vector = [0.1] * 1536
    similar = await Document.objects.annotate(
        distance=Document.embedding.l2_distance(query_vector)
    ).order_by("distance").limit(5).all()
    
    for doc in similar:
        print(f"{doc.title}: distance={doc.distance}")
```

## 最佳实践

### 1. 类型注册位置

在定义模型之前注册自定义类型：

```python
# ✅ 好：在单独的模块中注册
# custom_types.py
# Use register_field_type() to register custom types
register_field_type(TSVECTOR, "tsvector", comparator=TSVectorComparator)

# models.py
from .custom_types import TSVECTOR  # 触发注册
```

### 2. 比较器设计

为数据库操作提供直观的方法名：

```python
class PGVectorComparator(DefaultComparator):
    def l2_distance(self, other):  # 清晰、描述性的名称
        return self.op('<->')(other)
    
    def cosine_similarity(self, other):  # 用户友好
        return 1 - self.op('<=>')(other)
```

### 3. 类型参数

为常见配置使用默认参数：

```python
register_field_type(
    PGVECTOR,
    "pgvector",
    PGVectorComparator,
    default_params={"dimensions": 1536}  # 常见的 OpenAI 嵌入大小
)
```

### 4. 数据库扩展

确保启用所需的扩展：

```python
# 对于 PostgreSQL
async def setup_database():
    from sqlobjects.session import get_session
    
    session = get_session(readonly=False)
    await session.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    await session.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await session.commit()
```

## 类型注册表 API

### register_field_type()

向全局注册表注册自定义类型：

```python
from sqlobjects.fields.types.registry import register_field_type

register_field_type(
    field_type: type,                    # SQLAlchemy 类型类
    type_name: str,                      # column(type="name") 的类型名称
    *,                                   # 以下为关键字参数
    comparator: type | None = None,      # 比较器类（可选）
    aliases: list[str] | None = None,    # 替代名称
    default_params: dict | None = None   # 默认构造函数参数
)
```

### 使用所有参数的示例

```python
register_field_type(
    PGVECTOR,
    "pgvector",
    comparator=PGVectorComparator,
    aliases=["vector", "embedding"],  # 可以使用任何这些名称
    default_params={"dimensions": 1536}
)

# 所有等效：
embedding1: Column = column(type="pgvector", dimensions=768)
embedding2: Column = column(type="vector", dimensions=768)
embedding3: Column = column(type="embedding", dimensions=768)
```

## 另请参阅

- [模型定义](02-model-definition.md) - 基本字段类型
- [数据查询](03-querying-data.md) - 查询构建和过滤
- [性能优化](07-performance-optimization.md) - 自定义类型的索引策略

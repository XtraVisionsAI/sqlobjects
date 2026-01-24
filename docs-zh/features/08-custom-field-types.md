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
from sqlalchemy import Index
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column

class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(type="text")
    content_vector: Column = column(type="tsvector")
    
    class Config:
        table_name = "documents"
        indexes = [
            # 用于全文搜索的 GIN 索引（推荐）
            Index("idx_content_vector", "content_vector", postgresql_using="gin"),
        ]
```

**索引选项：**
```python
class Config:
    indexes = [
        # GIN 索引（查询更快，更新更慢，占用更多空间）
        Index("idx_content_gin", "content_vector", postgresql_using="gin"),
        
        # GiST 索引（更新更快，查询更慢，占用更少空间）
        Index("idx_content_gist", "content_vector", postgresql_using="gist"),
    ]
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
from sqlalchemy import Index

class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(type="text")
    embedding: Column = column(type="pgvector", dimensions=1536)
    
    class Config:
        table_name = "documents"
        indexes = [
            # 用于近似最近邻搜索的 IVFFlat 索引
            Index("idx_embedding", "embedding",
                  postgresql_using="ivfflat",
                  postgresql_ops={"embedding": "vector_l2_ops"}),
        ]
```

**索引选项：**
```python
class Config:
    indexes = [
        # 使用 L2 距离的 IVFFlat（欧几里得）
        Index("idx_embedding_l2", "embedding",
              postgresql_using="ivfflat",
              postgresql_ops={"embedding": "vector_l2_ops"}),
        
        # 使用余弦距离的 IVFFlat
        Index("idx_embedding_cosine", "embedding",
              postgresql_using="ivfflat",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        
        # 使用内积的 IVFFlat
        Index("idx_embedding_ip", "embedding",
              postgresql_using="ivfflat",
              postgresql_ops={"embedding": "vector_ip_ops"}),
        
        # HNSW 索引（查询更快，占用更多内存）
        Index("idx_embedding_hnsw", "embedding",
              postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_l2_ops"}),
    ]
```

**索引配置：**
```python
# IVFFlat 需要训练 - 设置 lists 参数
# 经验法则：lists = rows / 1000（对于 > 1M 行的数据集）
async def create_ivfflat_index():
    from sqlobjects.session import get_session
    
    session = get_session(readonly=False)
    await session.execute(
        "CREATE INDEX idx_embedding ON documents "
        "USING ivfflat (embedding vector_l2_ops) WITH (lists = 100)"
    )
    await session.commit()
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
from sqlalchemy import Index
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column
from .custom_types import TSVECTOR, PGVECTOR  # 触发注册

class Document(ObjectModel):
    title: Column[str] = column(type="string", length=200)
    content: Column[str] = column(type="text")
    content_vector: Column = column(type="tsvector")
    embedding: Column = column(type="pgvector", dimensions=1536)
    
    class Config:
        table_name = "documents"
        indexes = [
            Index("idx_content_vector", "content_vector", postgresql_using="gin"),
            Index("idx_embedding", "embedding",
                  postgresql_using="ivfflat",
                  postgresql_ops={"embedding": "vector_l2_ops"}),
        ]
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

### 5. 索引创建

创建索引以获得最佳查询性能：

```python
from sqlalchemy import Index

class Config:
    indexes = [
        # tsvector：使用 GIN 进行全文搜索
        Index("idx_content_vector", "content_vector", postgresql_using="gin"),
        
        # pgvector：使用 IVFFlat 或 HNSW 进行相似度搜索
        Index("idx_embedding", "embedding",
              postgresql_using="ivfflat",
              postgresql_ops={"embedding": "vector_l2_ops"}),
    ]
```

**索引选择指南：**

| 类型 | 方法 | 使用场景 | 速度 | 内存 |
|------|--------|----------|------|------|
| tsvector | GIN | 全文搜索（推荐） | 快速查询 | 高 |
| tsvector | GiST | 频繁更新的全文搜索 | 中等 | 低 |
| pgvector | IVFFlat | 大数据集（>100K 向量） | 快速 | 中等 |
| pgvector | HNSW | 最高查询速度 | 最快 | 最高 |
| pgvector | 无 | 小数据集（<10K 向量） | 慢 | 无 |

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

## 性能考虑

### tsvector 索引

**GIN vs GiST：**
```python
# GIN：更适合读密集型工作负载
Index("idx_gin", "content_vector", postgresql_using="gin")
# - 查询快 3 倍
# - 更新慢 3 倍
# - 磁盘空间多 2-3 倍

# GiST：更适合写密集型工作负载
Index("idx_gist", "content_vector", postgresql_using="gist")
# - 更新更快
# - 查询更慢
# - 磁盘空间更少
```

### pgvector 索引

**IVFFlat 配置：**
```python
# lists 参数影响速度/准确性权衡
# 更多 lists = 查询更快，准确性更低
# 更少 lists = 查询更慢，准确性更高

# 小数据集（<100K）：lists = 100
# 中等数据集（100K-1M）：lists = rows / 1000
# 大数据集（>1M）：lists = sqrt(rows)

Index("idx_embedding", "embedding",
      postgresql_using="ivfflat",
      postgresql_ops={"embedding": "vector_l2_ops"})
```

**HNSW 配置：**
```python
# HNSW 提供比 IVFFlat 更好的查询性能
# 但需要更多内存和构建时间

Index("idx_embedding_hnsw", "embedding",
      postgresql_using="hnsw",
      postgresql_ops={"embedding": "vector_l2_ops"},
      postgresql_with={"m": 16, "ef_construction": 64})
# m：每层最大连接数（更高 = 更好的召回率，更多内存）
# ef_construction：构建时间质量（更高 = 更好的索引，更慢的构建）
```

**距离操作符选择：**
```python
# 根据相似度度量选择操作符
operators = {
    "vector_l2_ops": "L2 距离（欧几里得）",      # 最常见
    "vector_cosine_ops": "余弦距离",            # 归一化向量
    "vector_ip_ops": "内积（负值）",            # 点积
}
```

## 另请参阅

- [模型定义](02-model-definition.md) - 基本字段类型
- [数据查询](03-querying-data.md) - 查询构建和过滤
- [性能优化](07-performance-optimization.md) - 索引策略

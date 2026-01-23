# 自定义类型示例

演示如何使用自定义数据库特定字段类型扩展 SQLObjects 的示例。

## PostgreSQL 类型

### [postgresql_types.py](postgresql_types.py)

完整示例展示：
- **tsvector** - 全文搜索
- **pgvector** - 向量相似度搜索

**功能：**
- 使用自定义比较器进行类型注册
- 全文搜索查询
- 向量相似度操作（L2、余弦、内积）
- 组合文本 + 语义搜索

**要求：**
```sql
CREATE EXTENSION pg_trgm;
CREATE EXTENSION vector;
```

**运行：**
```bash
uv run python examples/custom_types/postgresql_types.py
```

## 创建自定义类型

### 1. 定义 SQLAlchemy 类型

```python
from sqlalchemy.types import UserDefinedType

class MyCustomType(UserDefinedType):
    cache_ok = True
    
    def get_col_spec(self, **kw):
        return "CUSTOM_TYPE_NAME"
```

### 2. 创建比较器（可选）

```python
from sqlobjects.fields.types.comparators import DefaultComparator

class MyCustomComparator(DefaultComparator):
    def custom_operation(self, value):
        return self.op('CUSTOM_OP')(value)
```

### 3. 注册类型

```python
from sqlobjects.fields.types.registry import register_field_type

# Use register_field_type() to register custom types
register_field_type(MyCustomType, "mytype", comparator=MyCustomComparator)
```

### 4. 在模型中使用

```python
from sqlobjects.model import ObjectModel
from sqlobjects.fields import Column, column

class MyModel(ObjectModel):
    custom_field: Column = column(type="mytype")
```

## 另请参阅

- [自定义字段类型文档](../../docs-zh/features/08-custom-field-types.md)
- [模型定义](../../docs-zh/features/02-model-definition.md)
- [数据查询](../../docs-zh/features/03-querying-data.md)

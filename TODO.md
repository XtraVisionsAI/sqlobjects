# SQLObjects TODO - 未来功能规划

## 已实现功能 ✅

### 窗口函数支持 (v1.0)

```python
# 排名和分析函数
User.objects.annotate(
    rank=func.rank().over(order_by=[User.score.desc()]),
    row_number=func.row_number().over(partition_by=[User.department])
)

# 支持的窗口函数:
# - ROW_NUMBER, RANK, DENSE_RANK, PERCENT_RANK
# - LAG, LEAD, FIRST_VALUE, LAST_VALUE, NTH_VALUE
# - NTILE
```

### 查询计划分析 (v1.0)

```python
# 查询执行计划
plan = await User.objects.filter(User.age > 25).explain()
detailed = await User.objects.filter(User.name == "Alice").explain(analyze=True, verbose=True)
```

### UPSERT 操作 (v1.0)

```python
# 内部使用 UpsertHandler 实现
# PostgreSQL: ON CONFLICT
# SQLite: INSERT OR REPLACE
# 在 save() 方法中自动使用
```

### CTE (Common Table Expressions) 支持 (v1.0)

```python
# 基础 CTE
adults = User.objects.filter(User.age >= 18).cte("adults")
result = await User.objects.with_cte(adults).filter(adults.c.age < 30).all()

# 多个 CTE
adults = User.objects.filter(User.age >= 18).cte("adults")
active = User.objects.filter(User.is_active == True).cte("active")
result = await User.objects.with_cte(adults, active).all()

# 递归 CTE
base = Employee.objects.filter(Employee.manager_id.is_(None)).cte("tree", recursive=True)
recursive_part = Employee.objects.join(base, Employee.manager_id == base.c.id)
tree = base.union_all(recursive_part)
result = await Employee.objects.with_cte(tree).all()
```

## 数据库管理增强

### 数据库健康检查

```python
# 数据库连接健康检查
await check_db_health("primary")
await check_db_health("replica") 

# 动态数据库切换
await switch_default_db("backup")
await switch_default_db("primary")

# 连接池状态监控
pool_stats = await get_connection_pool_stats()
```

## 批量操作增强

### 批量Upsert操作增强 ⏳

```python
# 批量插入或更新 (当前已有基础实现，需要增强)
await User.objects.bulk_upsert(
    data=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
    match_fields=["id"]
)

# 冲突时更新策略
await User.objects.bulk_create(
    data=users_data,
    on_conflict="update",  # 当前只支持 "ignore"
    update_fields=["name", "email"]
)
```

## 高级SQL功能

### 高级聚合函数 ⏳

```python
# 数组聚合、JSON聚合等
User.objects.aggregate(
    tags=ArrayAgg("tags"),
    profile=JsonAgg("profile_data")
)
```

## 查询优化增强

### 索引建议 ⏳

```python
# 自动索引建议
suggestions = await User.objects.get_index_suggestions()
await User.objects.create_suggested_indexes()
```

### 查询性能分析 ⏳

```python
# 慢查询检测
slow_queries = await get_slow_queries(threshold=1000)  # ms
await log_query_performance(enable=True)
```

## 数据迁移增强

### 自动迁移生成

```python
# 基于模型变更自动生成迁移
await generate_migration_from_models()
await apply_pending_migrations()
```

### 数据迁移工具

```python
# 大数据量迁移优化
await migrate_data_in_batches(
    source_table="old_users",
    target_table="users",
    batch_size=10000
)
```

## 实现优先级

### 高优先级 (v2.0)

- 数据库健康检查
- 批量Upsert操作增强

### 中优先级 (v2.1)

- 高级聚合函数 (ArrayAgg, JsonAgg)
- 索引建议功能
- 自动迁移生成

### 低优先级 (v2.2+)

- 查询性能分析工具
- 复杂查询优化
- 数据迁移工具

## 设计原则

1. **保持简洁** - 不增加不必要的复杂性
2. **向后兼容** - 新功能不破坏现有API
3. **性能优先** - 所有新功能都要考虑性能影响
4. **渐进增强** - 功能可选，不影响核心使用
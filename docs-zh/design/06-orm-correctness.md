# 持久化与查询契约

ORM 使用 SQLAlchemy Core 处理 SQL 和连接管理。这些契约定义了其模型与 QuerySet API 的行为。
回归测试覆盖位于 `tests/integration/test_orm_contracts.py`、`test_commit_callbacks.py`、
`test_query_logging_contracts.py`、`test_distinct_contracts.py`、
`test_signal_contracts.py`、`test_database_events.py`、
`test_dynamic_relationships.py`、`test_aggregate_contracts.py`、
`test_grouped_aggregation.py`、`test_schema_naming.py` 和 `test_index_contracts.py`。
这些测试在 CI 中针对 SQLite、PostgreSQL 和 MySQL 运行。

## 已持久化对象与部分对象

从数据库加载的对象会保留其数据库别名。后续的 `save()`、`delete()`、`refresh()` 以及延迟字段的读取
都使用该别名，除非被 `using()` 覆盖。显式绑定的会话保留其原有的生命周期规则。

数据库水合（hydration）不会对缺失的列应用 Python 构造默认值。`only()` 保留主键；未选中的字段保持延迟状态。
为延迟字段赋值会在本地加载它并将其标记为脏。保存已持久化对象时只更新已赋值的列，
因此过期对象不会覆盖无关的变更。保存未变更的对象不会执行 UPDATE。对可变值的原地修改仍需重新赋值该字段
才能将其标记为脏。

新对象使用 INSERT 并读取生成的主键。保存一个带有已存在主键的新构造对象时，保留分离对象的更新行为。
对同一字段的并发更新仍是最后写入者胜出；此变更不添加乐观版本检查。事务回滚不会回退 Python 对象的状态；
请丢弃或刷新受影响的实例。

## 写入与事务边界

QuerySet 的 `update()` 和 `delete()` 在发出 SQL 之前会拒绝 LIMIT、OFFSET、分组、HAVING、DISTINCT 和连接。
从读查询派生写操作时，绝不能静默丢弃这些子句。

实例写入请求可写会话。复合级联操作和隐式批量写入拥有自己的事务；在显式可写会话内的操作则参与该会话的事务。

| 批量模式 | 边界 |
| --- | --- |
| `INHERIT` | 使用调用方的事务，或为整个隐式调用拥有一个事务。 |
| `INDEPENDENT` | 在同一数据库上为所有批次拥有一个独立的事务。 |
| `BATCH` | 每个批次拥有一个独立的事务；先前已提交的批次在之后的失败中得以保留。 |
| `SAVEPOINT` | 在调用方的事务内或在一个自有事务内，用保存点隔离每个批次。 |

保存点之外的 SQL 错误会使显式事务在回滚之前不可用。仅捕获异常并不能恢复它。只读会话不持有事务，
并在每条语句之后释放其连接，因此那里的失败查询不会影响后续查询。对于可恢复的错误：

```python
async with ctx_session() as session:
    try:
        async with await session.begin_nested():
            await User.objects.create(username="duplicate")
    except IntegrityError:
        pass
    await User.objects.create(username="next")
```

在隐式（自动提交）会话上调用 `begin_nested()` 只会为其保存点打开一个事务。当最外层保存点被释放或回滚时，
该事务提交并归还连接，因此在保存点内释放的工作会像单独的自动提交语句一样被持久化。

`COLLECT` 和 `IGNORE` 用保存点隔离每条尝试写入的记录。`COLLECT` 跨批次报告输入索引。
独立连接可能被外层事务持有的锁阻塞；请避免在独立批次中写入这些行。独立连接也看不到外层事务尚未提交的行：
用 `INDEPENDENT` 或 `BATCH` 更新、删除这些行时匹配不到任何记录，返回 `success_count=0` 且不报错，
因此请先提交。SQLite 还在数据库层面限制并发写入者。

### 异步任务所有权与清理

打开的会话属于拥有它的 asyncio 任务。将 ContextVar 复制到子任务不会克隆其连接或事务。
通过继承的或显式传入的父会话执行 ORM 操作，会在触及数据库之前抛出 `TransactionError`。
每个并发工作者必须打开自己的 `ctx_session()`；`join_ambient=True` 无法加入另一个活动任务的事务。
这些独立事务不会随父事务一起回滚。

`has_session()` 只报告当前任务可用的会话。在前一个所有者任务结束后支持顺序交接，
但被其上下文管理器关闭的会话仍保持关闭。隐式的按语句释放连接使会话对象可在顺序操作中复用。

取消会回滚活动的上下文/请求事务。即使清理过程抛出异常，会话上下文令牌也会被恢复，
且多数据库清理会尝试关闭每个会话。事务内的超时应使用 `asyncio.timeout()`，
因为 `wait_for()` 会为协程创建另一个任务。API 暴露的底层 SQLAlchemy 连接、结果游标和事务句柄
也必须留在其所属的任务中。

这遵循 [SQLAlchemy 关于每个并发任务一个会话的指导](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks)。

`get_or_create()` 用保存点隔离创建操作，并在完整性冲突后重试查找。要实现并发唯一性，
查找字段上必须有数据库唯一约束。无关的完整性错误会向外传播。`update_or_create()` 在数据库支持时
会在其写事务内锁定已有行。在 SQLite 之外，显式的 `select_for_update()` / `select_for_share()` 读取
需要显式事务。隔离级别的序列化失败和死锁仍需要应用层重试。

### 提交回调

`await session.on_commit(callback)` 在显式可写会话上排队一个可调用对象，即便在其第一条语句之前。
`await on_commit(callback)` 选择环境会话，并在不存在显式事务时立即执行。
`SignalContext.on_commit()` 使用该操作所用的会话，包括实例绑定或传给 `save()` 的会话。
同步回调及可等待的返回值在根提交成功后按注册顺序运行。

每个回调保留其保存点谱系。保存点回滚会移除它自己的回调以及已释放子保存点的回调；仅释放绝不会运行它们。
根回滚、关闭或提交失败会丢弃整个队列。保存点包装器为 `async with await session.begin_nested()`
精确启动一个物理 SAVEPOINT，强制任务所有权和逆序完成，并把对已释放保存点的清理视为空操作。

提交所用的连接在分派之前归还到连接池。已提交的数据库别名会暂时从环境会话中移除，
因此即使是单连接的连接池，回调查询也会使用新的会话。分派期间拒绝显式复用提交中的会话。
回调无法撤销已提交的数据：错误会传播并阻止后续回调，除非设置 `robust=True`，它会记录普通异常并继续。
取消始终会传播。

回调内联运行，不是持久化投递。需要崩溃安全的副作用时请使用事务性发件箱。多数据库上下文按顺序提交每个数据库；
回调不提供分布式提交边界。这些语义遵循
[Django 的提交回调契约](https://docs.djangoproject.com/en/5.2/topics/db/transactions/#performing-actions-after-commit)，
并增加了异步回调支持和显式会话所有权。

### 信号执行

管理器 `create()` 在 INSERT 前后发出实例的 save/create 钩子，即使调用方提供了主键。
before 钩子可以在验证之前更改值；after 钩子看到的是已持久化的对象。它加入显式可写事务，
或拥有一个覆盖钩子与 SQL 的事务。QuerySet 的 update/delete 钩子使用与写入相同的事务和数据库绑定；
不支持的写入子句会在任何钩子运行之前被拒绝。

管理器的批量钩子在每个批次的实际事务或保存点内运行一次。create/update 先发出通用的批量保存钩子，
再发出操作特定的钩子；批量方法不发出实例钩子。before 计数描述批次的输入；after 计数与该批次的成功结果一致。
空输入不发出钩子。QuerySet 的 before 计数保持未知，其 after 计数即返回的计数。

在每种错误策略下钩子错误都会传播，并回滚自有的事务或保存点。加入显式事务时由调用方控制回滚。
提交回调的错误同样会传播，但不会把已提交的记录重新归类为失败输入。这些边界使 `context.on_commit()`
能够正确跟踪全部四种批量事务模式。关于上下文字段和直接实例保存的行为，
参见[信号指南](../features/06-validation-signals.md)。

## 批量结果

UPSERT 处理每一行输入。当 RETURNING 可以按唯一冲突键匹配时，结果会恢复为输入顺序。
返回的键值可能被数据库规范化（字符串转整数、Decimal 精度、时区、不区分大小写的排序规则）；
与原始输入键不相等的行会通过数据库查找来归属，且仅当它们属于该语句自身的 RETURNING 集合时才被接受，
因此计数和对象绝不会丢失已存储的行。其他情况逐行执行。返回的对象包含数据库中存储的值；
缺失的 UPDATE 目标不会产生凭空构造的对象。不支持 RETURNING 的后端使用键来获取已插入或已更新的记录。
这需要额外的查询。

在不报告 executemany 行数的驱动上，准确的 UPDATE 计数可能需要逐条执行。`accurate_count=False`
允许这些驱动返回近似计数。PostgreSQL 和 SQLite 的冲突处理以及 MySQL 的
`INSERT IGNORE` / `ON DUPLICATE KEY UPDATE` 保持其原生方言语义。

## 查询求值与关系

`count()` 统计组合后查询的结果，包括分组、去重和切片。标量计数子查询使用相同的查询形态。

`distinct()` 对选中的列应用普通的 SQL DISTINCT，包括投影值以及因连接而重复的行。
即使没有字段参数，其启用状态也能在克隆后保留。`distinct(*fields)` 需要已知的模型列以及
PostgreSQL 的 DISTINCT ON。SQLite/MySQL 会在执行前拒绝它，包括在计数、存在性检查、流式读取、
子查询、CTE 和 EXPLAIN 内部。这遵循
[Django 对普通 DISTINCT 与 PostgreSQL DISTINCT ON 的区分](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#distinct)。
`aggregate()` 在执行、SQL 渲染、标量子查询和 EXPLAIN 中使用同一条语句。过滤条件（包括 Q 对象、
关键字过滤和绑定的额外 WHERE 子句）、连接和 CTE 在组合后得以保留。DISTINCT、注解和切片通过派生表进行聚合；
普通的未切片聚合使用直接 SELECT。当切片或 DISTINCT ON 需要时会保留排序。

聚合输入会被重新映射到派生表，包括延迟的模型字段和注解别名。普通 DISTINCT 之后的连接/标量输入
必须已经被投影；隐式添加它们会改变去重键。标量输入保持其局部查询作用域，相关聚合子查询在所有受支持的后端上均可工作。
仅投影一个标量表达式时现在会保留模型的 FROM 子句。空输入保留 SQL 聚合的默认值。
显式 GROUP BY 查询现在可以通过 `aggregate()` 进行汇总。派生表只选取分组键和注解，
并保留 HAVING、DISTINCT、切片和 CTE。外层聚合引用分组键或注解别名；分组键之外的直接模型字段会被拒绝。
空输入保留 SQL 聚合的默认值。分组 values API 仍返回各组的单独行。
没有显式分组的 HAVING 以及行锁定仍不受支持。

原生的 SQLAlchemy 分组表达式现在保留其表达式和来源表，而不是被简化为字段名。按注解别名排序也能工作，
因此切片会选取预期的分组。常量分组使用投影别名，以避免 MySQL 将数字字面量视为选择列表的序号。
在分组终端聚合中，注解不能遮蔽模型列。这扩展了
[Django 风格的注解聚合](https://docs.djangoproject.com/en/5.2/topics/db/aggregation/#aggregating-annotations)，
同时保留了 SQLObjects 显式的 `group_by()` API。

这遵循 [Django 的过滤聚合与注解组合](https://docs.djangoproject.com/en/5.2/topics/db/aggregation/)，
并使用 [SQLAlchemy 的派生表和标量子查询 API](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#subqueries-and-ctes)。
[查询指南](../features/03-querying-data.md#汇总分组结果)记录了受支持的组合与边界。

`iterator()` 以有界分区流式读取原始查询并产出模型，保留排序、LIMIT、OFFSET 和延迟字段。
迭代器自有的会话在释放时不做任务所有权检查，因此当 asyncio 从另一个任务终结生成器时，
被 `break` 丢弃的迭代器仍会释放其游标和连接；调用方拥有的会话保持 `close()` 的所有权契约。
终结时机取决于垃圾回收器；如果迭代可能提前停止，请显式关闭它以立即释放资源：

```python
from contextlib import aclosing

async with aclosing(User.objects.order_by("id").iterator(chunk_size=500)) as users:
    async for user in users:
        if should_stop(user):
            break
```

迭代器借用显式会话时，将其生命周期交由调用方管理。MySQL 带预取的流式读取会被拒绝，
因为活动的流式游标无法安全地与预取查询共享连接；请使用显式分页。

`select_related()` 选取并水合单值关系，每条路径一个别名。集合关系使用 `prefetch_related()`。
两者都解析实际的关系和外键元数据，包括非主键的被引用列。约定的 `author_id` 到 `author` 简写
使用该列实际的 FK。无效路径会抛出错误。自定义预取查询集必须以声明的关联模型为目标。
在实现每父级限制之前，切片的预取查询集会被拒绝；全局限制会错误地截断集合。

### 动态集合

`lazy="dynamic"` 现在返回一个可用的 `RelatedQuerySet` 代理，而不是占位符。构建查询不会执行 SQL。
每个新查询捕获父对象当前的引用值和数据库/会话绑定，然后委托给普通的 QuerySet 进行过滤、排序、投影、
计数、流式读取和写入。已构建的 QuerySet 保留其原始作用域。水合使用正常的持久化状态和数据库别名保留机制。

反向关系使用真实的 FK 映射，包括非主键和复合引用。多对多关系对已有的关联表使用成员子查询，
因此重复的链接不会使目标行重复。显式的 `M2MTable` 映射支持自定义列。模型名称在其所属注册表中解析；
不相关的注册表可以安全地包含同名模型。

动态的 `fetch()` 和 `load_relation()` 发出新查询，而不会用缓存的行替换代理。
同步迭代、真值判断和长度获取会被拒绝，取而代之的是异步迭代、`exists()` 和 `count()`。
只有公共的 QuerySet 方法被代理；其他名称会抛出 `AttributeError`，因此 `hasattr()`、
`copy`/`pickle` 协议查找以及 `to_dict(include_relations=True)` 在未保存的父对象上也能工作，
它们会像其他未加载的代理一样跳过动态集合。父对象必须具有完整的主键值，延迟的引用字段必须显式加载。
空的引用值产生空查询。经过动态关系的预加载路径、标量动态关系以及自定义连接条件都会被拒绝。
该代理不添加关系的 add/remove/set 或创建方法。

跨数据库覆盖还暴露了一个可空类型推断缺陷：使用 `column()` 或 `foreign_key()` 的 `Column[int | None]`
被推断为字符串。映射器现在除 `Optional[T]` 之外也能识别 PEP 604 联合类型，保留整数 SQL 类型；
自引用的动态集合测试在全部三种数据库上创建并查询了这个 FK。

这采用了 [Django 的关联管理器](https://docs.djangoproject.com/en/5.2/ref/models/relations/)
所描述的可查询集合模式，并使用 SQLObjects 的异步 Core QuerySet 实现。SQLAlchemy 记录了其遗留动态加载器的
[异步与隐式迭代局限](https://docs.sqlalchemy.org/en/20/orm/large_collections.html#dynamic-relationship)；
SQLObjects 保持求值的显式性，并使用其现有的异步流式路径。
参见[动态集合指南](../features/05-relationships.md#动态集合查询)。

## 查询执行日志

`sqlobjects.sql` 日志器观察每个已配置的引擎，除 QuerySet 读取外还覆盖模型写入、批量操作、原生 SQL 和流式读取。
记录描述物理驱动调用，包括失败和取消；它们不会在 QueryExecutor 层重复记录。
分批的 RETURNING 记录使用每个批次实际的 SQL 和参数，而不是原始的未分批值。

结构化记录包含数据库别名、方言、耗时、驱动行数、executemany 状态以及成功/错误类型。
`hide_parameters=True` 在成功和失败时都抑制绑定值。处理器异常不会改变数据库结果。
调用者查找会跨越 SQLAlchemy 的异步 greenlet 桥遍历栈帧。禁用日志时跳过计时和栈检查，
且日志绝不会重新编译 SQL。计时测量的是游标执行时间，不包括连接池等待、编译、后续取数、水合和提交。
关于与旧 QueryExecutor 日志器相比的格式变化，参见[日志字段契约](../features/01-database-setup.md#sql-日志)。

集中式的执行观测遵循 [Django 查询观测](https://docs.djangoproject.com/en/5.2/topics/db/instrumentation/)的目的，
使用底层的 [SQLAlchemy 方言与连接事件](https://docs.sqlalchemy.org/en/20/core/events.html)实现，
因此每个 ORM 入口点共享同一条记录路径。

## 数据库事件注册

`db.on(name, **options)` 在所选数据库的 `engine.sync_engine` 上注册原生的 SQLAlchemy Engine、Pool 和
Dialect 监听器。装饰器保留监听器的标识和签名，转发诸如 `named` 和 `retval` 之类的选项，
并支持通过 `sqlalchemy.event.remove` 移除。未知名称和无效选项保留 SQLAlchemy 的校验。
监听器的作用域限定为一个引擎；请在打开需要被观察的连接之前注册。

即使使用异步驱动，SQLAlchemy 事件也是同步运行的。协程函数、异步可调用对象和异步生成器函数在注册时会被拒绝；
普通的同步监听器不得返回可等待对象。原生的连接和连接池回调参数会被透传，包括 SQLAlchemy 2.x
连接池重置的第三个 `reset_state` 参数。监听器异常遵循 SQLAlchemy 的事件规则，与 SQL 日志器的处理器错误隔离无关。

先前宣传的 `before_commit`、`after_commit`、`before_rollback` 和 `after_rollback` 名称不属于 Engine 事件，
现在会产生可操作的错误。`commit` 和 `rollback` 在驱动完成之前拦截尝试；它们无法确认成功。
对于事务成功之后的副作用，请使用 `await session.on_commit(callback)`。测试验证了事件/驱动/回调的顺序，
以及当事件监听器或驱动提交任一失败时回调被抑制。

参见[事件使用指南](../features/01-database-setup.md#数据库事件)和
[SQLAlchemy 的异步事件契约](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-events-with-the-asyncio-extension)。

## 模式迁移

模型或抽象基类上显式的 `__registry__ = ModelRegistry(...)` 会被尊重并继承。此前元类会悄悄地用共享注册表替换它，
导致应用程序的表泄漏到错误的迁移元数据中。未提供显式注册表时，默认的共享注册表仍然可用。

可选的 `migrations` extra 会安装 Alembic。[可运行示例](../../examples/migrations/README.md)使用异步环境、
隔离的注册表、归属过滤器和专用的版本表。两个历史修订演示了模式创建和必填字段回填，
包括支持离线 SQL 的 SQLite 批处理操作。它同时支持 CLI 和通过 `run_sync()` 由调用方提供的连接。

`tests/integration/test_migrations.py` 检查带数据的升级、降级、生成的修订、归属过滤、真实的默认值变更、
ORM 写入和离线 SQL。SQLite/MySQL 的 Identity 差异会被过滤，而不会抑制实际的服务器默认值变更。
Alembic 1.16.5 和锁文件中的版本都在本地 SQLite 上进行了测试；锁文件版本还在 CI 中于 PostgreSQL 和 MySQL 上运行。

## 保留索引定义

索引去重比较有序的 SQL 表达式、它们的键、字面值、唯一性和方言选项。颠倒复合列顺序、更改函数、
排序方向或排序规则，或使用不同的访问方法、操作符类、包含列或前缀长度，都必须保留为独立的索引。
表达式键很重要，因为 PostgreSQL 按键（包括标签）选择操作符类。完整唯一索引只替换具有相同表达式和选项的普通索引；
部分索引绝不替换完整索引。

条件 DDL 索引在模型注册期间得以保留，而不会执行回调。没有通用编译器的自定义表达式同样被保留，
字面值无法渲染的方言谓词（例如 JSON 值）被视为不同的索引，而不会导致模型定义失败。
等价的无条件定义仍会确定性地去重，并优先保留显式名称：当一列同时声明 `index=True` 和一个显式命名的 `Index` 时，
保留显式名称。此前是生成的 `idx_<table>_<column>` 名称胜出，因此已有数据库需要参照迁移指南中的迁移说明。
该流程此前按排序后的列名比较，可能会悄悄移除函数式唯一性约束。

这遵循 [SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/constraints.html#indexes) 与
[Django](https://docs.djangoproject.com/en/5.2/ref/models/indexes/) 所记录的表达式和排序语义，
以及 [PostgreSQL 的多列索引行为](https://www.postgresql.org/docs/current/indexes-multicolumn.html)。
单元测试覆盖定义同一性和保守保留；集成测试在全部三种数据库上检查实际索引、强制函数式唯一性、
执行 ORM 查询并删除/重建索引。已有模式可能需要一次
[恢复缺失索引的迁移](../features/09-migrations.md#恢复先前被丢弃的索引)。

## 可移植的生成模式名称

SQLObjects 将其生成的 CHECK、UNIQUE、外键和索引名称限制在 63 个 UTF-8 字节以内，短名称保持不变，
长名称则添加一个可读的前缀和一个稳定的 SHA-256 后缀。这同时处理了复合键和多字节标识符，
而不依赖服务器截断。生成名称的冲突使用约束/索引定义来选择不同的名称。
显式名称以及 SQLAlchemy 命名约定已分配的名称保持其现有规则。字段/辅助函数索引共享同一条命名路径；
去重时显式索引名称优先。部分索引的比较包含绑定值。

[SQLAlchemy 的确定性截断](https://docs.sqlalchemy.org/en/20/core/constraints.html#truncation-of-long-names)
为这一方法提供了参考。SQLObjects 依据 [PostgreSQL 的字节限制](https://www.postgresql.org/docs/current/sql-syntax-lexical.html#SQL-SYNTAX-IDENTIFIERS)
来限制元数据名称本身，因此得到的物理名称在所有受支持的后端上保持一致。
测试涵盖真实的 DDL、反射、约束强制执行、删除/重建以及 Alembic 比较，包括 Unicode 名称和长复合外键。

已有的过长/冲突名称需要一次经过审查的迁移，或用显式名称固定当前的数据库标识符。
CHECK 变更没有被 Alembic 自动生成完全覆盖。参见[迁移指南](../features/09-migrations.md#生成的模式名称的变更)。
表/列名称以及显式命名对象之间的数据库范围冲突仍由应用程序负责。

## 验证与剩余工作

CI 运行 SQLite 单元/集成套件、三种数据库上的性能工作负载、跨数据库契约套件以及额外的 PostgreSQL 集成测试。
打标签发布依赖这些检查。一些较旧的集成模型仍包含无效的 PostgreSQL 索引 DDL，已从跨数据库契约作业中排除。
性能夹具只创建它们自己需要的表。

[性能套件](../../tests/performance/README.md)在 JUnit 报告中记录耗时、客户端 CPU 时间、RSS 增量和执行的语句。
固定的时间比率和依赖机器的内存/CPU 限制已替换为结果、查询计数和对象生命周期断言。
并发工作者拥有独立的会话并读取已提交的夹具；任务组在拆除之前完成。SQLite 使用指向临时文件的独立连接，
100 KiB 文本夹具在 MySQL 上使用 LONGTEXT。完整/延迟对比验证投影和已加载状态；
大数据集夹具不再为每一行保留第二份水合副本。

2026-10-08 的本地验证使用 Python 3.12、SQLAlchemy 2.0.44 和 Alembic 1.20.0：

| 数据库 | 范围 | 结果 |
| --- | --- | --- |
| SQLite | 单元、集成和性能套件 | 856 通过；一个行锁测试被跳过，因为 SQLite 没有 SELECT FOR UPDATE。 |
| PostgreSQL 16 | 契约、提交回调、查询日志、迁移、DISTINCT、信号契约、数据库事件、动态关系、包含分组输入的聚合、模式命名、索引定义、CRUD、关系、延迟字段、批量结果、级联和信号 | 389 通过。 |
| MySQL 8.4 | 契约、提交回调、查询日志、迁移、DISTINCT、信号契约、数据库事件和动态关系、包含分组输入的聚合、模式命名和索引定义，使用 aiomysql 及其 RSA 认证 extra | 253 通过；一个 executemany RETURNING 测试被跳过，因为该后端不支持它。 |

66 个性能工作负载在 SQLite、PostgreSQL 16 和 MySQL 8.4 上全部通过，每个数据库导出了 101 项测量和环境元数据。
上述 SQLite 总数包含这些工作负载。修复之前，旧的 SQLite 性能套件在本地基线运行中产生了六个失败和四个拆除错误。

10 个迁移集成测试在 SQLite 上使用 Alembic 1.16.5 也全部通过。

Ruff 的 lint 和格式化检查通过。Pyright 报告零错误以及三个既有的不必要忽略警告。
SQLite 不再发出 DISTINCT ON 方言警告。工作流定义已在本地检查；托管 CI 的结果将在变更推送后可用。

ORM 评审带来的后续工作包括使用类生产工作负载的持续性能基线、分批数据迁移工具以及更广泛的驱动/版本覆盖。
当前的性能测量提供的是用于比较的观察结果，而非普适的性能保证。

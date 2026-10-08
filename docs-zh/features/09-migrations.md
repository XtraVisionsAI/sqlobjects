# 使用 Alembic 进行模式迁移

SQLObjects 的注册表继承自 SQLAlchemy `MetaData`，因此 Alembic 可以直接将其与数据库进行比较。
请使用迁移来演进已有的模式；`create_tables()` 只会创建缺失的表，不会升级已存在的表。

## 安装与可运行示例

对于应用程序，请安装可选的迁移依赖及其异步驱动：

```bash
pip install 'sqlobjects[migrations]' asyncpg
```

SQLite 请改用 `aiosqlite`，MySQL 请改用 `aiomysql[rsa]`。核心 ORM 不依赖 Alembic。
仓库的测试依赖组包含这三种驱动以及 Alembic。

完整的[示例](../../examples/migrations/README.md)包含 `alembic.ini`、一个异步的 `env.py`、
一个修订模板、模型以及两个历史修订。在仓库根目录下执行：

```bash
uv sync --group test
uv run --no-sync alembic -c examples/migrations/alembic.ini upgrade head
uv run --no-sync alembic -c examples/migrations/alembic.ini check
```

这会使用示例目录中的本地 SQLite 文件。设置 `SQLOBJECTS_MIGRATION_URL` 可选择另一个异步数据库 URL。
环境直接读取该值，保留经过百分号编码的凭据，而不经过 INI 插值。即使从其他目录通过绝对的 `-c` 路径
调用 CLI，配置与模型导入也能正常工作。将示例复制到应用程序时，请根据该项目更新模型导入、
`prepend_sys_path`、表归属过滤器以及版本表名称。

## 隔离应用程序的元数据

在创建具体模型之前，先声明一个显式的注册表：

```python
from sqlobjects.metadata import ModelRegistry
from sqlobjects.model import ObjectModel

class AppModel(ObjectModel):
    __abstract__ = True
    __registry__ = ModelRegistry(
        naming_convention={
            "pk": "pk_%(table_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        }
    )

# 所有具体的应用程序模型都继承 AppModel。
target_metadata = AppModel.__registry__
```

显式的 `__registry__` 必须是一个 `ModelRegistry`。子类会继承这个确切的注册表，除非它们显式覆盖。
没有显式注册表的模型保持共享的默认行为。在为 Alembic 赋值 `target_metadata` 之前，
请先导入所有模型模块；注册表只包含已经导入的模型。

仅隔离元数据并不能限制 Alembic 反射哪些已有的数据库表。示例中的 `include_name` 过滤器
拥有 `migration_` 表前缀的归属权。这样既排除了其他应用程序的表，又仍能检测到先前受管理的表被删除。
请为你的应用程序选择一条稳定的归属规则；若仅按当前模型名称过滤，将会掩盖表的删除。
各自独立的迁移历史还需要不同的版本表或不同的数据库。

## 生成并应用模式变更

首先将开发数据库升级到当前修订。编辑模型后执行：

```bash
uv run --no-sync alembic -c examples/migrations/alembic.ini revision --autogenerate -m "add account field"
# 检查并编辑生成的修订。
uv run --no-sync alembic -c examples/migrations/alembic.ini upgrade head
uv run --no-sync alembic -c examples/migrations/alembic.ini check
```

当模式差异会产生迁移操作时，`check` 以非零状态退出。它要求数据库处于当前修订的 head。
自动生成比较的是模式，而不是 ORM 验证、信号或 Python 默认值。列/表的重命名可能表现为
删除/新增操作，需要手工修正。自定义数据库类型、视图、触发器以及数据转换也可能需要手写操作。
参见 [Alembic 自动生成的局限](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#what-does-autogenerate-detect-and-what-does-it-not-detect)。

示例会比较类型和服务器默认值。其修订重写器只在不支持 SQL 标准 Identity 的方言上移除
Identity 变更：SQLite 和 MySQL 使用它们自己的整数自增行为。PostgreSQL 的 Identity 变更
和普通的服务器默认值变更仍参与比较。请针对你的部署方言生成并审查修订。

## 恢复先前被丢弃的索引

早期的索引去重按排序后的列名进行比较。它可能丢弃一个列顺序相反的复合索引、一个表达式索引
（包括唯一表达式索引），或一个与同列唯一索引仅在方言选项上不同的普通索引。这些定义现在会保留在模型元数据中。

更新元数据不会为已有的表添加缺失的索引。请检查数据库中实际的索引定义，并审查一份迁移来创建
所有缺失的索引。表达式索引的反射和自动生成支持因方言而异；必要时请编写显式的 `create_index` 操作。
在添加被恢复的唯一表达式索引之前，请检查现有行是否与该表达式存在冲突。
参见[索引定义](02-model-definition.md#索引定义与去重)。

## 生成的模式名称的变更

SQLObjects 现在将其自动生成的约束和索引名称限制在 63 个 UTF-8 字节以内。过长的名称和
生成名称之间的冲突会获得一个稳定的哈希后缀；显式名称以及 SQLAlchemy 命名约定已分配的名称保持不变。
参见[自动模式名称](02-model-definition.md#自动约束和索引名称)。

普通列、复合唯一约束、外键和 CHECK 约束的短生成名称没有变化。有两种情况会改变：当一列同时声明了
`index=True`（或 `unique=True`）和一个作用于同一表达式的显式命名 `Index` 时，去重现在保留显式名称，
而不是生成的 `idx_<table>_<column>`；当多个生成名称发生冲突时（例如同一列上的两个未命名 CHECK），
冲突中的每个成员都会获得哈希后缀。Alembic 会将第一种情况报告为索引的删除/创建。

已有的数据库可能带有旧的完整名称、被服务器截断的名称或被 SQLAlchemy 缩短的索引名。
在生成修订之前请先检查部署数据库。若要保留已有对象，请在模型配置中用其物理名称显式命名。
若要采用新名称，请编写适用于部署方言的重命名或删除/创建操作；SQLite 的约束变更可能需要批处理模式。
Alembic 可能把索引/唯一约束的名称变更报告为删除/创建，而 CHECK 名称的变更可能根本不会出现在自动生成中。
请审查修订，而不要把 `check` 的空结果当作所有名称一致的证明。

## 使用历史定义迁移现有数据

第二个修订演示了如何向已有数据的表添加必填字段：

1. 将 `display_name` 添加为可空列。
2. 使用 Core UPDATE 从现有的 email 列回填该字段。
3. 将其改为 NOT NULL 并创建索引。

修订文件使用本地的 SQLAlchemy 表/列定义。它们不导入当前的应用程序模型、不调用 `save()`，
也不会触发当前的验证/信号。这样即使模型 API 发生变化，旧修订仍然可运行。Python 默认值不会
回填已存储的行；请编写显式的数据操作或服务器默认值。

示例对一个小表使用单条 UPDATE。大规模部署应将模式扩展、分批回填和约束强制执行分开进行，
并协调应用程序的并发写入。SQLite 的批处理变更可能会重建表；MySQL 的 DDL 可能隐式提交，
因此失败的迁移并不保证撤销先前的步骤。降级到 `0001_accounts` 会保留 email/id 但丢失显示名称；
降级到 `base` 会移除账户表。

## 复用已有的异步连接

若要由应用程序控制迁移执行，可将 `AsyncConnection.run_sync()` 提供的同步连接通过 Alembic 的配置传入：

```python
from alembic import command
from alembic.config import Config
from sqlobjects.database import get_database

def upgrade(connection):
    config = Config("examples/migrations/alembic.ini")
    config.attributes["connection"] = connection
    command.upgrade(config, "head")

async with get_database().engine.begin() as connection:
    await connection.run_sync(upgrade)
```

示例环境借用该连接，但不会关闭或释放它。若未提供连接，CLI 会使用 `NullPool` 创建一个异步引擎，
通过 `run_sync()` 运行迁移，并在 `finally` 中释放引擎。请避免在运行中的事件循环内不提供连接就直接
调用同步的 Alembic 命令；CLI 路径使用 `asyncio.run()`。请在应用程序工作进程启动之前运行一个经过协调的
迁移作业。对于多数据库，请分别迁移每个别名；这不是分布式事务。

这遵循 Alembic 文档中的
[asyncio 与连接共享配方](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic)。

## 离线 SQL

```bash
uv run --no-sync alembic -c examples/migrations/alembic.ini upgrade head --sql
uv run --no-sync alembic -c examples/migrations/alembic.ini downgrade 0002_display_names:base --sql
```

离线模式在不连接数据库的情况下编译已有的修订。它无法发现模型与数据库之间的差异。
SQLite 批处理模式通常需要反射；本示例为每个修订提供了其历史的 `copy_from` 表，
以同样支持离线 SQL。请保持这些定义与该修订时的模式一致。生成的 SQL 面向配置的数据库方言
和修订范围；它不是可在已升级数据库上重放的幂等脚本。

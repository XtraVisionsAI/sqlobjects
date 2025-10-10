"""统一的测试数据库配置管理"""

import os
from typing import Any
from urllib.parse import urlparse


class TestDatabaseConfig:
    """统一的测试数据库配置管理"""

    DATABASES = {
        "sqlite": {
            "url": "sqlite+aiosqlite:///:memory:",
            "driver": None,
            "pool_config": {},
        },
        "postgresql": {
            "url": "postgresql+asyncpg://test:test@localhost/tests",
            "driver": "asyncpg",
            "env_var": "POSTGRESQL_TEST_URL",
            "pool_config": {"pool_size": 10, "max_overflow": 0, "pool_pre_ping": True},
        },
        "mysql": {
            "url": "mysql+asyncmy://test:test@localhost/tests",
            "driver": "asyncmy",
            "env_var": "MYSQL_TEST_URL",
            "pool_config": {},
        },
    }

    @classmethod
    def get_config(cls, db_type: str) -> dict[str, Any]:
        """获取完整的数据库配置"""
        config = cls.DATABASES.get(db_type)
        if not config:
            raise ValueError(f"Unsupported database type: {db_type}")

        # 使用环境变量覆盖默认URL
        env_var = config.get("env_var")
        if env_var and os.getenv(env_var):
            config = config.copy()
            config["url"] = os.getenv(env_var)

        return config


async def test_database_connection(db_type: str, url: str) -> bool:
    """测试数据库连接"""
    if db_type == "postgresql":
        import asyncpg  # type: ignore[reportMissingImports]

        # 转换 SQLAlchemy URL 为 asyncpg URL
        native_url = url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(native_url)
        await conn.close()
    elif db_type == "mysql":
        import asyncmy  # type: ignore[reportMissingImports]

        # 解析 SQLAlchemy URL
        native_url = url.replace("mysql+asyncmy://", "mysql://")
        parsed = urlparse(native_url)
        conn = await asyncmy.connect(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username or "test",
            password=parsed.password or "test",
            db=parsed.path.lstrip("/") or "tests",
        )
        await conn.ensure_closed()
    return True


async def check_database_connection(db_type: str) -> bool:
    """统一的数据库连接检查"""
    if db_type == "sqlite":
        return True

    try:
        config = TestDatabaseConfig.get_config(db_type)

        # 检查驱动
        driver = config.get("driver")
        if driver:
            __import__(driver)

        # 测试连接
        return await test_database_connection(db_type, config["url"])

    except ImportError:
        print(f"❌ {config.get('driver')} not installed for {db_type} testing")  # type: ignore[reportPossiblyUnboundVariable]
        return False
    except Exception as e:
        print(f"❌ {db_type.upper()} connection failed: {e}")
        return False

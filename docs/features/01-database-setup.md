# Database Setup

> 📝 This document is based on the Chinese version. For the latest Chinese version, see [docs-zh/features/01-database-setup.md](../../docs-zh/features/01-database-setup.md)

SQLObjects provides flexible database configuration and connection management with support for multiple databases, connection pooling, and async operations.

## Quick Start

### Single Database Setup

```python
from sqlobjects.database import init_db, create_tables
from sqlobjects.model import ObjectModel

# Initialize database connection
await init_db("sqlite+aiosqlite:///app.db")

# Create tables for all models
await create_tables(ObjectModel)
```

### Multi-Database Setup

```python
from sqlobjects.database import init_dbs

# Configure multiple databases
databases = await init_dbs({
    "main": {"url": "postgresql+asyncpg://user:pass@localhost/main"},
    "analytics": {"url": "sqlite+aiosqlite:///analytics.db"},
    "echo": False  # Disable SQL logging in production
}, default="main")
```

## Database Configuration

### Connection URLs

SQLObjects supports all SQLAlchemy-compatible database URLs:

```python
# PostgreSQL
await init_db("postgresql+asyncpg://user:password@localhost/dbname")

# MySQL
await init_db("mysql+aiomysql://user:password@localhost/dbname")

# SQLite
await init_db("sqlite+aiosqlite:///path/to/database.db")

# In-memory SQLite (for testing)
await init_db("sqlite+aiosqlite:///:memory:")
```

### Connection Pool Configuration

```python
from sqlobjects.database import init_db

await init_db(
    "postgresql+asyncpg://user:pass@localhost/db",
    pool_size=20,           # Base connection pool size
    max_overflow=30,        # Additional connections during peak load
    pool_timeout=30,        # Max wait time for connection (seconds)
    pool_recycle=3600,      # Recycle connections every hour
    pool_pre_ping=True,     # Verify connections before use
    echo=False              # Disable SQL logging in production
)
```

## Session Management

### Context Managers

```python
from sqlobjects.session import ctx_session, ctx_sessions

# Single database session
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="alice")
    posts = await user.posts.using(session).all()
    # Automatic commit on success, rollback on exception

# Multi-database sessions
async with ctx_sessions("main", "analytics") as sessions:
    user = await User.objects.using(sessions["main"]).create(username="bob")
    await Log.objects.using(sessions["analytics"]).create(message="User created")
    # Coordinated transaction across databases
```

### Session Binding

```python
# Bind operations to specific sessions
user = await User.objects.using(session).get(User.id == 1)
await user.using(session).save()

# Chain operations with session binding
users = await User.objects.using(session).filter(
    User.is_active == True
).order_by("-created_at").all()
```

## Database Management

### Table Creation

```python
from sqlobjects.database import create_tables, drop_tables
from sqlobjects.model import ObjectModel

# Create all tables
await create_tables(ObjectModel)

# Create specific model tables
await create_tables([User, Post, Comment])

# Drop tables (use with caution)
await drop_tables(ObjectModel)
```

### Database Health Checks

```python
from sqlobjects.database import check_db_health, get_db_info

# Check database connectivity
is_healthy = await check_db_health()
if not is_healthy:
    print("Database connection issues detected")

# Get database information
db_info = await get_db_info()
print(f"Database: {db_info['dialect']} v{db_info['version']}")
```

## Advanced Configuration

### Environment-Based Configuration

```python
import os
from sqlobjects.database import init_db

# Production configuration
if os.getenv("ENVIRONMENT") == "production":
    await init_db(
        os.getenv("DATABASE_URL"),
        pool_size=20,
        max_overflow=30,
        pool_recycle=3600,
        echo=False
    )
else:
    # Development configuration
    await init_db(
        "sqlite+aiosqlite:///dev.db",
        pool_size=5,
        echo=True  # Enable SQL logging for debugging
    )
```

### Database Routing

```python
class User(ObjectModel):
    class Config:
        database = "main"  # Use specific database

class AnalyticsLog(ObjectModel):
    class Config:
        database = "analytics"  # Route to analytics database
```

## Best Practices

### Connection Management

1. **Initialize Early**: Set up database connections during application startup
2. **Use Context Managers**: Always use `ctx_session()` for transaction management
3. **Pool Configuration**: Tune connection pool settings based on your application load
4. **Health Monitoring**: Implement regular database health checks

### Performance Optimization

```python
# Optimize for read-heavy workloads
await init_db(
    database_url,
    pool_size=30,        # Larger pool for concurrent reads
    max_overflow=50,
    pool_recycle=7200,   # Longer recycle time for stable connections
    pool_pre_ping=True   # Ensure connection validity
)

# Optimize for write-heavy workloads
await init_db(
    database_url,
    pool_size=10,        # Smaller pool to avoid lock contention
    max_overflow=20,
    pool_timeout=60,     # Longer timeout for write operations
    pool_recycle=1800    # Shorter recycle for fresh connections
)
```

### Error Handling

```python
from sqlobjects.exceptions import DatabaseError, ConnectionError

try:
    await init_db("postgresql://invalid:url@localhost/db")
except ConnectionError as e:
    print(f"Failed to connect to database: {e}")
    # Implement fallback or retry logic

try:
    async with ctx_session() as session:
        # Database operations
        pass
except DatabaseError as e:
    print(f"Database operation failed: {e}")
    # Handle database-specific errors
```

## Testing Setup

### Test Database Configuration

```python
import pytest
from sqlobjects.database import init_db, create_tables, close_db
from sqlobjects.model import ObjectModel

@pytest.fixture(scope="session")
async def test_db():
    """Setup test database for the entire test session"""
    await init_db("sqlite+aiosqlite:///:memory:")
    await create_tables(ObjectModel)
    yield
    await close_db()

@pytest.fixture
async def clean_db(test_db):
    """Clean database state between tests"""
    async with ctx_session() as session:
        # Clean all tables
        for table in reversed(ObjectModel.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()
```

### Isolated Test Transactions

```python
@pytest.fixture
async def test_session():
    """Provide isolated session for each test"""
    async with ctx_session() as session:
        yield session
        # Transaction automatically rolled back after test

async def test_user_creation(test_session):
    user = await User.objects.using(test_session).create(username="test")
    assert user.username == "test"
    # Changes rolled back after test
```
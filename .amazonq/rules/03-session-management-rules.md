# Session Management and Transaction Architecture

## Session Management Design Patterns

### Core Session Interfaces

#### `using()` Method Pattern
**Universal session binding interface across all operations**
```python
# Model operations
user = await User.objects.using(session).create(username="john")
await user.using(session).save()

# Query operations  
users = await User.objects.using(session).filter(User.is_active == True).all()

# Bulk operations
await User.objects.using(session).bulk_create(user_data)
```

#### ModelProxy Pattern
**Transparent session management for detached instances**
- Automatically attaches detached instances to appropriate sessions
- Handles session binding for save(), delete(), refresh() operations
- Maintains session context across method calls
- Provides seamless experience for detached instance operations

### Session Context Managers

#### Single Database Sessions
```python
# ctx_session() for single database operations
async with ctx_session() as session:
    user = await User.objects.using(session).create(username="alice")
    posts = await user.posts.using(session).all()
    # Automatic commit on success, rollback on exception
```

#### Multiple Database Sessions
```python
# ctx_sessions() for multi-database operations
async with ctx_sessions("main", "analytics") as sessions:
    user = await User.objects.using(sessions["main"]).create(username="bob")
    await Log.objects.using(sessions["analytics"]).create(message="User created")
    # Coordinated transaction across databases
```

## Transaction Management Patterns

### Three Transaction Modes

#### 1. ContextVar Inheritance (Unified Transactions)
**Use Case**: All operations should be in the same transaction
```python
async with ctx_session() as session:
    # All async tasks inherit the same session context
    tasks = [asyncio.create_task(process_user(user_id)) for user_id in user_ids]
    await asyncio.gather(*tasks)
    # All operations committed together
```

#### 2. Independent Context (Fault Isolation)
**Use Case**: Operations should be isolated from each other
```python
# Each task gets independent transaction context
tasks = [
    asyncio.create_task(process_user(user_id), context=contextvars.copy_context())
    for user_id in user_ids
]
await asyncio.gather(*tasks, return_exceptions=True)
# Failures in one task don't affect others
```

#### 3. Explicit Session Passing (Full Control)
**Use Case**: Complex transaction logic with explicit control
```python
async with ctx_session() as session:
    tasks = [asyncio.create_task(process_user(user_id, session)) for user_id in user_ids]
    await asyncio.gather(*tasks)
    # Explicit session management with full control
```

## Database Connection Architecture

### DatabaseManager Design
**Singleton pattern for multi-database management**
- Centralized database registration and configuration
- Connection pool management and health monitoring
- Automatic failover and load balancing support
- Named database routing and default database handling

### SessionContextManager Implementation
**Factory pattern for session creation**
- Session factory creation and configuration
- Context manager lifecycle management
- Transaction boundary control and cleanup
- Error handling and rollback strategies

### Auto-Default Mechanism
**Automatic database failover system**
```python
# Graceful shutdown with automatic failover
await close_db("primary", auto_default=True)
# Automatically switches default to next available database

# Health-based failover
if not await check_db_health("primary"):
    await switch_default_db("backup")
```

## Design Decision Rationale

### Why using() Method Pattern?
**Alternative Considered**: Parameter passing (session=session)
**Decision**: using() method for consistency
**Rationale**:
- Consistent interface across all operation types
- Chainable with other query methods
- Clear indication of session binding
- Supports both bound and unbound operations

### Why ModelProxy vs Direct Session Binding?
**Alternative Considered**: Always require explicit session
**Decision**: ModelProxy for transparent session management
**Rationale**:
- Seamless experience for detached instances
- Reduces boilerplate for simple operations
- Maintains session context across operations
- Backward compatibility with session-less operations

### Why Three Transaction Modes?
**Alternative Considered**: Single transaction model
**Decision**: Multiple patterns for different use cases
**Rationale**:
- ContextVar inheritance for unified transactions
- Independent contexts for fault tolerance
- Explicit passing for complex scenarios
- Flexibility without complexity for simple cases

## Session Lifecycle Management

### Session Creation and Configuration
```python
# Session factory configuration
session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)

# Context manager integration
async with ctx_session() as session:
    # Session automatically configured and managed
    pass
```

### Transaction Boundaries
- **Automatic Commit**: Success path commits automatically
- **Automatic Rollback**: Exception path rolls back automatically
- **Manual Control**: Available when needed for complex scenarios
- **Nested Transactions**: Support for savepoints and nested contexts

### Connection Pool Integration
```python
# Pool configuration for optimal performance
engine = create_async_engine(
    database_url,
    pool_size=20,           # Base connection pool
    max_overflow=30,        # Burst capacity
    pool_timeout=30,        # Connection wait timeout
    pool_recycle=3600,      # Connection refresh interval
    pool_pre_ping=True      # Connection health checks
)
```

## Error Handling and Recovery

### Session Error Recovery
- **Connection Errors**: Automatic retry with exponential backoff
- **Transaction Conflicts**: Deadlock detection and retry logic
- **Pool Exhaustion**: Graceful degradation and queuing
- **Database Unavailability**: Failover to backup databases

### Transaction Rollback Strategies
- **Automatic Rollback**: All exceptions trigger rollback
- **Partial Rollback**: Savepoint-based partial rollback
- **Manual Recovery**: Explicit rollback and retry logic
- **Error Propagation**: Clean error propagation to application layer

## Performance Optimization

### Session Reuse Patterns
- **Context Inheritance**: Reuse sessions across async tasks
- **Connection Pooling**: Efficient connection reuse
- **Prepared Statements**: Statement caching and reuse
- **Batch Operations**: Session-aware bulk processing

### Memory Management
- **Session Cleanup**: Automatic session cleanup and resource release
- **Object Expiration**: Configurable object expiration policies
- **Memory Monitoring**: Session memory usage tracking
- **Garbage Collection**: Proactive cleanup of unused sessions

## Integration Guidelines

### Framework Integration
- **FastAPI**: Integration with dependency injection
- **Django**: Compatibility with Django's transaction management
- **Flask**: Support for Flask's application context
- **Standalone**: Direct usage without framework dependencies

### Testing Integration
```python
# Test session management
@pytest.fixture
async def test_session():
    async with ctx_session() as session:
        yield session
        # Automatic cleanup after test

# Isolated test transactions
async def test_user_creation(test_session):
    user = await User.objects.using(test_session).create(username="test")
    assert user.username == "test"
    # Transaction rolled back after test
```
# Core Architecture

> 📝 This document is based on the Chinese version. For the latest Chinese version, see [docs-zh/design/01-core-architecture.md](../../docs-zh/design/01-core-architecture.md)

SQLObjects is built on a solid architectural foundation that prioritizes performance, type safety, and developer experience while maintaining the familiar Django ORM API.

## Architecture Overview

### Foundation Stack

```
┌─────────────────────────────────────────┐
│           SQLObjects API Layer          │
├─────────────────────────────────────────┤
│     Model System    │   Query System    │
├─────────────────────┼───────────────────┤
│   Field System      │   Session Mgmt    │
├─────────────────────┼───────────────────┤
│   Signal System     │   Cache Layer     │
├─────────────────────────────────────────┤
│           SQLAlchemy Core               │
├─────────────────────────────────────────┤
│        Database Drivers (Async)         │
└─────────────────────────────────────────┘
```

### Core Design Principles

1. **Performance First**: Built on SQLAlchemy Core for maximum performance
2. **Type Safety**: Comprehensive type annotations and runtime validation
3. **Async Native**: Designed for async/await from the ground up
4. **Django Familiarity**: Familiar API for Django developers
5. **Extensibility**: Clean extension points and plugin architecture

## Module Architecture

### Core Modules

#### Model System (`model.py`)
- **ObjectModel**: Base class for all models with metaclass magic
- **Field Processing**: Automatic field discovery and table generation
- **Configuration**: Model configuration and metadata processing
- **State Management**: Instance state tracking and dirty field detection

```python
# Model system responsibilities
class ObjectModel:
    # Metaclass processing for automatic table generation
    # Field discovery and type processing
    # Configuration parsing and application
    # State management and change tracking
```

#### Field System (`fields/`)
- **Type Registry**: Centralized mapping of Python types to SQLAlchemy types
- **Field Definitions**: Type-safe field classes with parameter validation
- **Shortcuts**: Convenience functions for common field types
- **Validation**: Field-level validation integration

```python
# Field system architecture
fields/
├── core.py          # Core field classes and type registry
├── shortcuts.py     # StringColumn, IntegerColumn, etc.
├── functions.py     # column(), foreign_key(), etc.
├── types/           # Specialized field types
└── relations/       # Relationship field definitions
```

#### Query System (`queries/`, `queryset.py`)
- **QuerySet**: Chainable query building with lazy evaluation
- **QueryBuilder**: Immutable query construction and SQL generation
- **Executor**: Unified query execution and result processing
- **Cache**: Query result caching with performance monitoring

```python
# Query system flow
QuerySet → QueryBuilder → SQLAlchemy Query → Database → Results
    ↓           ↓              ↓              ↓         ↓
  Chaining   SQL Build    Execution      Raw Data   Objects
```

#### Session Management (`session.py`, `database/`)
- **Context Managers**: `ctx_session()` and `ctx_sessions()` for transaction control
- **Database Manager**: Multi-database configuration and routing
- **Connection Pooling**: Optimized connection pool management
- **Transaction Control**: Automatic commit/rollback and isolation levels

### Integration Patterns

#### Unified Type System
All components share a common type system for consistency:

```python
# Type registry used across all modules
TypeRegistry = {
    str: ("string", {"length": 255}),
    int: ("integer", {}),
    bool: ("boolean", {}),
    datetime: ("datetime", {}),
    # ... comprehensive type mapping
}
```

#### Session Integration
All operations support session binding through the `using()` pattern:

```python
# Consistent session binding across all operations
user = await User.objects.using(session).create(...)
await user.using(session).save()
queryset = User.objects.using(session).filter(...)
```

## Performance Architecture

### SQLAlchemy Core Foundation

**Why Core over ORM?**
- **Better Performance**: Direct SQL generation without ORM overhead
- **Memory Efficiency**: Reduced object creation and memory allocation
- **Async Integration**: Simpler async/await integration
- **Control**: Fine-grained control over SQL generation

### Caching Strategy

```python
# Multi-level caching architecture
┌─────────────────┐
│  Query Cache    │  ← Result caching with FIFO eviction
├─────────────────┤
│  Field Cache    │  ← Field metadata caching with LRU
├─────────────────┤
│  Type Cache     │  ← Type conversion caching
└─────────────────┘
```

### Bulk Operations

High-performance bulk processing through:
- **Batch Processing**: Configurable batch sizes for optimal performance
- **Memory Management**: Streaming processing for large datasets
- **Database Optimization**: Database-specific bulk operation strategies

## Type Safety Architecture

### Comprehensive Type Annotations

```python
# Type safety throughout the system
class User(ObjectModel):
    username: Column[str] = StringColumn(length=50)  # Type-safe field definition
    age: Column[int] = IntegerColumn(nullable=True)

# Type-safe query building
users: list[User] = await User.objects.filter(
    User.age >= 18  # Type-checked field access
).all()
```

### Runtime Validation

- **Field Validation**: Type checking and constraint validation at field level
- **Model Validation**: Business logic validation at model level
- **Query Validation**: Parameter type checking in query building

## Extension Architecture

### Signal System

Comprehensive lifecycle hooks with automatic registration:

```python
class User(ObjectModel):
    # Signals automatically registered through method discovery
    async def before_save(self, context): pass
    async def after_create(self, context): pass
    async def before_delete(self, context): pass
```

### Plugin Points

Well-defined extension points for customization:
- **Custom Field Types**: Extend the field system with new types
- **Query Extensions**: Add custom query methods and operations
- **Validation Extensions**: Custom validators and validation rules
- **Signal Extensions**: Custom signal handlers and processors

### Mixin Architecture

Composition-based extension through mixins:

```python
# Core functionality through mixins
class ObjectModel(
    ModelMixin,      # Complete functionality integration
    SignalMixin,     # Signal processing
    HistoryMixin,    # History tracking
    ModelProcessor   # Metadata processing
):
    pass
```

## Async Architecture

### Native Async Design

Built for async/await from the ground up:
- **Async Context Managers**: Session and transaction management
- **Async Iterators**: Memory-efficient large dataset processing
- **Async Signals**: Non-blocking lifecycle hooks
- **Async Validation**: Asynchronous validation support

### Context Variable Integration

Seamless context propagation for session management:

```python
# Context variables for session inheritance
async with ctx_session() as session:
    # All async tasks inherit the same session context
    tasks = [asyncio.create_task(process_user(user_id)) for user_id in user_ids]
    await asyncio.gather(*tasks)
```

## Database Compatibility

### Multi-Database Support

Unified API across different database systems:
- **PostgreSQL**: Full feature support with advanced capabilities
- **MySQL**: Comprehensive support with dialect-specific optimizations
- **SQLite**: Complete support for development and testing
- **Others**: Extensible support for additional databases

### Database-Specific Optimizations

```python
# Automatic dialect detection and optimization
if session.bind.dialect.name == "postgresql":
    # Use PostgreSQL-specific functions
    result = func.date_trunc("day", User.created_at)
elif session.bind.dialect.name == "mysql":
    # Use MySQL-specific functions
    result = func.date_format(User.created_at, "%Y-%m-%d")
else:
    # Fallback to standard SQL
    result = func.date(User.created_at)
```

## Memory Management

### Efficient Object Creation

- **Lazy Loading**: Defer expensive operations until needed
- **Object Pooling**: Reuse objects where possible
- **Memory Monitoring**: Track memory usage and optimize accordingly
- **Garbage Collection**: Proactive cleanup of unused objects

### State Management

Efficient state tracking without memory leaks:

```python
# StateManager for efficient state storage
class StateManager:
    def __init__(self):
        self._state = {}  # Minimal state storage
    
    def get(self, key, default=None):
        return self._state.get(key, default)
    
    def set(self, key, value):
        self._state[key] = value
```

## Error Handling Architecture

### Comprehensive Exception Hierarchy

```python
SQLObjectsError
├── ValidationError      # Data validation failures
├── DatabaseError       # Database operation failures
├── ConfigurationError  # Configuration issues
├── QueryError          # Query building/execution errors
└── SessionError        # Session management errors
```

### Error Context and Recovery

- **Rich Error Information**: Detailed error context for debugging
- **Recovery Strategies**: Automatic retry and fallback mechanisms
- **Error Propagation**: Clean error propagation through the stack
- **Logging Integration**: Structured logging for error tracking

## Testing Architecture

### Test Organization

```python
tests/
├── unit/           # Component isolation tests
├── integration/    # Component interaction tests
└── performance/    # Performance and benchmarking tests
```

### Test Patterns

- **Behavior Testing**: Focus on observable behavior over implementation
- **Fixture Management**: Reusable test data and database setup
- **Performance Testing**: Automated performance regression detection
- **Cross-Database Testing**: Ensure compatibility across database systems

## Future Architecture Considerations

### Planned Enhancements

- **Window Functions**: Advanced SQL window function support
- **CTE Support**: Common Table Expression integration
- **Advanced Caching**: Sophisticated cache management and invalidation
- **Query Optimization**: Automatic query optimization and analysis

### Extensibility Goals

- **Plugin Ecosystem**: Rich plugin system for community extensions
- **Custom Backends**: Support for non-SQL data stores
- **Advanced Monitoring**: Built-in performance monitoring and profiling
- **Cloud Integration**: Native cloud database service integration

This architecture provides a solid foundation for building high-performance, type-safe database applications while maintaining the familiar Django ORM experience that developers love.
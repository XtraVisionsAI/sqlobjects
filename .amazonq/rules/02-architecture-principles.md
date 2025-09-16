# SQLObjects Architecture Principles

## Core Design Philosophy

### Foundation Technology Stack

- **Built on SQLAlchemy Core** (not ORM) for maximum performance and control
- **Django-style API** for familiar and intuitive developer experience
- **Async-first design** with comprehensive async/await support
- **Type safety** with full type annotations and runtime validation

### Design Priorities

1. **Performance First**: Optimize for database operations and memory usage
2. **Developer Experience**: Intuitive APIs with minimal boilerplate
3. **Type Safety**: Comprehensive type checking and validation
4. **Scalability**: Support for high-concurrency and large datasets

## Module Architecture and Responsibilities

### Core Module Boundaries

#### `base.py` - Model Foundation

- **ObjectModel base class**: Core model functionality and metaclass
- **Configuration system**: ModelConfig parsing and application
- **Metadata processing**: Table generation and schema management
- **Dataclass integration**: Automatic field processing and type handling

#### `fields.py` - Type System

- **Field definitions**: Column types and parameter processing
- **Type registry**: Centralized type mapping and conversion
- **Validation integration**: Field-level validator support
- **Column type classes**: Type-safe field definitions with parameter validation

#### `queries.py` - Query Engine

- **QuerySet implementation**: Chainable query building with comprehensive method coverage
- **ObjectsManager**: Model-level query interface providing shortcuts to all QuerySet methods
- **Bulk operations**: High-performance batch processing
- **Result processing**: Query execution and object instantiation
- **Method Delegation**: ObjectsManager delegates to QuerySet for consistent API

#### `database.py` - Connection Management

- **Database initialization**: Connection setup and configuration
- **Session management**: Context managers and session factories
- **Transaction control**: Commit/rollback and isolation levels
- **Multi-database support**: Named databases and routing

### Cross-Module Integration Patterns

#### Unified Type System

- **TypeRegistry**: Central type mapping with LRU caching
- **Parameter extraction**: Automatic SQLAlchemy parameter conversion
- **Type validation**: Runtime type checking and coercion

#### Session Management Integration

- **using() method pattern**: Consistent session binding across all operations
- **ModelProxy pattern**: Transparent session attachment for detached instances
- **Context propagation**: Automatic session inheritance in async contexts

## Architecture Evolution Principles

### Backward Compatibility

- **API Stability**: Public interfaces remain stable across minor versions
- **Deprecation Process**: 2-version deprecation cycle with clear migration paths
- **Migration Tools**: Automated tools for major version upgrades

### Extension Strategy

- **Plugin Architecture**: New functionality through mixins and extensions
- **Hook Points**: Well-defined extension points for customization
- **Composition over Inheritance**: Favor mixins over deep inheritance hierarchies
- **Interface Segregation**: Small, focused interfaces over monolithic ones

## Key Design Decisions and Rationale

### SQLAlchemy Core vs ORM

**Decision**: Use SQLAlchemy Core as foundation
**Rationale**:

- Better performance for bulk operations
- More control over SQL generation
- Simpler async integration
- Reduced memory overhead

### Django-style API Design

**Decision**: Adopt Django ORM-like interface
**Rationale**:

- Familiar to many Python developers
- Proven patterns for common operations
- Intuitive query building and chaining
- Clear separation of concerns

### Async-First Architecture

**Decision**: Design all APIs as async-first
**Rationale**:

- Modern Python applications are increasingly async
- Better resource utilization for I/O-bound operations
- Consistent programming model
- Future-proof architecture

### Multi-Database Compatibility Strategy

**Decision**: Database dialect detection with function mapping
**Rationale**:

- Optimal performance using database-native functions
- Consistent Python API across all databases
- Graceful fallback for unsupported databases
- Type safety with unified return types

### Type Safety Implementation

**Decision**: Comprehensive type annotations with runtime validation
**Rationale**:

- Better IDE support and developer experience
- Catch errors at development time
- Self-documenting code
- Integration with modern Python tooling

## Current Version Feature Boundaries

### Implemented Features ✅

- **Expression Syntax**: Full support for User.field and string syntax
- **Basic Cache Control**: no_cache() and basic statistics
- **Bulk Operations**: bulk_create, bulk_update, bulk_delete with batch processing
- **Signal System**: Complete lifecycle hooks with automatic registration
- **Relationship Loading**: select_related and prefetch_related with expression syntax
- **Field System**: Complete type registry with Auto type inference
- **Validation System**: Field-level and model-level validation with custom validators

### Planned Features (TODO.md) 🚧

- **Window Functions**: Planned for v2.0 (func.row_number().over())
- **Advanced Cache Management**: Detailed statistics and management (v2.1)
- **Database Health Checks**: check_db_health(), switch_default_db() (v2.0)
- **CTE Support**: Common Table Expressions (v2.2+)
- **Advanced SQL Functions**: Complex query patterns (v2.1+)

### Not Planned ❌

- **File Validators**: FileValidator, ImageValidator (use external libraries)
- **Complex Monitoring**: Built-in performance monitoring (use external tools)

## Architecture Constraints and Guidelines

### Module Dependencies

- **Circular Dependencies**: Strictly prohibited between core modules
- **Import Hierarchy**: Clear dependency tree with base → fields → queries → database
- **External Dependencies**: Minimize and carefully evaluate all external dependencies
- **Optional Dependencies**: Use optional imports for non-core functionality

### Interface Design

- **Consistency**: Similar operations have similar interfaces across modules
- **Discoverability**: Common operations easily discoverable through IDE completion
- **Flexibility**: Support both simple and advanced use cases
- **Error Handling**: Consistent error types and messages across all modules

### Performance Constraints

- **Memory Efficiency**: Minimize object creation and memory allocation
- **Query Optimization**: Generate efficient SQL for all operations
- **Caching Strategy**: Intelligent caching without memory leaks
- **Bulk Operations**: Always provide high-performance bulk alternatives
- **Database Optimization**: Use database-specific functions for optimal performance
- **Type Conversion**: Minimize overhead in cross-database type conversion
- **Fallback Performance**: Ensure fallback implementations remain performant


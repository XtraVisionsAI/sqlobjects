# SQLObjects Feature Documentation

This directory contains complete feature documentation for SQLObjects, organized by functionality to help users
understand and implement specific capabilities.

## Documentation Structure

### [01. Database Setup](01-database-setup.md)

Learn how to configure and manage database connections, sessions, and transactions.

**Core Topics:**

- Single and multi-database setup
- Connection pooling and configuration
- Session management patterns
- Transaction control
- Database events and lifecycle management

### [02. Model Definition](02-model-definition.md)

Understand how to define models with fields, validation, and configuration.

**Core Topics:**

- Model class definition and table generation
- Field types and parameters with performance optimization
- Field-level and model-level validation
- Code generation control with dataclass integration
- Identity columns and computed columns
- Custom field types and type registration

### [03. Data Querying](03-querying-data.md)

Master the query API for filtering, sorting, and retrieving data.

**Core Topics:**

- Basic and complex filtering with Q objects
- Sorting, pagination, and field selection
- Aggregation and annotation
- Subqueries and complex queries
- Raw SQL integration

### [04. CRUD Operations](04-crud-operations.md)

Learn comprehensive create, read, update, delete operations.

**Core Topics:**

- Individual and bulk operations
- Smart save() with automatic CREATE/UPDATE detection
- Detached instance operations
- Transaction management
- Performance optimization for large datasets

### [05. Relationships](05-relationships.md)

Implement and optimize relationships between models.

**Core Topics:**

- One-to-many, one-to-one, and many-to-many relationships
- Lazy and eager loading strategies
- JOIN optimization and manual joins
- Relationship querying and filtering
- Complex relationship patterns

### [06. Validation and Signals](06-validation-signals.md)

Implement data validation and lifecycle hooks.

**Core Topics:**

- Field-level validation with validators parameter integration
- Custom validation logic and schema validation
- Signal system for database operation hooks
- Smart operation detection and bulk signals
- Error handling and validation strategies

### [07. Performance Optimization](07-performance-optimization.md)

Optimize database operations for high-performance applications.

**Core Topics:**

- Bulk operations and batching
- Field-level performance optimization (lazy loading, active history)
- Query optimization and memory management
- Connection pooling and session patterns
- Performance monitoring and benchmarking
- Best practices and optimization checklist

### [08. Custom Field Types](08-custom-field-types.md)

Extend SQLObjects with custom database-specific field types.

**Core Topics:**

- Type registration and configuration
- Custom comparators for type-specific operations
- PostgreSQL examples (tsvector, pgvector)
- Index creation and performance optimization
- Best practices for custom types
- Type registry API reference

## Getting Started

If you're new to SQLObjects, we recommend following this learning path:

1. **Start with [Database Setup](01-database-setup.md)** - Learn basic configuration
2. **Move to [Model Definition](02-model-definition.md)** - Define your first models
3. **Practice [Data Querying](03-querying-data.md)** - Learn to retrieve data
4. **Master [CRUD Operations](04-crud-operations.md)** - Implement data manipulation
5. **Add [Relationships](05-relationships.md)** - Connect your models
6. **Implement [Validation and Signals](06-validation-signals.md)** - Add business logic
7. **Optimize with [Performance Optimization](07-performance-optimization.md)** - Scale your application
8. **Extend with [Custom Field Types](08-custom-field-types.md)** - Add database-specific types (optional)

## Feature Categories

### Core Features

- **Database Management**: Multi-database support with automatic connection handling
- **Model System**: Django-style models with automatic table generation
- **Query API**: Chainable queries with SQLAlchemy expression support
- **Type Safety**: Complete type annotations and validation

### Model Definition

- **Smart Field Parameters**: Automatic inference of init, repr, compare parameters based on field characteristics
- **Constructor Control**: Field-level model constructor participation control via init parameter
- **from_dict Method**: Intelligent handling of different field types during instance creation

### Advanced Features

- **Smart Operations**: Automatic CREATE/UPDATE detection for save operations
- **Bulk Processing**: High-performance bulk operations for large datasets
- **Signal System**: Comprehensive lifecycle hooks for database operations
- **Field Enhancements**: Field-level performance optimization and code generation control

### CRUD Operations

- **Unified Instance Creation**: ObjectsManager methods use from_dict to ensure consistent instance creation behavior
- **Dirty Field Tracking**: Automatic tracking of field modifications to optimize UPDATE operations
- **Smart Operation Detection**: Automatically determine INSERT vs UPDATE operations

### Performance Features

- **Connection Pooling**: Optimized database connection management
- **Memory Management**: Iterator support and efficient pagination
- **Field-level Optimization**: Lazy loading and active history tracking
- **Query Optimization**: Relationship loading and query analysis tools
- **Bulk Operations**: 10-100x performance improvements for bulk data

## Code Examples

Each feature document includes:

- **Quick Start**: Get up and running immediately
- **Basic Usage**: Common patterns and simple examples
- **Advanced Usage**: Complex scenarios and best practices
- **Performance Tips**: Optimization strategies
- **Error Handling**: Common issues and solutions

## Integration with Design Documentation

These feature documents complement the [design documentation](../design/) which covers technical architecture and
implementation details. Use both together for comprehensive understanding:

- **Feature Documentation**: Focus on "how to use" SQLObjects capabilities
- **Design Documentation**: Focus on "how SQLObjects works" internally

## Contributing

When adding new features or updating existing ones:

1. Update the relevant feature documentation
2. Include practical code examples
3. Add performance considerations
4. Update this README if adding new feature categories
5. Ensure examples follow the project's coding standards

## Support

For questions about specific features:

- Check the relevant feature documentation first
- Review [design documentation](../design/) for technical details
- Look at test files for additional usage examples
- Reference the API documentation in each feature document
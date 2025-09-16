# SQLObjects Features Documentation

This directory contains comprehensive documentation for all SQLObjects features and capabilities.

## Feature Documentation

### Core Features
- **[Database Setup](01-database-setup.md)** - Database configuration, connection management, and multi-database support
- **[Model Definition](02-model-definition.md)** - Model creation, field types, validation, and configuration
- **[Querying Data](03-querying-data.md)** - Query building, filtering, aggregation, and optimization
- **[CRUD Operations](04-crud-operations.md)** - Create, read, update, delete operations and bulk processing
- **[Relationships](05-relationships.md)** - Model relationships, loading strategies, and performance optimization
- **[Validation & Signals](06-validation-signals.md)** - Data validation and lifecycle hooks
- **[Performance Optimization](07-performance-optimization.md)** - Performance tuning, caching, and best practices

## Quick Navigation

### Getting Started
1. [Database Setup](01-database-setup.md#quick-start) - Initialize your database connection
2. [Model Definition](02-model-definition.md#basic-model-definition) - Create your first model
3. [Querying Data](03-querying-data.md#basic-queries) - Start querying your data

### Common Tasks
- **Creating Records**: [CRUD Operations - Create](04-crud-operations.md#create-operations)
- **Bulk Operations**: [CRUD Operations - Bulk](04-crud-operations.md#bulk-operations)
- **Complex Queries**: [Querying Data - Advanced](03-querying-data.md#advanced-querying)
- **Relationship Loading**: [Relationships - Loading](05-relationships.md#relationship-loading)
- **Performance Tuning**: [Performance Optimization](07-performance-optimization.md)

### Advanced Features
- **Multi-Database**: [Database Setup - Multi-Database](01-database-setup.md#multi-database-setup)
- **Custom Validation**: [Validation & Signals - Custom](06-validation-signals.md#custom-validation)
- **Lifecycle Hooks**: [Validation & Signals - Signals](06-validation-signals.md#signal-system)
- **Raw SQL**: [Querying Data - Raw SQL](03-querying-data.md#raw-sql)

## Documentation Status

> 📝 These English documents are based on the Chinese versions. For the most up-to-date content, see the corresponding files in [docs-zh/features/](../../docs-zh/features/).

### Translation Status
- ✅ **Database Setup** - Complete
- ✅ **Model Definition** - Complete  
- ✅ **Querying Data** - Complete
- 🚧 **CRUD Operations** - In Progress
- 🚧 **Relationships** - In Progress
- 🚧 **Validation & Signals** - In Progress
- 🚧 **Performance Optimization** - In Progress

## Related Documentation

### Design Documentation
- [Core Architecture](../design/01-core-architecture.md) - System architecture and design principles
- [Data Operations](../design/02-data-operations.md) - Query execution and data processing
- [Field System](../design/03-field-system.md) - Field types and type system

### Development Resources
- [Developer Guide](../../.amazonq/rules/) - Development rules and guidelines
- [API Reference](../api/) - Detailed API documentation
- [Examples](../../examples/) - Code examples and tutorials

## Contributing to Documentation

### Updating Documentation
1. **English Updates**: Update files in this directory (`docs/features/`)
2. **Chinese Updates**: Update corresponding files in `docs-zh/features/`
3. **Sync Status**: Update translation status in this README
4. **Cross-References**: Ensure all links point to correct language versions

### Documentation Standards
- **Runnable Examples**: All code examples must be executable
- **API Accuracy**: Examples must match actual implementation
- **Progressive Complexity**: Start simple, build to advanced concepts
- **Cross-Platform**: Examples work across supported databases

### Getting Help
- **Issues**: Report documentation issues on GitHub
- **Discussions**: Join community discussions for clarification
- **Contributions**: Submit pull requests for improvements
- **Translation**: Help translate missing documentation
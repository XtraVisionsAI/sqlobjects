# SQLObjects AI Assistant Rules

Best practices and usage patterns for SQLObjects, optimized for AI coding assistants.

## Quick Navigation

- **[01. Database & Session Guide](01-database-session-guide.md)** - Connection management, transactions, and SQL logging
- **[02. Model Definition Guide](02-model-definition-guide.md)** - Model creation and field configuration
- **[03. Query Operations Guide](03-query-operations-guide.md)** - Filtering, sorting, and data retrieval
- **[04. CRUD Operations Guide](04-crud-operations-guide.md)** - Create, read, update, delete operations
- **[05. Relationships Guide](05-relationships-guide.md)** - Model relationships, loading strategies, and cascade operations
- **[06. Validation & Signals Guide](06-validation-signals-guide.md)** - Data validation and lifecycle hooks
- **[07. Performance Guide](07-performance-guide.md)** - Optimization techniques and best practices

## Method Ownership Matrix

The single most common mistake is calling a manager-only method on a QuerySet
(or vice versa). `Model.objects` is the **manager**; `filter()` returns a
**QuerySet**. They own different methods:

| Operation | Manager (`Model.objects`) | QuerySet (`.filter(...)`) |
|---|---|---|
| Create | `create()`, `get_or_create()`, `update_or_create()` | — |
| Bulk write | `bulk_create()`, `bulk_update()`, `bulk_delete()` | — |
| Whole-table write | `delete_all()`, `update_all(**values)` | — |
| Filtered write | — | `update(**values)`, `delete()` |
| Read | `get()`, `all()`, `first()`, `last()`, `in_bulk()` | `get()`, `all()`, `first()`, `last()` |
| Refine | `filter()`, `exclude()` (returns QuerySet) | `filter()`, `exclude()`, `order_by()`, `limit()`, `offset()` |
| Projection | `values()`, `values_list()`, `only()`, `defer()` | `values()`, `values_list()`, `only()`, `defer()` |
| Aggregate | `count()`, `aggregate()`, `annotate()`, `group_by()`, `having()` | `count()`, `aggregate()`, `annotate()`, `group_by()`, `having()` |

Rules of thumb:

- `filter(...).delete_all()` / `filter(...).update_all()` **do not exist** — a
  filtered write is `filter(...).delete()` / `filter(...).update(**values)`.
- `bulk_*` operate on explicit row data, so they live on the manager only.
- Calling a manager-only method on a QuerySet raises `AttributeError` with a
  hint pointing to the correct method.

## Purpose

These rules provide concise, actionable guidance for using SQLObjects effectively. Each guide includes:

- **Core Concepts** - Essential understanding
- **Common Usage** - Most frequent patterns with code examples
- **Best Practices** - Do's and don'ts
- **Performance Tips** - Optimization considerations
- **Troubleshooting** - Common issues and solutions

## For AI Assistants

When helping users with SQLObjects:

1. **Reference the appropriate guide** based on the user's question
2. **Use the code examples** as templates
3. **Follow the best practices** outlined in each guide
4. **Consider performance implications** mentioned in the guides
5. **Check troubleshooting sections** for common issues

## For Developers

These rules complement the full documentation:

- **Detailed Documentation**: See `docs/features/` for comprehensive guides
- **Design Documentation**: See `docs/design/` for implementation details
- **API Reference**: See inline code documentation

## Installation

Install the package, then install rules for your AI assistant:

```bash
# Install SQLObjects
pip install sqlobjects

# Install rules for your AI assistant
sqlobjects-install-rules amazonq  # For Amazon Q
sqlobjects-install-rules cursor   # For Cursor
sqlobjects-install-rules claude   # For Claude
sqlobjects-install-rules kiro     # For Kiro
```

## Version

`sqlobjects-install-rules` stamps each installed file with the exact package
version it was generated from — trust that stamp over this line. Version-
sensitive behaviors to watch: grouped aggregation (`annotate` + `group_by`)
raises `QueryError` on out-of-group column selection and returns rows via
`.values()` since 2.0, and `aggregate()` combined with `group_by()` also
raises `QueryError` since 2.0; earlier versions silently expanded GROUP BY
(or dropped it entirely for `aggregate()`) and returned wrong results.

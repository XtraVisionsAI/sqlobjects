## 1.9.1 (2026-04-09)

### Fix

- **query**: order_by uses replace semantics instead of append

## 1.9.0 (2026-03-27)

### Feat

- **logging**: wire ObjectLogger into QueryExecutor, zero-config caller rewriting
- **logging**: replace SQLCallerFilter with ObjectLogger, remove SQLCallerFilter
- **logging**: add ObjectLogger and _install_object_logger

### Fix

- **logging**: skip stdlib logging frames in _should_skip_frame, add end-to-end test
- **logging**: use logging._lock context manager for Python 3.13 compatibility
- **logging**: add _should_skip_frame tests and fix assertion quality

### Refactor

- **logging**: extract _should_skip_frame and add _find_user_frame

## 1.8.0 (2026-03-26)

### Feat

- **logging**: export SQLCallerFilter and get_caller_frame in public API
- **logging**: emit SQL log records in QueryExecutor
- **logging**: add SQLCallerFilter
- **logging**: add get_caller_frame() helper

### Fix

- **logging**: eliminate isEnabledFor race and fix test name
- **logging**: restore logger level in test_no_log_when_logger_disabled
- **logging**: guard timing code with isEnabledFor check
- **logging**: simplify SQLCallerFilter extra_skip_packages handling
- **logging**: fix frame-skip edge cases and improve code quality

## 1.7.0 (2026-03-26)

### Feat

- **metadata**: add foreignkey() constraint builder

### Fix

- **raw**: allow SA expressions as arguments in raw() methods

## 1.6.0 (2026-03-18)

### Feat

- **metadata**: add foreignkey()    constraint builder

## 1.5.0 (2026-03-16)

### Feat

- **cascade**: unify cascade strategy with auto-detection for Model.delete()

## 1.4.0 (2026-03-11)

### Feat

- **session**: fix nested ctx_session() and add ASGI/FastAPI integration

## 1.3.0 (2026-03-10)

### Feat

- **fields**: support class name reference in foreign_key() with delayed matching

## 1.2.5 (2026-03-06)

### Fix

- **examples,docs**: fix PGVECTOR type definition and documentation errors
- **types**: fix JSON/JSONB field containment query generating wrong SQL

## 1.2.4 (2026-02-28)

### Fix

- handle nested Q objects in Q._to_sqlalchemy

### Refactor

- **relationships**: overhaul relationship resolution and prefetch system

## 1.2.3 (2026-02-26)

### Fix

- resolve PostgreSQL test failures and cross-test data pollution
- **executor**: add overloads to execute() and fix iterator type narrowing
- **queryset**: replace non-existent executor.session with _get_session()
- enhance exception handling to surface detailed SQLAlchemy errors

### Refactor

- **metadata**: simplify index handling and config parsing

## 1.2.2 (2026-02-26)

### Fix

- clone Column descriptor per subclass to prevent shared ColumnAttribute binding

## 1.2.1 (2026-02-25)

### Refactor

- centralize session resolution in get_session()

## 1.2.0 (2026-02-25)

### Feat

- **metadata**: improve constraint and index naming conventions

## 1.1.0 (2026-02-14)

### Feat

- update custom field type imports to use sqlobjects.fields.types
- implement CTE (Common Table Expressions) support
- add support for SQL window functions
- add EXPLAIN support with dialect-based architecture

### Fix

- update test imports to use DeferredObject instead of DeferredFieldProxy

## 1.0.16 (2025-11-18)

### Fix

- correct ModelMixin inheritance

## 1.0.15 (2025-11-18)

### Feat

- preserve annotate fields and add serialization options

## 1.0.14 (2025-11-18)

### Feat

- add has_session() to check explicit session availability

## 1.0.13 (2025-11-18)

## 1.0.12 (2025-11-18)

### Refactor

- move rules installer to independent scripts

## 1.0.11 (2025-11-18)

### Feat

- add AI assistant rules with auto-install support

## 1.0.10 (2025-11-17)

### Feat

- support Model class in join methods for cleaner API

## 1.0.9 (2025-11-14)

### Feat

- add optional tables parameter to create_tables/drop_tables

## 1.0.8 (2025-11-11)

### Feat

- add model-level relationship loading methods
- improve relation field type inference
- refactor relationship proxies

## 1.0.7 (2025-10-14)

### Feat

- add upsert support for PostgreSQL

### Fix

- identity support for PostgreSQL

### Refactor

- consolidate bulk and queryset logic

### Perf

- improve bulk delete performance

## 1.0.6 (2025-10-08)

### Feat

- optimize field cache and state manager
- implement relationship prefetch support
- add kwargs parameter support to filter/exclude/get methods

### Refactor

- unify cascade for model and queryset operations

## 1.0.5 (2025-09-25)

### Fix

- generate DDL using column definition order

## 1.0.4 (2025-09-25)

### Feat

- remove unnecessary exception catching
- implement insert or update using database upsert

### Fix

- use pk column name instead of column instance for pgsql upsert

### Refactor

- move field default value related methods to DataConversionMixin

## 1.0.3 (2025-09-25)

### Fix

- field default/default_factory not working

## 1.0.2 (2025-09-24)

### Feat

- add type support for StringColumn
- add support for cascade delete in relationships
- add cascade support to relationship fields
- add type checking for __registry__
- use base model to create database tables
- init public commit

### Fix

- foreign key type inference issue

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

from typing import Any

from sqlalchemy import (
    Table,
    and_,
    asc,
    desc,
    literal,
    select,
    text,
)


# Export classes for use in other modules
__all__ = ["QueryBuilder"]


class QueryBuilder:
    """Immutable query builder for SQL construction and optimization.

    Handles all aspects of SQL query building through composition pattern.
    Each method returns a new QueryBuilder instance to maintain immutability.
    """

    def __init__(self, model_class):
        """Initialize QueryBuilder with model class.

        Args:
            model_class: The model class this builder operates on
        """
        self.model_class = model_class
        self.conditions: list[Any] = []  # SQLAlchemy expressions, Q objects, etc.
        self.ordering: list[Any] = []  # Strings or SQLAlchemy expressions
        self.limits: int | None = None
        self.offset_value: int | None = None
        self.relationships: set[str] = set()  # For select_related (JOIN)
        self.prefetch_relationships: set[str] = set()  # For prefetch_related (separate queries)
        self.selected_fields: set[str] = set()
        self.deferred_fields: set[str] = set()
        self.distinct_fields: list[str] = []
        self.annotations: dict[str, Any] = {}
        self.group_clauses: list[Any] = []
        self.having_conditions: list[Any] = []
        self.joins: list[tuple[Table, Any, str]] = []  # (table, condition, join_type)
        self.lock_mode: str | None = None
        self.lock_options: dict[str, bool] = {}
        self.extra_columns: dict[str, str] = {}
        self.extra_where: list[str] = []
        self.extra_params: dict[str, Any] = {}
        self.is_none_query: bool = False
        self.is_reversed: bool = False
        self.prefetch_configs: dict[str, Any] = {}

    def add_filter(self, *conditions):
        """Add WHERE conditions to the query.

        Args:
            *conditions: SQLAlchemy expressions or Q objects

        Returns:
            New QueryBuilder instance with added conditions
        """
        new_builder = self.copy()
        new_builder.conditions.extend(conditions)
        return new_builder

    def add_ordering(self, *fields):
        """Add ORDER BY fields to the query.

        Args:
            *fields: Field names or SQLAlchemy ordering expressions

        Returns:
            New QueryBuilder instance with added ordering
        """
        new_builder = self.copy()
        new_builder.ordering.extend(fields)
        return new_builder

    def add_limit(self, count: int):
        """Add LIMIT clause to the query.

        Args:
            count: Maximum number of results to return

        Returns:
            New QueryBuilder instance with limit applied
        """
        new_builder = self.copy()
        new_builder.limits = count
        return new_builder

    def add_offset(self, count: int):
        """Add OFFSET clause to the query.

        Args:
            count: Number of results to skip

        Returns:
            New QueryBuilder instance with offset applied
        """
        new_builder = self.copy()
        new_builder.offset_value = count
        return new_builder

    def add_relationships(self, *fields):
        """Add relationship fields for select_related (JOIN).

        Args:
            *fields: Relationship field names as strings

        Returns:
            New QueryBuilder instance with relationship fields added
        """
        new_builder = self.copy()
        new_builder.relationships.update(fields)
        return new_builder

    def add_prefetch_relationships(self, *fields):
        """Add relationship fields for prefetch_related (separate queries).

        Args:
            *fields: Relationship field names as strings

        Returns:
            New QueryBuilder instance with prefetch relationship fields added
        """
        new_builder = self.copy()
        new_builder.prefetch_relationships.update(fields)
        return new_builder

    def add_prefetch_configs(self, **configs):
        """Add prefetch configurations with custom QuerySets.

        Args:
            **configs: Mapping of field names to custom QuerySet configurations

        Returns:
            New QueryBuilder instance with prefetch configs added
        """
        new_builder = self.copy()
        new_builder.prefetch_configs = {**self.prefetch_configs, **configs}
        return new_builder

    def add_selected_fields(self, *fields):
        """Add fields to SELECT clause (only() method).

        Args:
            *fields: Field names to include in SELECT

        Returns:
            New QueryBuilder instance with selected fields added
        """
        new_builder = self.copy()
        new_builder.selected_fields.update(fields)
        return new_builder

    def add_deferred_fields(self, *fields):
        """Add fields to defer from SELECT clause (defer() method).

        Args:
            *fields: Field names to exclude from SELECT

        Returns:
            New QueryBuilder instance with deferred fields added
        """
        new_builder = self.copy()
        new_builder.deferred_fields.update(fields)
        return new_builder

    def remove_deferred_fields(self, *fields):
        """Remove fields from deferred set (undefer() method).

        Args:
            *fields: Field names to remove from deferred set

        Returns:
            New QueryBuilder instance with specified fields no longer deferred
        """
        new_builder = self.copy()
        new_builder.deferred_fields.difference_update(fields)
        return new_builder

    def add_distinct(self, *fields):
        """Add DISTINCT clause to the query.

        Args:
            *fields: Field names for DISTINCT, empty for all fields

        Returns:
            New QueryBuilder instance with DISTINCT applied
        """
        new_builder = self.copy()
        new_builder.distinct_fields = list(fields)
        return new_builder

    def add_annotations(self, **kwargs):
        """Add annotation expressions to SELECT clause.

        Args:
            **kwargs: Mapping of alias names to SQLAlchemy expressions

        Returns:
            New QueryBuilder instance with annotations added
        """
        new_builder = self.copy()
        new_builder.annotations.update(kwargs)
        return new_builder

    def add_group_by(self, *fields):
        """Add GROUP BY clauses to the query.

        Args:
            *fields: Field names or SQLAlchemy expressions for grouping

        Returns:
            New QueryBuilder instance with GROUP BY added
        """
        new_builder = self.copy()
        new_builder.group_clauses.extend(fields)
        return new_builder

    def add_having(self, *conditions):
        """Add HAVING conditions for grouped queries.

        Args:
            *conditions: SQLAlchemy expressions for HAVING clause

        Returns:
            New QueryBuilder instance with HAVING conditions added
        """
        new_builder = self.copy()
        new_builder.having_conditions.extend(conditions)
        return new_builder

    def add_join(self, table: Table, condition: Any, join_type: str = "inner"):
        """Add JOIN clause to the query.

        Args:
            table: Table to join with
            condition: JOIN condition expression
            join_type: Type of join ('inner', 'left', 'outer')

        Returns:
            New QueryBuilder instance with JOIN added
        """
        new_builder = self.copy()
        new_builder.joins.append((table, condition, join_type))
        return new_builder

    def add_lock(self, mode: str, **options):
        """Add row-level locking to the query.

        Args:
            mode: Lock mode ('update' or 'share')
            **options: Lock options (nowait, skip_locked)

        Returns:
            New QueryBuilder instance with locking applied
        """
        new_builder = self.copy()
        new_builder.lock_mode = mode
        new_builder.lock_options = options
        return new_builder

    def add_extra(
        self, columns: dict[str, str] | None = None, where: list[str] | None = None, params: dict | None = None
    ):
        """Add extra SQL fragments to the query.

        Args:
            columns: Extra columns to add to SELECT clause
            where: Extra WHERE conditions as raw SQL strings
            params: Parameters for extra SQL fragments

        Returns:
            New QueryBuilder instance with extra SQL added
        """
        new_builder = self.copy()
        if columns:
            new_builder.extra_columns.update(columns)
        if where:
            new_builder.extra_where.extend(where)
        if params:
            new_builder.extra_params.update(params)
        return new_builder

    def set_none(self):
        """Set query to return no results (none() method).

        Returns:
            New QueryBuilder instance that will return empty results
        """
        new_builder = self.copy()
        new_builder.is_none_query = True
        return new_builder

    def set_reversed(self):
        """Set query ordering to be reversed.

        Returns:
            New QueryBuilder instance with reversed ordering
        """
        new_builder = self.copy()
        new_builder.is_reversed = True
        return new_builder

    def _find_foreign_key_column(self, table, relation_name):
        """Find foreign key column for relation."""
        fk_column_name = f"{relation_name}_id"
        if fk_column_name in table.c and table.c[fk_column_name].foreign_keys:
            return table.c[fk_column_name]
        return None

    def _find_table_by_model_name(self, metadata, model_name):
        """Find table by model name."""
        # Try pluralized form first
        table_name = f"{model_name}s"
        if table_name in metadata.tables:
            return metadata.tables[table_name]
        # Try exact name
        if model_name in metadata.tables:
            return metadata.tables[model_name]
        return None

    def _find_reverse_foreign_key(self, target_table, source_table):
        """Find reverse foreign key."""
        source_table_name = source_table.name
        if source_table_name.endswith("s"):
            source_table_name = source_table_name[:-1]
        source_fk_name = f"{source_table_name}_id"
        if source_fk_name in target_table.c and target_table.c[source_fk_name].foreign_keys:
            return target_table.c[source_fk_name]
        return None

    def _get_referenced_table(self, fk_column, metadata):
        """Get referenced table from foreign key."""
        fk = list(fk_column.foreign_keys)[0]
        return fk.column.table

    def _apply_select_related_joins(self, query, base_table):
        """Apply JOIN clauses for select_related relationships."""
        metadata = base_table.metadata

        for relationship_path in self.relationships:
            try:
                path_parts = relationship_path.split("__")
                current_table = base_table

                for relation_name in path_parts:
                    # Try forward relationship first
                    fk_column = self._find_foreign_key_column(current_table, relation_name)

                    if fk_column is not None:
                        # Forward relationship
                        referenced_table = self._get_referenced_table(fk_column, metadata)
                        join_condition = fk_column == referenced_table.c.id
                        query = query.outerjoin(referenced_table, join_condition)
                        current_table = referenced_table
                    else:
                        # Try reverse relationship
                        target_table = self._find_table_by_model_name(metadata, relation_name)
                        if target_table is not None:
                            reverse_fk = self._find_reverse_foreign_key(target_table, current_table)
                            if reverse_fk is not None:
                                join_condition = current_table.c.id == reverse_fk
                                query = query.outerjoin(target_table, join_condition)
                                current_table = target_table
                                continue

                        # No valid relationship found
                        available_relations = [
                            col.name[:-3] for col in current_table.c if col.name.endswith("_id") and col.foreign_keys
                        ]
                        raise ValueError(
                            f"Invalid relationship '{relation_name}' in path '{relationship_path}'. "
                            f"Available relationships: {available_relations}"
                        )

            except ValueError:
                raise
            except Exception as e:
                raise ValueError(f"Error processing relationship '{relationship_path}': {e}") from e

        return query

    def _get_next_table_in_path(self, current_table, relation_name, metadata):
        """Get next table in relationship path."""
        # Try forward relationship
        fk_column = self._find_foreign_key_column(current_table, relation_name)
        if fk_column:
            return self._get_referenced_table(fk_column, metadata)

        # Try reverse relationship
        target_table = self._find_table_by_model_name(metadata, relation_name)
        if target_table and self._find_reverse_foreign_key(target_table, current_table):
            return target_table

        return None

    def _get_select_related_columns(self, base_table):
        """Get columns from related tables for select_related."""
        related_columns = []
        metadata = base_table.metadata

        for relationship_path in self.relationships:
            try:
                path_parts = relationship_path.split("__")
                current_table = base_table

                for i, relation_name in enumerate(path_parts):
                    # Get next table
                    next_table = self._get_next_table_in_path(current_table, relation_name, metadata)
                    if next_table is None:
                        break

                    # Build path prefix for unique aliases
                    path_prefix = "__".join(path_parts[: i + 1])

                    # Add columns with unique aliases
                    for column in next_table.c:
                        alias = f"{path_prefix}__{column.name}"
                        related_columns.append(column.label(alias))

                    current_table = next_table

            except Exception:
                continue

        return related_columns

    def build(self, table):
        """Build final SQLAlchemy query object from accumulated clauses.

        Args:
            table: SQLAlchemy Table object to query

        Returns:
            SQLAlchemy Select object ready for execution
        """
        # Handle none query - return query that matches nothing
        if self.is_none_query:
            return select(table).where(literal(False))

        # Get auto-deferred fields from model class
        auto_deferred_fields = set()
        if hasattr(self.model_class, "_get_field_cache"):
            try:
                field_cache = self.model_class._get_field_cache()  # noqa
                auto_deferred_fields = field_cache.get("deferred_fields", set())
            except Exception:  # noqa
                pass

        # Collect all columns to select (base table + related tables)
        columns_to_select = []

        # Handle field selection (only() method)
        if self.selected_fields:
            columns_to_select.extend([table.c[field] for field in self.selected_fields if field in table.c])
        elif self.deferred_fields or auto_deferred_fields:
            # For defer() or auto-deferred fields, select all fields except deferred ones
            all_fields = set(table.columns.keys())
            combined_deferred = self.deferred_fields | auto_deferred_fields
            selected_fields = all_fields - combined_deferred
            columns_to_select.extend([table.c[field] for field in selected_fields if field in table.c])
        else:
            columns_to_select.extend(table.c)

        # Add related table columns for select_related (only for select_related, not prefetch_related)
        if self.relationships:
            related_columns = self._get_select_related_columns(table)
            columns_to_select.extend(related_columns)

        # Create the base query
        query = select(*columns_to_select) if columns_to_select else select(table)

        # Apply manual joins
        for join_table, join_condition, join_type in self.joins:
            if join_type == "left":
                query = query.outerjoin(join_table, join_condition)
            else:  # inner join
                query = query.join(join_table, join_condition)

        # Apply select_related joins (only for select_related, not prefetch_related)
        if self.relationships:
            query = self._apply_select_related_joins(query, table)

        # Apply conditions
        if self.conditions:
            # Convert FunctionExpression to underlying SQLAlchemy expressions
            processed_conditions = []
            for condition in self.conditions:
                if hasattr(condition, "expression"):
                    # This is a FunctionExpression, use its underlying expression
                    processed_conditions.append(condition.expression)
                else:
                    processed_conditions.append(condition)
            query = query.where(and_(*processed_conditions))

        # Apply extra where clauses
        if self.extra_where:
            extra_conditions = []
            for clause in self.extra_where:
                if self.extra_params:
                    extra_conditions.append(text(clause).bindparams(**self.extra_params))
                else:
                    extra_conditions.append(text(clause))
            query = query.where(and_(*extra_conditions))

        # Apply distinct
        if self.distinct_fields:
            columns = [table.c[field] for field in self.distinct_fields if field in table.c]
            if columns:
                query = query.distinct(*columns)
            else:
                query = query.distinct()

        # Apply annotations
        if self.annotations:
            annotation_columns = []
            for alias, expr in self.annotations.items():
                if hasattr(expr, "resolve"):
                    annotation_columns.append(expr.resolve(table).label(alias))
                else:
                    annotation_columns.append(expr.label(alias))
            query = query.add_columns(*annotation_columns)

        # Apply extra columns
        if self.extra_columns:
            extra_cols = []
            for alias, sql in self.extra_columns.items():
                if self.extra_params:
                    extra_cols.append(text(sql).bindparams(**self.extra_params).label(alias))
                else:
                    extra_cols.append(text(sql).label(alias))
            query = query.add_columns(*extra_cols)

        # Apply group by
        if self.group_clauses:
            group_columns = []
            for field in self.group_clauses:
                if isinstance(field, str) and field in table.c:
                    group_columns.append(table.c[field])
                elif hasattr(field, "resolve") and not isinstance(field, str):
                    group_columns.append(field.resolve(table))
                else:
                    group_columns.append(field)
            query = query.group_by(*group_columns)

        # Apply having
        if self.having_conditions:
            having_exprs = []
            for condition in self.having_conditions:
                if hasattr(condition, "resolve"):
                    having_exprs.append(condition.resolve(table))
                else:
                    having_exprs.append(condition)
            query = query.having(and_(*having_exprs))

        # Apply ordering
        if self.ordering:
            order_clauses = []
            for field in self.ordering:
                if isinstance(field, str):
                    if field.startswith("-"):
                        field_name = field[1:]
                        if field_name in table.c:
                            if self.is_reversed:
                                order_clauses.append(asc(table.c[field_name]))
                            else:
                                order_clauses.append(desc(table.c[field_name]))
                    else:
                        if field in table.c:
                            if self.is_reversed:
                                order_clauses.append(desc(table.c[field]))
                            else:
                                order_clauses.append(asc(table.c[field]))
                elif hasattr(field, "resolve"):
                    order_clauses.append(field.resolve(table))
                else:
                    order_clauses.append(field)

            if order_clauses:
                query = query.order_by(*order_clauses)
        elif self.is_reversed:
            # If reversed but no explicit ordering, use primary key for consistent reversal
            pk_columns = [col for col in table.columns if col.primary_key]
            if pk_columns:
                query = query.order_by(desc(pk_columns[0]))

        # Apply row locking
        if self.lock_mode:
            lock_kwargs = {k: v for k, v in self.lock_options.items() if k in ("nowait", "skip_locked")}
            if self.lock_mode == "update":
                query = query.with_for_update(**lock_kwargs)  # type: ignore[arg-type]
            elif self.lock_mode == "share":
                query = query.with_for_update(read=True, **lock_kwargs)  # type: ignore[arg-type]

        # Apply limit and offset
        if self.limits is not None:
            query = query.limit(self.limits)
        if self.offset_value is not None:
            query = query.offset(self.offset_value)

        return query

    def copy(self):
        """Create a deep copy of this QueryBuilder instance.

        Returns:
            New QueryBuilder instance with identical state
        """
        new_builder = QueryBuilder(self.model_class)
        new_builder.conditions = self.conditions.copy()
        new_builder.ordering = self.ordering.copy()
        new_builder.limits = self.limits
        new_builder.offset_value = self.offset_value
        new_builder.relationships = self.relationships.copy()
        new_builder.selected_fields = self.selected_fields.copy()
        new_builder.deferred_fields = self.deferred_fields.copy()
        new_builder.distinct_fields = self.distinct_fields.copy()
        new_builder.annotations = self.annotations.copy()
        new_builder.group_clauses = self.group_clauses.copy()
        new_builder.having_conditions = self.having_conditions.copy()
        new_builder.joins = self.joins.copy()
        new_builder.lock_mode = self.lock_mode
        new_builder.lock_options = self.lock_options.copy()
        new_builder.extra_columns = self.extra_columns.copy()
        new_builder.extra_where = self.extra_where.copy()
        new_builder.extra_params = self.extra_params.copy()
        new_builder.is_none_query = self.is_none_query
        new_builder.is_reversed = self.is_reversed
        new_builder.prefetch_configs = self.prefetch_configs.copy()
        new_builder.prefetch_relationships = self.prefetch_relationships.copy()
        return new_builder

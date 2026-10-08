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
from sqlalchemy.sql.selectable import Subquery

from ..exceptions import QueryError


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
        self.is_distinct = False
        self.annotations: dict[str, Any] = {}
        self.group_clauses: list[Any] = []
        self.having_conditions: list[Any] = []
        self.joins: list[tuple[Table | Subquery, Any, str]] = []  # (table, condition, join_type)
        self.lock_mode: str | None = None
        self.lock_options: dict[str, bool] = {}
        self.extra_columns: dict[str, str] = {}
        self.extra_where: list[str] = []
        self.extra_params: dict[str, Any] = {}
        self.is_none_query: bool = False
        self.is_reversed: bool = False
        self.prefetch_configs: dict[str, Any] = {}
        self.ctes: list[Any] = []  # CTEExpression objects

    def add_filter(self, *conditions, **kwargs):
        """Add WHERE conditions to the query.

        Args:
            *conditions: SQLAlchemy expressions or Q objects
            **kwargs: Field name to value mappings

        Returns:
            New QueryBuilder instance with added conditions
        """
        new_builder = self.copy()
        new_builder.conditions.extend(conditions)
        if kwargs:
            new_builder.conditions.append(("__KWARGS_MARKER__", kwargs))
        return new_builder

    def add_ordering(self, *fields):
        """Set ORDER BY fields for the query, replacing any existing ordering.

        Args:
            *fields: Field names or SQLAlchemy ordering expressions

        Returns:
            New QueryBuilder instance with replaced ordering
        """
        new_builder = self.copy()
        new_builder.ordering = list(fields)
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

    def add_cte(self, cte):
        """Add CTE (Common Table Expression) to the query.

        Args:
            cte: CTEExpression object to add

        Returns:
            New QueryBuilder instance with CTE added
        """
        new_builder = self.copy()
        new_builder.ctes = self.ctes + [cte]
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
        new_builder.is_distinct = True
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

    def add_join(self, table: Table | Subquery, condition: Any, join_type: str = "inner"):
        """Add JOIN clause to the query.

        Args:
            table: Table or Subquery to join with
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

    def _select_related_plan(self, base_table):
        """Resolve each relationship once and allocate an alias per path."""
        from ..fields.relations.utils import RelationshipAnalyzer

        plan = {}
        for path in sorted(self.relationships):
            model, source = self.model_class, base_table
            parts = path.split("__")
            for index, name in enumerate(parts):
                prefix = "__".join(parts[: index + 1])
                if prefix in plan:
                    target, info, _ = plan[prefix]
                else:
                    info = RelationshipAnalyzer.analyze_relationship(model, name)
                    if not info:
                        raise ValueError(f"Invalid relationship '{name}' on {model.__name__}")
                    if info["type"] not in ("many_to_one", "one_to_one"):
                        raise QueryError(
                            f"select_related requires a single-valued relationship; use prefetch_related for '{path}'"
                        )
                    target = info["related_model"].get_table().alias(f"sr_{prefix}")
                    local, remote = (
                        (info["foreign_key_fields"], info["ref_fields"])
                        if info["type"] == "many_to_one"
                        else (info["ref_fields"], info["foreign_key_fields"])
                    )
                    condition = and_(
                        *(source.c[left] == target.c[right] for left, right in zip(local, remote, strict=True))
                    )
                    plan[prefix] = (target, info, condition)
                model, source = info["related_model"], target
        return plan

    def _get_select_related_columns(self, plan):
        columns = []
        for path, (target, info, _) in plan.items():
            selected = {name[len(path) + 2 :] for name in self.selected_fields if name.startswith(path + "__")}
            primary_keys = {col.name for col in info["related_model"].get_table().primary_key}
            auto_deferred = info["related_model"]._get_field_cache().get("deferred_fields", set())
            for col in target.c:
                label = f"{path}__{col.name}"
                if col.name not in primary_keys:
                    if label in self.deferred_fields or (selected and col.name not in selected):
                        continue
                    if col.name in auto_deferred and col.name not in selected:
                        continue
                columns.append(col.label(label))
        return columns

    def build(self, table, values_fields: tuple[str, ...] | None = None):
        """Build final SQLAlchemy query object from accumulated clauses.

        Args:
            table: SQLAlchemy Table object to query
            values_fields: When given (values()/values_list() mode), select exactly
                these fields in order. Each name must resolve to a table column,
                an annotation alias, or an extra column alias.

        Returns:
            SQLAlchemy Select object ready for execution
        """
        # Handle none query - return query that matches nothing
        if self.is_none_query:
            return select(table).where(literal(False))

        # Build CTEs first (they need to be available for the main query)
        cte_objects = []
        if self.ctes:
            for cte in self.ctes:
                cte_obj = cte._build_cte(table)  # noqa
                cte_objects.append(cte_obj)

        # Get auto-deferred fields from model class
        auto_deferred_fields = set()
        if hasattr(self.model_class, "_get_field_cache"):
            try:
                field_cache = self.model_class._get_field_cache()  # noqa
                auto_deferred_fields = field_cache.get("deferred_fields", set())
            except Exception:  # noqa
                pass

        select_plan = self._select_related_plan(table) if self.relationships else {}

        # Collect all columns to select (base table + related tables)
        columns_to_select = []

        if values_fields is not None:
            # values()/values_list() mode: select exactly the requested fields in
            # order so result rows align with the field names positionally
            unknown = [
                f
                for f in values_fields
                if f not in table.c and f not in self.annotations and f not in self.extra_columns
            ]
            if unknown:
                raise QueryError(
                    f"Unknown field(s) in values()/values_list(): {unknown}. "
                    "Each field must be a model column, an annotation alias, or an extra() column alias."
                )
            for field_name in values_fields:
                if field_name in table.c:
                    columns_to_select.append(table.c[field_name])
                elif field_name in self.annotations:
                    expr = self.annotations[field_name]
                    resolved = expr.resolve(table) if hasattr(expr, "resolve") else expr
                    columns_to_select.append(resolved.label(field_name))
                else:
                    sql = self.extra_columns[field_name]
                    if self.extra_params:
                        columns_to_select.append(text(sql).bindparams(**self.extra_params).label(field_name))
                    else:
                        columns_to_select.append(text(sql).label(field_name))
        # Handle field selection (only() method)
        elif self.selected_fields:
            selected = self.selected_fields - self.deferred_fields
            if not self.group_clauses:
                selected.update(col.name for col in table.primary_key)
            columns_to_select.extend(table.c[field] for field in table.c.keys() if field in selected)
        elif self.deferred_fields or auto_deferred_fields:
            # For defer() or auto-deferred fields, select all fields except deferred ones
            all_fields = set(table.columns.keys())
            combined_deferred = self.deferred_fields | auto_deferred_fields
            selected_fields = all_fields - combined_deferred
            if not self.group_clauses:
                selected_fields.update(col.name for col in table.primary_key)
            columns_to_select.extend([table.c[field] for field in selected_fields if field in table.c])
        else:
            columns_to_select.extend(table.c)

        # Add related table columns for select_related (only for select_related, not prefetch_related)
        if self.relationships and values_fields is None:
            related_columns = self._get_select_related_columns(select_plan)
            columns_to_select.extend(related_columns)

        # Create the base query
        query = (select(*columns_to_select) if columns_to_select else select(table)).select_from(table)

        # Add CTEs to query
        if cte_objects:
            for cte_obj in cte_objects:
                query = query.add_cte(cte_obj)

        # Apply manual joins
        for join_table, join_condition, join_type in self.joins:
            if join_type == "left":
                query = query.outerjoin(join_table, join_condition)
            else:  # inner join
                query = query.join(join_table, join_condition)

        # Apply select_related joins (only for select_related, not prefetch_related)
        if select_plan:
            for target, _, condition in select_plan.values():
                query = query.outerjoin(target, condition)

        # Apply conditions
        if self.conditions:
            # Convert FunctionExpression to underlying SQLAlchemy expressions
            processed_conditions = []
            for condition in self.conditions:
                if isinstance(condition, tuple) and condition[0] == "__KWARGS_MARKER__":
                    # Process kwargs
                    kwargs_dict = condition[1]
                    for field_name, value in kwargs_dict.items():
                        field = getattr(self.model_class, field_name)
                        processed_conditions.append(field == value)
                elif hasattr(condition, "expression") and hasattr(condition, "resolve"):
                    # This is a FunctionExpression, use its underlying expression
                    processed_conditions.append(condition.expression)  # type: ignore[reportAttributeAccessIssue]
                elif hasattr(condition, "_to_sqlalchemy"):
                    # This is a Q object
                    processed_conditions.append(condition._to_sqlalchemy(table))  # noqa # type: ignore[reportAttributeAccessIssue]
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
        if self.is_distinct:
            unknown = [field for field in self.distinct_fields if field not in table.c]
            if unknown:
                raise QueryError(f"Unknown DISTINCT field(s): {unknown}")
            query = query.distinct(*(table.c[field] for field in self.distinct_fields))

        # Apply annotations (values mode already selected the requested ones)
        if self.annotations and values_fields is None:
            annotation_columns = []
            for alias, expr in self.annotations.items():
                if hasattr(expr, "resolve"):
                    annotation_columns.append(expr.resolve(table).label(alias))
                else:
                    annotation_columns.append(expr.label(alias))
            query = query.add_columns(*annotation_columns)

        # Apply extra columns (values mode already selected the requested ones)
        if self.extra_columns and values_fields is None:
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
            group_names = set()
            for field in self.group_clauses:
                if isinstance(field, str) and field in table.c:
                    group_columns.append(table.c[field])
                    group_names.add(field)
                elif hasattr(field, "resolve") and not isinstance(field, str):
                    resolved = field.resolve(table)
                    group_columns.append(resolved)
                    if getattr(resolved, "name", None):
                        group_names.add(resolved.name)
                else:
                    group_columns.append(field)
                    field_name = getattr(field, "name", None)
                    if field_name:
                        group_names.add(field_name)

            # Grouped aggregation must not select columns outside GROUP BY.
            # Previous versions silently added the selected columns to GROUP BY
            # "for PostgreSQL compatibility", which degenerated every group to a
            # single row and produced wrong aggregate values. Grouping by the
            # full primary key is exempt: every column of the table is
            # functionally dependent on it, so one group == one model row.
            if self.annotations:
                pk_names = {col.name for col in table.primary_key.columns}
                if values_fields is not None:
                    selected_names = {f for f in values_fields if f in table.c}
                elif self.selected_fields:
                    selected_names = {f for f in self.selected_fields if f in table.c}
                else:
                    selected_names = set(table.columns.keys()) - self.deferred_fields - auto_deferred_fields

                grouped_by_pk = bool(pk_names) and pk_names <= group_names
                extra_selected = selected_names - group_names
                if not grouped_by_pk and extra_selected:
                    raise QueryError(
                        f"column(s) {sorted(extra_selected)} are selected but not in GROUP BY. "
                        "SQLObjects no longer adds selected columns to GROUP BY silently — "
                        "that would collapse each group to a single row and corrupt aggregates. "
                        "Use .values(*group_fields, *aggregate_aliases) for aggregation rows, "
                        ".only(*group_fields) to hydrate partial instances, "
                        "or group by the primary key to aggregate per model row."
                    )

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
                    descending = field.startswith("-")
                    field_name = field[1:] if descending else field
                    if field_name in table.c:
                        order_column = table.c[field_name]
                    elif field_name in self.annotations:
                        expr = self.annotations[field_name]
                        order_column = expr.resolve(table) if hasattr(expr, "resolve") else expr
                    else:
                        continue
                    order_clauses.append(desc(order_column) if descending != self.is_reversed else asc(order_column))
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
        new_builder.is_distinct = self.is_distinct
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
        new_builder.ctes = self.ctes.copy()
        return new_builder

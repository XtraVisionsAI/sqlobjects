"""Aggregate expression implementations."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import false, select
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import BindParameter, ColumnClause, ColumnElement, False_, Null, True_
from sqlalchemy.sql.selectable import ScalarSelect

from ..exceptions import QueryError
from .base import QueryExpression


if TYPE_CHECKING:
    from ..queries import QueryBuilder

# NULL, TRUE and FALSE: constants that are not bind parameters.
_SINGLETON_CONSTANTS = (Null, True_, False_)


class AggregateExpression(QueryExpression[dict[str, Any]]):
    """Aggregate matching rows, with one statement shared by all evaluation paths."""

    def __init__(self, builder: "QueryBuilder", aggregations: dict[str, Any], executor=None):
        super().__init__(executor)
        if not aggregations:
            raise ValueError("aggregate() requires at least one aggregation expression")
        self._builder = builder
        self._aggregations = aggregations

    def get_query(self):
        """Build the aggregate over the QuerySet's filtered, deduplicated, sliced rows."""
        builder = self._builder
        table = builder.model_class.get_table()
        empty = builder.is_none_query
        grouped = bool(builder.group_clauses)
        if empty or grouped:
            builder = builder.copy()
            builder.is_none_query = False
        grouping_keys = []
        if grouped:
            query, grouping_keys = self._build_grouped_input(builder, table)
        else:
            query = builder.build(table)
        if empty:
            query = query.where(false())
        expressions = {
            alias: expr.resolve(table) if hasattr(expr, "resolve") else expr
            for alias, expr in self._aggregations.items()
        }
        sliced = builder.limits is not None or builder.offset_value is not None
        if not sliced and not builder.distinct_fields:
            query = query.order_by(None)

        if not (grouped or sliced or builder.is_distinct or builder.annotations or builder.extra_columns):
            return query.with_only_columns(
                *(expr.label(alias) for alias, expr in expressions.items())
            ).correlate_except(table)

        # Project aggregate inputs before wrapping. only()/defer() control model
        # hydration, so base-model fields may still be used by an aggregate.
        inputs = {}

        def project_input(element: Any, **kw: Any):
            nonlocal query
            if (
                grouped
                and isinstance(element, ColumnElement)
                and not isinstance(element, BindParameter)
                and not isinstance(element, _SINGLETON_CONSTANTS)
            ):
                for key, alias in grouping_keys:
                    if element.compare(key):
                        inputs[element] = query.selected_columns[alias]
                        return element
            if not isinstance(element, (ColumnClause, ScalarSelect)):
                return None
            if isinstance(element, ColumnClause) and element.table is None:
                if element.name == "*":
                    return element
                projected = query.selected_columns.get(element.name)
                if projected is None:
                    raise QueryError(
                        f"aggregate() input {element.name!r} must be a model column or a projected annotation alias"
                    )
            else:
                projected = query.selected_columns.corresponding_column(element)
                if projected is None:
                    if grouped:
                        raise QueryError("aggregate() over grouped rows requires a grouping key or an annotation alias")
                    # Adding a joined column to ordinary DISTINCT would change
                    # which rows are duplicates. Require an explicit annotation.
                    if (
                        builder.is_distinct
                        and not builder.distinct_fields
                        and getattr(element, "table", None) is not table
                    ):
                        raise QueryError("aggregate() over DISTINCT requires joined or scalar inputs to be projected")
                    projected = element.label(None) if isinstance(element, ScalarSelect) else element
                    query = query.add_columns(projected)
            inputs[element] = projected
            # Scalar subqueries are an input value; never traverse their local
            # columns and accidentally add their tables to the outer query.
            return element

        for expr in expressions.values():
            visitors.replacement_traverse(expr, {}, project_input)

        source = query.correlate_except(table).subquery()
        replacements = {node: source.corresponding_column(projected) for node, projected in inputs.items()}

        def replace_input(element: Any, **kw: Any):
            return replacements.get(element)

        aggregates = [
            visitors.replacement_traverse(expr, {}, replace_input).label(alias) for alias, expr in expressions.items()
        ]
        return select(*aggregates).select_from(source)

    @staticmethod
    def _build_grouped_input(builder, table):
        """Project grouping keys and annotations without adding model-row fields."""
        aliases = list(builder.annotations)
        shadowed = set(aliases) & set(table.c.keys())
        if shadowed:
            raise QueryError(f"Grouped aggregate annotation aliases shadow model columns: {sorted(shadowed)}")
        fields = aliases + list(builder.extra_columns)
        grouping_keys = []
        used = set(fields) | set(table.c.keys())
        for index, field in enumerate(builder.group_clauses):
            if isinstance(field, str):
                if field in table.c:
                    expression = table.c[field]
                elif field in builder.annotations:
                    expression = builder.annotations[field]
                else:
                    raise QueryError(f"Unknown aggregate grouping key: {field!r}")
            else:
                expression = field
            if hasattr(expression, "resolve"):
                expression = expression.resolve(table)
            elif hasattr(expression, "__clause_element__"):
                expression = expression.__clause_element__()
            if not isinstance(expression, ColumnElement):
                raise QueryError("Aggregate grouping keys must be columns, expressions or annotation aliases")
            alias = f"_sqlobjects_group_{index}"
            while alias in used:
                alias += "_"
            used.add(alias)
            builder.annotations[alias] = expression
            fields.append(alias)
            grouping_keys.append((expression, alias))
            if isinstance(expression, (BindParameter, *_SINGLETON_CONSTANTS)):
                # MySQL interprets GROUP BY 1 as a select-list ordinal. Refer to
                # the projected constant by alias to preserve one constant group.
                builder.group_clauses[index] = alias
        return builder.build(table, values_fields=tuple(fields)), grouping_keys

    async def execute(self) -> dict[str, Any]:
        """Execute exactly the statement used by SQL rendering and EXPLAIN."""
        if not self._executor:
            raise RuntimeError("No executor available for aggregate execution")
        result = await self._executor.execute(self.get_query(), "aggregate")
        if isinstance(result, list) and result:
            return dict(zip(self._aggregations, result[0], strict=True))
        return {}

    def scalar_subquery(self):
        """Convert a single aggregate to a scalar subquery."""
        if len(self._aggregations) != 1:
            raise ValueError("Cannot convert multi-field aggregation to scalar subquery")
        return self.get_query().scalar_subquery()

    def __clause_element__(self):
        """Allow SQLAlchemy column comparisons to coerce a single aggregate."""
        return self.scalar_subquery()

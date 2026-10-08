"""Aggregate expression implementations."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import false, select
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import ColumnClause
from sqlalchemy.sql.selectable import ScalarSelect

from ..exceptions import QueryError
from .base import QueryExpression


if TYPE_CHECKING:
    from ..queries import QueryBuilder


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
        if builder.is_none_query:
            builder = builder.copy()
            builder.is_none_query = False
            query = builder.build(table).where(false())
        else:
            query = builder.build(table)
        expressions = {
            alias: expr.resolve(table) if hasattr(expr, "resolve") else expr
            for alias, expr in self._aggregations.items()
        }
        sliced = builder.limits is not None or builder.offset_value is not None
        if not sliced and not builder.distinct_fields:
            query = query.order_by(None)

        if not (sliced or builder.is_distinct or builder.annotations or builder.extra_columns):
            return query.with_only_columns(
                *(expr.label(alias) for alias, expr in expressions.items())
            ).correlate_except(table)

        # Project aggregate inputs before wrapping. only()/defer() control model
        # hydration, so base-model fields may still be used by an aggregate.
        inputs = {}

        def project_input(element: Any, **kw: Any):
            nonlocal query
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

"""Aggregate expression implementations."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, select

from .base import QueryExpression


if TYPE_CHECKING:
    from ..queries import QueryBuilder


class AggregateExpression(QueryExpression[dict[str, Any]]):
    """Represents an aggregation operation that can be executed or used as subquery.

    Aggregate expressions encapsulate SQL aggregation functions like COUNT, AVG, SUM
    and can be used both as standalone queries and as scalar subqueries in filters.
    """

    def __init__(self, builder: "QueryBuilder", aggregations: dict[str, Any], executor=None):
        """Initialize aggregate expression.

        Args:
            builder: Query builder containing base query conditions
            aggregations: Dictionary of alias -> aggregation expression mappings
            executor: Optional query executor
        """
        super().__init__(executor)
        self._builder = builder
        self._aggregations = aggregations

    async def execute(self) -> dict[str, Any]:
        """Execute aggregation query and return results dictionary.

        Returns:
            Dictionary mapping aggregation aliases to computed values
        """
        if not self._executor:
            raise RuntimeError("No executor available for aggregate execution")

        # Build aggregation expressions
        aggregations = []
        labels = []

        for alias, expr in self._aggregations.items():
            if hasattr(expr, "resolve"):
                aggregations.append(expr.resolve(self._builder.model_class.get_table()).label(alias))
            else:
                aggregations.append(expr.label(alias))
            labels.append(alias)

        # Build and execute query
        query = self._builder.build(self._builder.model_class.get_table())
        result = await self._executor.execute(query, "aggregate", aggregations=aggregations)

        if isinstance(result, list) and result:
            first_result = result[0]
            return dict(zip(labels, first_result, strict=False))
        return {}

    def get_sql(self) -> str:
        """Generate SQL string for aggregate query.

        Returns:
            SQL string for the aggregation operation
        """
        # Build aggregation expressions
        aggregations = []

        for alias, expr in self._aggregations.items():
            if hasattr(expr, "resolve"):
                aggregations.append(expr.resolve(self._builder.model_class.get_table()).label(alias))
            else:
                aggregations.append(expr.label(alias))

        # Build base query
        query = select(*aggregations).select_from(self._builder.model_class.get_table())

        # Add conditions if present
        if self._builder.conditions:
            query = query.where(and_(*self._builder.conditions))

        return str(query.compile(compile_kwargs={"literal_binds": True}))

    def scalar_subquery(self):
        """Convert to scalar subquery for use in comparisons.

        Returns:
            SQLAlchemy scalar subquery expression
        """
        # For single aggregation, return scalar subquery
        if len(self._aggregations) == 1:
            expr = next(iter(self._aggregations.values()))

            if hasattr(expr, "resolve"):
                agg_expr = expr.resolve(self._builder.model_class.get_table())
            else:
                agg_expr = expr

            query = select(agg_expr).select_from(self._builder.model_class.get_table())

            if hasattr(self._builder, "conditions") and self._builder.conditions:
                query = query.where(and_(*self._builder.conditions))

            return query.scalar_subquery()
        else:
            raise ValueError("Cannot convert multi-field aggregation to scalar subquery")

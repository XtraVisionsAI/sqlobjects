"""EXPLAIN query analysis support."""


class ExplainResult:
    """Awaitable result for EXPLAIN operations.

    This class wraps EXPLAIN query execution and makes it awaitable,
    providing a clean async interface for query plan analysis.

    Examples:
        plan = await User.objects.filter(User.age > 25).explain()
        analysis = await User.objects.all().explain(analyze=True, verbose=True)
    """

    def __init__(self, expression, analyze: bool, verbose: bool):
        """Initialize EXPLAIN result.

        Args:
            expression: QueryExpression to explain
            analyze: Include actual execution statistics
            verbose: Include detailed execution information
        """
        self.expression = expression
        self.analyze = analyze
        self.verbose = verbose

    def __await__(self):
        """Make this object awaitable."""
        return self._execute().__await__()

    async def _execute(self) -> str:
        """Execute EXPLAIN and return plan.

        Returns:
            Query execution plan as string
        """
        query = self.expression.get_query()
        return await self.expression._executor.explain(query, self.analyze, self.verbose)

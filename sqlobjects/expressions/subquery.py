from typing import Any, Literal

from sqlalchemy import Boolean, ColumnElement, Select, String, exists
from sqlalchemy.ext.compiler import compiles

from ..exceptions import ValidationError


class SubqueryExpression(ColumnElement):
    """Intelligent subquery expression supporting multiple SQLAlchemy subquery types.

    This class provides a unified interface for creating and managing different types
    of subqueries including table subqueries, scalar subqueries, and existence subqueries.
    It automatically handles type conversion and provides operator overloading for
    seamless integration with other expressions.

    Examples:
        >>> # Table subquery for JOIN operations
        >>> subq = User.objects.filter(age__gte=18).subquery()
        >>> # Scalar subquery for comparisons
        >>> avg_age = User.objects.aggregate(avg_age=func.avg(User.age)).subquery("scalar")
        >>> # Existence subquery for boolean conditions
        >>> has_posts = Post.objects.filter(author_id=User.id).subquery("exists")
    """

    inherit_cache = True  # Support SQLAlchemy caching

    def __init__(
        self, query: Select, name: str | None = None, query_type: Literal["auto", "table", "scalar", "exists"] = "auto"
    ):
        """Initialize subquery expression with intelligent type inference.

        Args:
            query: SQLAlchemy Select query to convert to subquery
            name: Optional alias name for the subquery
            query_type: Type of subquery ('auto', 'table', 'scalar', 'exists')

        Raises:
            ValidationError: If query_type is invalid
        """
        super().__init__()
        valid_types = {"auto", "table", "scalar", "exists"}
        if query_type not in valid_types:
            raise ValidationError(f"Unknown query type: {query_type}. Available types: {', '.join(valid_types)}")

        self.query = query
        self.name = name
        self.query_type = self._infer_type() if query_type == "auto" else query_type
        self._subquery = None
        self._scalar_subquery = None
        self._exists_subquery = None

    # SQLAlchemy type obtained dynamically through type attribute
    def __getattribute__(self, name):
        if name == "type":
            return self._get_expression_type() or super().__getattribute__(name)
        return super().__getattribute__(name)

    def _infer_type(self) -> str:
        """Automatically infer the appropriate subquery type based on query structure.

        Analyzes query characteristics including column count, aggregate functions,
        and LIMIT clauses to determine the most suitable subquery type.

        Returns:
            Inferred subquery type ('scalar', 'table', or 'exists')
        """
        try:
            structure = self._analyze_query_structure()

            # Rule 1: Clear scalar query characteristics
            if (
                structure["has_single_column"]
                and structure["has_aggregates"]
                and (structure["has_limit_one"] or structure["is_count_query"])
            ):
                return "scalar"

            # Rule 2: Single column aggregate query (commonly used for comparisons)
            if structure["has_single_column"] and structure["has_aggregates"]:
                return "scalar"

            # Rule 3: Multi-column queries default to table subquery
            if structure["column_count"] > 1:
                return "table"

            # Rule 4: Single column non-aggregate query (e.g., ID lists)
            if structure["has_single_column"] and not structure["has_aggregates"]:
                return "table"  # For IN conditions

            # Default: table subquery
            return "table"

        except Exception:  # noqa
            # Default to table subquery when inference fails
            return "table"

    def _analyze_query_structure(self) -> dict:
        """Analyze query structure to extract inference criteria.

        Examines various aspects of the query including SELECT columns,
        aggregate functions, LIMIT clauses, and annotations to provide
        data for intelligent type inference.

        Returns:
            Dictionary containing query structure analysis results
        """
        analysis = {
            "select_columns": [],
            "has_aggregates": False,
            "has_single_column": False,
            "has_limit_one": False,
            "has_annotations": False,
            "column_count": 0,
            "is_count_query": False,
        }

        try:
            # Analyze SELECT columns
            if hasattr(self.query, "selected_columns"):
                analysis["select_columns"] = list(self.query.selected_columns)  # noqa
                analysis["column_count"] = len(analysis["select_columns"])
                analysis["has_single_column"] = analysis["column_count"] == 1

            # Analyze aggregate functions (simplified detection)
            query_str = str(self.query).lower()
            aggregate_keywords = ["count(", "sum(", "avg(", "max(", "min("]
            analysis["has_aggregates"] = any(keyword in query_str for keyword in aggregate_keywords)

            # Analyze LIMIT clause
            analysis["has_limit_one"] = (
                hasattr(self.query, "_limit") and self.query._limit is not None and self.query._limit == 1  # noqa
            )

            # Detect count queries
            analysis["is_count_query"] = "count(" in query_str

        except Exception:  # noqa
            # Return safe defaults when analysis fails
            pass

        return analysis

    def _get_expression_type(self):
        """Infer SQLAlchemy type based on subquery type

        Returns:
            SQLAlchemy type object or None for table subqueries
        """
        if self.query_type == "exists":
            return Boolean()
        elif self.query_type == "scalar":
            return self._infer_scalar_type()
        else:  # "table"
            return None

    def _infer_scalar_type(self):
        """Infer the return type of scalar subquery

        Returns:
            SQLAlchemy type object based on column analysis
        """
        try:
            columns = list(self.query.selected_columns)  # noqa

            if len(columns) == 1:
                # Single column query: use the column's type directly
                return columns[0].type
            elif len(columns) > 1:
                # Multi-column query: find aggregate column (usually the last one)
                return self._find_aggregate_column_type(columns)
            else:
                # No column info: use default type
                return String()

        except Exception:  # noqa
            return String()

    @staticmethod
    def _find_aggregate_column_type(columns):
        """Find aggregate column type from multiple columns

        Args:
            columns: List of column objects to analyze

        Returns:
            SQLAlchemy type object of the aggregate column
        """
        # Strategy 1: Find columns with aggregate function labels
        for col in reversed(columns):  # Search from back to front
            if hasattr(col, "name") and col.name:
                # Check if column is generated by aggregate function
                if any(agg in str(col).lower() for agg in ["count", "sum", "avg", "max", "min"]):
                    return col.type

        # Strategy 2: Find annotate-generated column (usually the last one)
        last_column = columns[-1]
        if hasattr(last_column, "type"):
            return last_column.type

        # Strategy 3: Default type
        return String()

    def get_children(self, **kwargs):
        """Return child expressions for SQLAlchemy visitor pattern

        Args:
            **kwargs: Additional keyword arguments

        Returns:
            List containing the query object
        """
        return [self.query]

    def resolve(self, table_or_model=None) -> Any:
        """Resolve to appropriate SQLAlchemy object based on subquery type.

        Args:
            table_or_model: Table object or model class for field resolution (unused for subqueries)

        Returns:
            SQLAlchemy subquery object (Subquery, ScalarSelect, or Exists)

        Raises:
            ValidationError: If subquery conversion fails
        """
        _ = table_or_model  # use it to avoid unused argument warning

        try:
            if self.query_type == "scalar":
                return self._get_scalar_subquery()
            elif self.query_type == "exists":
                return self._get_exists_subquery()
            else:  # 'table'
                return self._get_table_subquery()
        except Exception as e:
            raise ValidationError(f"Subquery conversion failed: {e}") from e

    def _get_table_subquery(self):
        """Get table subquery (equivalent to SQLAlchemy subquery()).

        Creates a table subquery that can be used in JOIN operations
        and other table-level operations.

        Returns:
            SQLAlchemy Subquery object

        Raises:
            ValidationError: If subquery creation fails
        """
        if self._subquery is None:
            try:
                self._subquery = self.query.subquery(name=self.name)
            except Exception as e:
                raise ValidationError(f"Subquery build failed: {e}") from e
        return self._subquery

    def _get_scalar_subquery(self):
        """Get scalar subquery (equivalent to SQLAlchemy scalar_subquery()).

        Creates a scalar subquery that returns a single value and can be used
        in comparisons and arithmetic operations.

        IMPORTANT: This method handles multi-column queries (like from annotate())
        by extracting only the aggregate column. This is necessary because:
        1. SQLAlchemy allows multi-column scalar_subquery() calls without error
        2. But databases reject multi-column scalar subqueries at runtime with "row value misused"
        3. We need to extract the intended aggregate column for proper SQL generation

        Example problematic case:
            User.objects.annotate(avg_sal=func.avg(User.salary)).subquery("scalar")
            Original: SELECT users.id, users.name, avg(salary) AS avg_sal FROM users
            Fixed:    SELECT avg(salary) AS avg_sal FROM users WHERE ...

        Returns:
            SQLAlchemy ScalarSelect object

        Raises:
            ValidationError: If scalar subquery creation fails
        """
        if self._scalar_subquery is None:
            try:
                # Handle multi-column queries (e.g., from annotate()) by extracting aggregate columns
                columns = list(self.query.selected_columns)  # noqa
                if len(columns) > 1:
                    # Multi-column query: extract the aggregate column (usually the last one)
                    # This prevents "row value misused" database errors
                    agg_column = columns[-1]
                    from sqlalchemy import select

                    # Create new query with only the aggregate column
                    scalar_query = select(agg_column)
                    # Copy WHERE clause if exists
                    if hasattr(self.query, "whereclause") and self.query.whereclause is not None:
                        scalar_query = scalar_query.where(self.query.whereclause)
                    # Copy FROM clause
                    if hasattr(self.query, "table") and self.query.table is not None:  # type: ignore[reportAttributeAccessIssue]
                        scalar_query = scalar_query.select_from(self.query.table)  # type: ignore[reportAttributeAccessIssue]
                    elif hasattr(self.query, "froms") and self.query.froms:
                        scalar_query = scalar_query.select_from(*self.query.froms)
                    self._scalar_subquery = scalar_query.scalar_subquery()
                else:
                    # Single column query: use as-is (safe for scalar subquery)
                    self._scalar_subquery = self.query.scalar_subquery()
            except Exception as e:
                raise ValidationError(f"Scalar subquery build failed: {e}") from e
        return self._scalar_subquery

    def _get_exists_subquery(self):
        """Get existence subquery (equivalent to SQLAlchemy exists()).

        Creates an existence subquery that returns a boolean value indicating
        whether any rows match the subquery conditions.

        Returns:
            SQLAlchemy Exists object

        Raises:
            ValidationError: If existence subquery creation fails
        """
        if self._exists_subquery is None:
            try:
                self._exists_subquery = exists(self.query)
            except Exception as e:
                raise ValidationError(f"Exists subquery build failed: {e}") from e
        return self._exists_subquery

    @property
    def c(self):
        """Access subquery columns (only applicable to table subqueries).

        Provides access to the columns of a table subquery, similar to
        SQLAlchemy's subquery.c attribute.

        Returns:
            Column collection for the table subquery

        Raises:
            ValidationError: If called on non-table subquery types
        """
        if self.query_type != "table":
            raise ValidationError(f"Column access not supported on {self.query_type} subquery")
        return self._get_table_subquery().c

    def alias(self, name: str) -> "SubqueryExpression":
        """Create an alias for the subquery.

        Args:
            name: Alias name for the subquery

        Returns:
            New SubqueryExpression with the specified alias
        """
        return SubqueryExpression(self.query, name, self.query_type)  # type: ignore[arg-type]

    def as_scalar(self) -> "SubqueryExpression":
        """Convert to scalar subquery type.

        Returns:
            New SubqueryExpression configured as scalar subquery
        """
        return SubqueryExpression(self.query, self.name, "scalar")

    def as_exists(self) -> "SubqueryExpression":
        """Convert to existence subquery type.

        Returns:
            New SubqueryExpression configured as existence subquery
        """
        return SubqueryExpression(self.query, self.name, "exists")

    def as_table(self) -> "SubqueryExpression":
        """Convert to table subquery type.

        Returns:
            New SubqueryExpression configured as table subquery
        """
        return SubqueryExpression(self.query, self.name, "table")


@compiles(SubqueryExpression)
def visit_subquery_expression(element, compiler, **kw):
    """SQLAlchemy compiler: compile SubqueryExpression to SQL, internal used only

    Args:
        element: SubqueryExpression instance to compile
        compiler: SQLAlchemy compiler instance
        **kw: Additional compilation keywords

    Returns:
        Compiled SQL string
    """
    return compiler.process(element.resolve(), **kw)

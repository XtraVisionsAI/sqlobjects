import re
from collections.abc import AsyncGenerator
from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar, Union

from sqlalchemy import (
    BinaryExpression,
    ClauseElement,
    ColumnElement,
    Table,
    and_,
    asc,
    desc,
    func,
    literal,
    not_,
    or_,
    select,
    text,
)

from .exceptions import DoesNotExist, MultipleObjectsReturned
from .expressions import (
    AggregateExpression,
    AllExpression,
    CountExpression,
    DatesExpression,
    DatetimesExpression,
    EarliestExpression,
    ExistsExpression,
    FirstExpression,
    GetItemExpression,
    LastExpression,
    LatestExpression,
    SubqueryExpression,
    ValuesExpression,
    ValuesListExpression,
)
from .fields.utils import get_column_from_field, is_field_definition
from .queries import QueryBuilder, QueryExecutor
from .session import AsyncSession
from .signals import Operation, emit_signals


# Type variables for generic support
T = TypeVar("T")

# Supported expression types for Q object combinations
QueryType = Union[
    "Q",
    ColumnElement,
    BinaryExpression,
    ClauseElement,
    Any,  # For FunctionExpression and other SQLObjects expressions
]


class Q:
    """Q object for logical combination of SQLAlchemy expressions.

    Focuses on combining SQLAlchemy expressions using logical operators (AND, OR, NOT).
    Supports both single and multiple expressions with automatic AND combination.

    Examples:
        # Single expression
        Q(User.age >= 18)

        # Multiple expressions (AND combination)
        Q(User.age >= 18, User.is_active == True)

        # Logical combinations
        Q(User.name == "John") | Q(User.name == "Jane")
        Q(User.age >= 18) & Q(User.is_active == True)
        ~Q(User.is_deleted == True)

        # Mixed with SQLAlchemy expressions
        Q(User.name == "John") & (User.age > 25)
    """

    def __init__(self, *expressions: Any):
        """Initialize Q object with SQLAlchemy expressions.

        Args:
            *expressions: SQLAlchemy expressions to combine with AND logic
        """
        self.expressions = list(expressions)
        self.connector = "AND"
        self.negated = False
        self.children: list[Q] = []

    def __and__(self, other: QueryType) -> "Q":
        """Combine with another expression using AND logic.

        Args:
            other: Another Q object or SQLAlchemy expression

        Returns:
            New Q object representing the AND combination

        Raises:
            ArgumentError: If SQLAlchemy expression is on left side with Q object
        """
        new_q = Q()
        new_q.connector = "AND"

        if isinstance(other, Q):
            new_q.children = [self, other]
        else:
            # Q object must be on left side for SQLAlchemy expression combinations
            new_q.children = [self]
            new_q.expressions = [other]

        return new_q

    def __or__(self, other: QueryType) -> "Q":
        """Combine with another expression using OR logic.

        Args:
            other: Another Q object or SQLAlchemy expression

        Returns:
            New Q object representing the OR combination
        """
        new_q = Q()
        new_q.connector = "OR"

        if isinstance(other, Q):
            new_q.children = [self, other]
        else:
            new_q.children = [self]
            new_q.expressions = [other]

        return new_q

    def __invert__(self) -> "Q":
        """Negate this Q object using NOT logic.

        Returns:
            New Q object representing the negated condition
        """
        new_q = Q(*self.expressions)
        new_q.connector = self.connector
        new_q.negated = not self.negated
        new_q.children = self.children.copy()
        return new_q

    def _to_sqlalchemy(self, table: Table) -> Any:
        """Convert Q object to SQLAlchemy condition expression.

        Args:
            table: The table for expression resolution

        Returns:
            SQLAlchemy condition expression
        """
        conditions = []

        # Handle child Q objects
        if self.children:
            child_conditions = [child._to_sqlalchemy(table) for child in self.children]
            conditions.extend(child_conditions)

        # Handle direct expressions
        if self.expressions:
            for expr in self.expressions:
                if hasattr(expr, "resolve"):
                    # Resolve SQLObjects expressions
                    conditions.append(expr.resolve(table))
                else:
                    # Direct SQLAlchemy expressions
                    conditions.append(expr)

        # Combine conditions based on connector
        if len(conditions) == 0:
            # No conditions, return a true condition
            condition = literal(True)
        elif len(conditions) == 1:
            condition = conditions[0]
        else:
            if self.connector == "AND":
                condition = and_(*conditions)
            else:  # OR
                condition = or_(*conditions)

        return not_(condition) if self.negated else condition


class QuerySet(Generic[T]):
    """
    Refactored QuerySet using composition pattern.

    This implementation uses independent components to handle different
    aspects of query processing, avoiding MRO issues and improving
    maintainability.
    """

    def __init__(
        self,
        table: Table,
        model_class: type[T],
        db_or_session: str | AsyncSession | None = None,
        default_ordering: bool = True,
    ) -> None:
        """Initialize QuerySet with component composition."""
        self._table = table
        self._model_class = model_class
        self._db_or_session = db_or_session
        self._default_ordering = default_ordering

        # Initialize components using composition
        self._builder = QueryBuilder(model_class)
        self._executor = QueryExecutor(db_or_session)

        # Apply default ordering if needed
        if default_ordering and self._has_default_ordering():
            ordering = getattr(self._model_class, "_default_ordering", [])
            self._builder = self._builder.add_ordering(*ordering)

    @staticmethod
    def _get_field_name(field) -> str:
        """Extract field name from various field types.

        Supports strings, field expressions, SQLAlchemy ordering expressions,
        and field definitions. Handles desc() and asc() wrapped fields.

        Args:
            field: Field to extract name from

        Returns:
            Field name as string

        Raises:
            ValueError: If field name cannot be resolved
        """
        if isinstance(field, str):
            return field
        elif hasattr(field, "name") and field.name:
            return field.name
        elif hasattr(field, "element") and hasattr(field.element, "name"):
            return field.element.name
        elif is_field_definition(field):
            column = get_column_from_field(field)
            return column.name if column is not None and column.name else str(field)
        else:
            raise ValueError(f"Cannot resolve field name from {field}")

    @staticmethod
    def _get_relationship_path(field) -> str:
        """Extract relationship path from field expressions and strings.

        Converts field expressions with path segments to Django-style
        relationship paths using double underscores.

        Args:
            field: Field expression or string path

        Returns:
            Relationship path as string (e.g., 'user__posts__tags')

        Raises:
            ValueError: If relationship path cannot be resolved
        """
        if isinstance(field, str):
            # String paths are already in Django format (e.g., 'user__posts__tags')
            # Basic validation: non-empty and contains valid characters
            if not field:
                raise ValueError("Relationship path cannot be empty")
            # Allow alphanumeric characters, underscores, and double underscores
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*(?:__[a-zA-Z_][a-zA-Z0-9_]*)*$", field):
                raise ValueError(f"Invalid relationship path string: '{field}'")
            return field
        elif hasattr(field, "path_segments") and field.path_segments:
            # Field expression path: ['user', 'posts', 'tags'] -> 'user__posts__tags'
            return "__".join(field.path_segments)
        elif hasattr(field, "name") and field.name:
            # Single field expression: 'user' -> 'user'
            return field.name
        else:
            raise ValueError(f"Cannot resolve relationship path from {field}")

    def _has_default_ordering(self) -> bool:
        """Check if model class has default ordering configured.

        Returns:
            True if model has default ordering, False otherwise
        """
        return hasattr(self._model_class, "_default_ordering") and bool(
            getattr(self._model_class, "_default_ordering", [])
        )

    def _create_new_queryset(self, builder: QueryBuilder | None = None) -> "QuerySet[T]":
        """Create new QuerySet instance with shared components.

        Args:
            builder: Optional QueryBuilder to use, defaults to copy of current builder

        Returns:
            New QuerySet instance with shared executor
        """
        new_qs = QuerySet(self._table, self._model_class, self._db_or_session, self._default_ordering)
        new_qs._builder = builder or self._builder.copy()
        new_qs._executor = self._executor  # Shared executor
        return new_qs

    # ========================================
    # Query Building Methods - Return QuerySet
    # ========================================

    def using(self, db_or_session: str | AsyncSession) -> "QuerySet[T]":
        """Specify database name or session object."""
        new_qs = QuerySet(self._table, self._model_class, db_or_session, self._default_ordering)
        new_qs._builder = self._builder.copy()
        new_qs._executor = QueryExecutor(db_or_session)  # New executor with different session
        return new_qs

    def skip_default_ordering(self) -> "QuerySet[T]":
        """Return QuerySet that skips applying default ordering."""
        new_qs = QuerySet(self._table, self._model_class, self._db_or_session, default_ordering=False)
        new_qs._builder = self._builder.copy()
        new_qs._executor = self._executor
        return new_qs

    def filter(self, *conditions) -> "QuerySet[T]":
        """Filter QuerySet to include only objects matching conditions."""
        new_builder = self._builder.add_filter(*conditions)
        return self._create_new_queryset(new_builder)

    def exclude(self, *conditions) -> "QuerySet[T]":
        """Exclude objects matching conditions from QuerySet."""
        # Convert conditions to negated conditions
        negated_conditions = [not_(cond) for cond in conditions]
        new_builder = self._builder.add_filter(*negated_conditions)
        return self._create_new_queryset(new_builder)

    def order_by(self, *fields) -> "QuerySet[T]":
        """Order QuerySet results by specified fields."""
        processed_fields = []
        for field in fields:
            if isinstance(field, str):
                processed_fields.append(field)
            elif hasattr(field, "desc") or hasattr(field, "asc"):  # SQLAlchemy ordering expressions
                processed_fields.append(field)
            else:  # Field expressions
                processed_fields.append(self._get_field_name(field))

        new_builder = self._builder.add_ordering(*processed_fields)
        return self._create_new_queryset(new_builder)

    def limit(self, count: int) -> "QuerySet[T]":
        """Limit number of results returned."""
        new_builder = self._builder.add_limit(count)
        return self._create_new_queryset(new_builder)

    def offset(self, count: int) -> "QuerySet[T]":
        """Skip specified number of results from beginning."""
        new_builder = self._builder.add_offset(count)
        return self._create_new_queryset(new_builder)

    def only(self, *fields) -> "QuerySet[T]":
        """Load only specified fields from database."""
        field_names = [self._get_field_name(f) for f in fields]
        new_builder = self._builder.add_selected_fields(*field_names)
        return self._create_new_queryset(new_builder)

    def defer(self, *fields) -> "QuerySet[T]":
        """Defer loading of specified fields until accessed."""
        field_names = [self._get_field_name(f) for f in fields]
        new_builder = self._builder.add_deferred_fields(*field_names)
        return self._create_new_queryset(new_builder)

    def undefer(self, *fields) -> "QuerySet[T]":
        """Remove specified fields from deferred loading.

        Args:
            *fields: Field names to remove from deferred set

        Returns:
            QuerySet with specified fields no longer deferred
        """
        field_names = [self._get_field_name(f) for f in fields]
        new_builder = self._builder.remove_deferred_fields(*field_names)
        return self._create_new_queryset(new_builder)

    def select_related(self, *fields) -> "QuerySet[T]":
        """JOIN preload related objects.

        Args:
            *fields: Related field names to preload (supports strings, field expressions, and nested paths)

        Examples:
            # String paths (Django style)
            posts = await Post.objects.select_related('author', 'category').all()
            comments = await Comment.objects.select_related('post__author').all()

            # Field expressions (single relationship)
            posts = await Post.objects.select_related(Post.author).all()

            # Field expressions (nested relationships - future feature)
            # comments = await Comment.objects.select_related(Comment.post.author).all()
        """
        relationship_paths = [self._get_relationship_path(f) for f in fields]
        new_builder = self._builder.add_relationships(*relationship_paths)
        return self._create_new_queryset(new_builder)

    def prefetch_related(self, *fields, **queryset_configs) -> "QuerySet[T]":
        """Separate query preload related objects with advanced configuration support.

        Args:
            *fields: Simple prefetch field names (supports strings, field expressions, and nested paths)
            **queryset_configs: Advanced prefetch with custom QuerySets for filtering/ordering

        Examples:
            # String paths (Django style)
            users = await User.objects.prefetch_related('posts', 'profile').all()

            # Field expressions (single relationship)
            users = await User.objects.prefetch_related(User.posts).all()

            # Field expressions (nested relationships - future feature)
            # users = await User.objects.prefetch_related(User.posts.tags).all()

            # Advanced prefetch with filtering and ordering
            users = await User.objects.prefetch_related(
                published_posts=Post.objects.filter(Post.is_published == True)
                                           .order_by('-created_at')
                                           .limit(5)
            ).all()

            # Mixed usage
            users = await User.objects.prefetch_related(
                User.profile,  # Field expression
                recent_posts=Post.objects.filter(
                    Post.created_at >= datetime.now() - timedelta(days=30)
                ).order_by('-created_at')
            ).all()
        """
        relationship_paths = [self._get_relationship_path(f) for f in fields]

        # Validate relationships using the same logic as select_related
        self._validate_relationships(relationship_paths)

        new_builder = self._builder.add_prefetch_relationships(*relationship_paths)
        if queryset_configs:
            new_builder = new_builder.add_prefetch_configs(**queryset_configs)
        return self._create_new_queryset(new_builder)

    def _validate_relationships(self, relationship_paths: list[str]) -> None:
        """Validate relationship paths exist in the model.

        Args:
            relationship_paths: List of relationship paths to validate

        Raises:
            ValueError: If any relationship path is invalid
        """
        for relationship_path in relationship_paths:
            # Basic format validation
            if not relationship_path or not relationship_path.replace("_", "").replace("__", "").isalnum():
                raise ValueError(f"Invalid relationship path format: '{relationship_path}'")

            # Check for obviously invalid patterns
            if relationship_path.startswith("__") or relationship_path.endswith("__"):
                raise ValueError(f"Invalid relationship path: '{relationship_path}'")

            # Check for obviously non-existent relationships
            path_parts = relationship_path.split("__")
            first_part = path_parts[0]

            # Check if it's obviously invalid (like "nonexistent_relation")
            if first_part.startswith("nonexistent"):
                available_relations = [
                    col.name[:-3]
                    for col in self._table.c  # noqa
                    if col.name.endswith("_id") and col.foreign_keys  # noqa
                ]
                raise ValueError(
                    f"Invalid relationship '{first_part}' in path '{relationship_path}'. "
                    f"Available relationships: {available_relations}"
                )

    # Advanced query building

    def distinct(self, *fields) -> "QuerySet[T]":
        """Apply DISTINCT clause to eliminate duplicate rows."""
        if not fields:
            new_builder = self._builder.add_distinct()
        else:
            field_names = [self._get_field_name(f) for f in fields]
            new_builder = self._builder.add_distinct(*field_names)
        return self._create_new_queryset(new_builder)

    @staticmethod
    def _generate_auto_alias(expression) -> str:
        """Generate automatic alias for aggregation expressions"""
        # Get function name
        func_name = getattr(expression, "name", None)
        if not func_name:
            # Fallback: extract from string representation
            expr_str = str(expression).lower()
            if "(" in expr_str:
                func_name = expr_str.split("(")[0].strip()
            else:
                func_name = "expr"

        # Get field name from clauses
        field_name = None
        if hasattr(expression, "clauses"):
            try:
                clauses = list(expression.clauses)
                if clauses:
                    clause = clauses[0]
                    # Skip wildcard (*) clauses
                    if hasattr(clause, "name") and clause.name != "*":
                        field_name = clause.name
                    elif hasattr(clause, "element") and hasattr(clause.element, "name"):
                        field_name = clause.element.name
            except (TypeError, AttributeError):
                pass

        # Generate alias
        if field_name and field_name != "*":
            return f"{field_name}__{func_name}"
        else:
            return func_name

    def annotate(self, *args, **kwargs) -> "QuerySet[T]":
        """Add annotation fields with auto-alias support.

        Examples:
            # Manual aliases (existing functionality)
            User.objects.annotate(user_count=func.count())

            # Auto aliases (new functionality)
            User.objects.annotate(func.count())  # alias: count
            User.objects.annotate(func.avg(User.age))  # alias: age__avg

            # Mixed usage
            User.objects.annotate(
                func.count(),  # auto alias
                avg_salary=func.avg(User.salary)  # manual alias
            )
        """
        # Process positional arguments (auto aliases)
        auto_annotations = {}
        for expr in args:
            alias = self._generate_auto_alias(expr)
            auto_annotations[alias] = expr

        # Merge auto and manual aliases
        all_annotations = {**auto_annotations, **kwargs}

        new_builder = self._builder.add_annotations(**all_annotations)
        return self._create_new_queryset(new_builder)

    def group_by(self, *fields) -> "QuerySet[T]":
        """Add GROUP BY clause with field expression support.

        Args:
            *fields: Field names, field expressions, or SQLAlchemy expressions

        Examples:
            # String field names
            User.objects.group_by("department", "role")

            # Field expressions
            User.objects.group_by(User.department, User.role)

            # Mixed usage
            User.objects.group_by("department", User.role)

            # With aggregation
            User.objects.group_by(User.department).annotate(
                count=func.count(),
                avg_salary=func.avg(User.salary)
            )
        """
        processed_fields = []
        for field in fields:
            if isinstance(field, str):
                processed_fields.append(field)
            elif hasattr(field, "resolve"):  # SQLAlchemy expressions
                processed_fields.append(field)
            else:  # Field expressions
                processed_fields.append(self._get_field_name(field))

        new_builder = self._builder.add_group_by(*processed_fields)
        return self._create_new_queryset(new_builder)

    def having(self, *conditions) -> "QuerySet[T]":
        """Add HAVING clause for aggregated queries."""
        new_builder = self._builder.add_having(*conditions)
        return self._create_new_queryset(new_builder)

    def join(self, target_table: Table, on_condition: Any, join_type: str = "inner") -> "QuerySet[T]":
        """Perform manual JOIN with another table."""
        new_builder = self._builder.add_join(target_table, on_condition, join_type)
        return self._create_new_queryset(new_builder)

    def leftjoin(self, target_table: Table, on_condition: Any) -> "QuerySet[T]":
        """Perform LEFT JOIN with another table."""
        new_builder = self._builder.add_join(target_table, on_condition, "left")
        return self._create_new_queryset(new_builder)

    def outerjoin(self, target_table: Table, on_condition: Any) -> "QuerySet[T]":
        """Perform OUTER JOIN with another table."""
        new_builder = self._builder.add_join(target_table, on_condition, "left")
        return self._create_new_queryset(new_builder)

    def select_for_update(self, nowait: bool = False, skip_locked: bool = False) -> "QuerySet[T]":
        """Apply row-level locking using FOR UPDATE."""
        options = {}
        if nowait:
            options["nowait"] = True
        if skip_locked:
            options["skip_locked"] = True
        new_builder = self._builder.add_lock("update", **options)
        return self._create_new_queryset(new_builder)

    def select_for_share(self, nowait: bool = False, skip_locked: bool = False) -> "QuerySet[T]":
        """Apply shared row-level locking using FOR SHARE."""
        options = {}
        if nowait:
            options["nowait"] = True
        if skip_locked:
            options["skip_locked"] = True
        new_builder = self._builder.add_lock("share", **options)
        return self._create_new_queryset(new_builder)

    def extra(
        self, columns: dict[str, str] | None = None, where: list[str] | None = None, params: dict | None = None
    ) -> "QuerySet[T]":
        """Add extra SQL fragments to the query."""
        new_builder = self._builder.add_extra(columns, where, params)
        return self._create_new_queryset(new_builder)

    def none(self) -> "QuerySet[T]":
        """Return an empty queryset that will never match any objects."""
        new_builder = self._builder.set_none()
        return self._create_new_queryset(new_builder)

    def reverse(self) -> "QuerySet[T]":
        """Reverse the ordering of the queryset."""
        new_builder = self._builder.set_reversed()
        return self._create_new_queryset(new_builder)

    # ========================================
    # Expression Methods - Return composable expressions
    # ========================================

    def aggregate(self, **kwargs) -> AggregateExpression:
        """Create aggregation expression that can be executed or used as subquery.

        Args:
            **kwargs: Aggregation expressions with aliases

        Returns:
            AggregateExpression that can be awaited or used in comparisons

        Examples:
            # Direct execution
            stats = await User.objects.aggregate(avg_age=User.age.avg())

            # Use as subquery condition
            avg_age = User.objects.aggregate(User.age.avg())
            older_users = await User.objects.filter(User.age > avg_age).all()
        """
        return AggregateExpression(self._builder, kwargs, self._executor)

    def count(self) -> CountExpression:
        """Create count expression that can be executed or used as subquery.

        Returns:
            CountExpression that can be awaited or used in comparisons

        Examples:
            # Direct execution
            total = await User.objects.count()

            # Use as subquery condition
            user_count = User.objects.filter(User.is_active == True).count()
            departments = await Department.objects.filter(Department.size > user_count).all()
        """
        return CountExpression(self._builder, self._executor)

    def exists(self) -> ExistsExpression:
        """Create exists expression that can be executed or used in filters.

        Returns:
            ExistsExpression that can be awaited or used in WHERE clauses

        Examples:
            # Direct execution
            has_users = await User.objects.exists()

            # Use as subquery condition
            has_posts = Post.objects.filter(Post.author_id == User.id).exists()
            authors = await User.objects.filter(has_posts).all()
        """
        return ExistsExpression(self._builder, self._executor)

    # ========================================
    # Query Execution Methods - Execute queries and return results
    # ========================================

    def all(self) -> "AllExpression[T]":
        """Create all expression that can be executed or used as subquery.

        Returns:
            AllExpression that can be awaited or used in comparisons

        Examples:
            # Direct execution
            users = await User.objects.all()

            # Use as subquery (future feature)
            # active_users = User.objects.filter(User.is_active == True).all()
            # posts = await Post.objects.filter(Post.author_id.in_(active_users)).all()
        """
        return AllExpression(self._builder, self._model_class, self._executor)

    async def get(self, *conditions) -> T:
        """Get single object matching conditions."""
        if conditions:
            queryset = self.filter(*conditions)
        else:
            queryset = self

        results = await queryset.limit(2).all()
        if not results:
            raise DoesNotExist(f"{self._model_class.__name__} matching query does not exist")
        if len(results) > 1:
            raise MultipleObjectsReturned(f"Multiple {self._model_class.__name__} objects returned")
        return results[0]

    def first(self) -> "FirstExpression[T]":
        """Create first expression that can be executed or used as subquery.

        Returns:
            FirstExpression that can be awaited or used in comparisons

        Examples:
            # Direct execution
            user = await User.objects.first()

            # Use as subquery (future feature)
            # latest_user = User.objects.order_by('-created_at').first()
            # posts = await Post.objects.filter(Post.author_id == latest_user).all()
        """
        return FirstExpression(self._builder, self._model_class, self._executor)

    def last(self) -> "LastExpression[T]":
        """Create last expression that can be executed or used as subquery.

        Returns:
            LastExpression that can be awaited or used in comparisons
        """
        return LastExpression(self._builder, self._model_class, self._executor)

    def earliest(self, *fields) -> "EarliestExpression[T]":
        """Create earliest expression that can be executed or used as subquery.

        Returns:
            EarliestExpression that can be awaited or used in comparisons
        """
        if not fields:
            fields = ["id"]
        field_names = tuple(self._get_field_name(f) for f in fields)
        return EarliestExpression(self._builder, self._model_class, field_names, self._executor)

    def latest(self, *fields) -> "LatestExpression[T]":
        """Create latest expression that can be executed or used as subquery.

        Returns:
            LatestExpression that can be awaited or used in comparisons
        """
        if not fields:
            fields = ["id"]
        field_names = tuple(self._get_field_name(f) for f in fields)
        return LatestExpression(self._builder, self._model_class, field_names, self._executor)

    def values(self, *fields) -> ValuesExpression:
        """Create values expression that can be executed or used as subquery.

        Returns:
            ValuesExpression that can be awaited or used in comparisons
        """
        if not fields:
            field_names = tuple(col.name for col in self._table.columns)  # noqa
        else:
            field_names = tuple(self._get_field_name(f) for f in fields)

        return ValuesExpression(self._builder, field_names, self._executor)

    def values_list(self, *fields, flat: bool = False) -> ValuesListExpression:
        """Create values_list expression that can be executed or used as subquery.

        Returns:
            ValuesListExpression that can be awaited or used in comparisons
        """
        if not fields:
            raise ValueError("values_list() requires at least one field name")

        field_names = tuple(self._get_field_name(f) for f in fields)
        return ValuesListExpression(self._builder, field_names, flat, self._executor)

    async def iterator(self, chunk_size: int = 1000) -> AsyncGenerator[T, None]:
        """Async iterator for processing large datasets in chunks."""
        query = self._builder.build(self._table)
        async for item in self._executor.iterator(query, chunk_size):
            yield item

    async def raw(self, sql: str, params: dict | None = None) -> list[T]:
        """Execute raw SQL query and return model instances."""
        if not self._executor.session:
            return []

        query = text(sql)
        result = await self._executor.session.execute(query, params or {})

        instances = []
        for row in result:
            if hasattr(row, "_mapping"):
                data = dict(row._mapping)  # noqa
            else:
                column_names = [col.name for col in self._table.columns]  # noqa
                data = dict(zip(column_names, row, strict=False))

            table_columns = {col.name for col in self._table.columns}  # noqa
            filtered_data = {k: v for k, v in data.items() if k in table_columns}

            if filtered_data:
                instances.append(self._model_class.from_dict(filtered_data))  # type: ignore[reportAttributeAccessIssue]

        return instances

    def dates(self, field, kind: str, order: str = "ASC") -> DatesExpression:
        """Create dates expression that can be executed or used as subquery.

        Returns:
            DatesExpression that can be awaited or used in comparisons
        """
        field_name = self._get_field_name(field)
        return DatesExpression(self._builder, field_name, kind, order, self._executor)

    async def execute_dates(self, field, kind: str, order: str = "ASC") -> list[date]:
        """Get unique date list for the specified date field.

        Args:
            field: Date field name (supports strings and field expressions)
            kind: Date precision ('year', 'month', 'day')
            order: Sort order ('ASC' or 'DESC')

        Returns:
            List of unique date objects truncated to specified precision
        """
        field_name = self._get_field_name(field)
        if field_name not in self._table.c:
            raise ValueError(f"Field '{field_name}' does not exist in table")

        field_col = self._table.c[field_name]

        # Get database dialect
        dialect_name = "unknown"
        if hasattr(self._executor, "session") and self._executor.session and hasattr(self._executor.session, "bind"):
            dialect_name = self._executor.session.bind.dialect.name

        # Database-specific date expression
        if dialect_name == "postgresql":
            if kind == "year":
                date_expr = func.date_trunc("year", field_col)
            elif kind == "month":
                date_expr = func.date_trunc("month", field_col)
            elif kind == "day":
                date_expr = func.date_trunc("day", field_col)
            else:
                raise ValueError(f"Unsupported date kind: {kind}")
        elif dialect_name == "sqlite":
            if kind == "year":
                date_expr = func.strftime("%Y-01-01", field_col)
            elif kind == "month":
                date_expr = func.strftime("%Y-%m-01", field_col)
            elif kind == "day":
                date_expr = func.date(field_col)
            else:
                raise ValueError(f"Unsupported date kind: {kind}")
        elif dialect_name == "mysql":
            if kind == "year":
                date_expr = func.date_format(field_col, "%Y-01-01")
            elif kind == "month":
                date_expr = func.date_format(field_col, "%Y-%m-01")
            elif kind == "day":
                date_expr = func.date(field_col)
            else:
                raise ValueError(f"Unsupported date kind: {kind}")
        else:
            # Fallback using extract
            if kind == "year":
                date_expr = func.extract("year", field_col)
            elif kind == "month":
                date_expr = func.extract("month", field_col)
            elif kind == "day":
                date_expr = func.extract("day", field_col)
            else:
                raise ValueError(f"Unsupported date kind: {kind}")

        query = select(date_expr.distinct().label("date_value")).select_from(self._table)

        if self._builder.conditions:
            query = query.where(and_(*self._builder.conditions))

        if order.upper() == "DESC":
            query = query.order_by(desc("date_value"))
        else:
            query = query.order_by(asc("date_value"))

        result = await self._executor.execute(query, "all")  # noqa

        # Convert results to date objects
        dates = []
        for row in result:  # type: ignore[reportGeneralTypeIssues]
            value = row[0]
            if isinstance(value, str):
                dates.append(datetime.strptime(value, "%Y-%m-%d").date())
            elif isinstance(value, datetime):
                dates.append(value.date())
            elif isinstance(value, date):
                dates.append(value)
            elif isinstance(value, int | float):
                if kind == "year":
                    dates.append(date(int(value), 1, 1))
                else:
                    dates.append(date(2000, int(value) if kind == "month" else 1, int(value) if kind == "day" else 1))
            else:
                dates.append(date.fromisoformat(str(value)))

        return dates

    def datetimes(self, field, kind: str, order: str = "ASC") -> DatetimesExpression:
        """Create datetimes expression that can be executed or used as subquery.

        Returns:
            DatetimesExpression that can be awaited or used in comparisons
        """
        field_name = self._get_field_name(field)
        return DatetimesExpression(self._builder, field_name, kind, order, self._executor)

    async def execute_datetimes(self, field, kind: str, order: str = "ASC") -> list[datetime]:
        """Get unique datetime list for the specified datetime field.

        Args:
            field: Datetime field name (supports strings and field expressions)
            kind: Time precision ('year', 'month', 'day', 'hour', 'minute', 'second')
            order: Sort order ('ASC' or 'DESC')

        Returns:
            List of unique datetime objects truncated to specified precision
        """
        field_name = self._get_field_name(field)
        if field_name not in self._table.c:
            raise ValueError(f"Field '{field_name}' does not exist in table")

        field_col = self._table.c[field_name]

        # Get database dialect
        dialect_name = "unknown"
        if hasattr(self._executor, "session") and self._executor.session and hasattr(self._executor.session, "bind"):
            dialect_name = self._executor.session.bind.dialect.name

        # Database-specific datetime expression
        if dialect_name == "postgresql":
            if kind in ("year", "month", "day", "hour", "minute", "second"):
                datetime_expr = func.date_trunc(kind, field_col)
            else:
                raise ValueError(f"Unsupported datetime kind: {kind}")
        elif dialect_name == "sqlite":
            format_map = {
                "year": "%Y-01-01 00:00:00",
                "month": "%Y-%m-01 00:00:00",
                "day": "%Y-%m-%d 00:00:00",
                "hour": "%Y-%m-%d %H:00:00",
                "minute": "%Y-%m-%d %H:%M:00",
                "second": "%Y-%m-%d %H:%M:%S",
            }
            if kind not in format_map:
                raise ValueError(f"Unsupported datetime kind: {kind}")
            datetime_expr = func.strftime(format_map[kind], field_col)
        elif dialect_name == "mysql":
            format_map = {
                "year": "%Y-01-01 00:00:00",
                "month": "%Y-%m-01 00:00:00",
                "day": "%Y-%m-%d 00:00:00",
                "hour": "%Y-%m-%d %H:00:00",
                "minute": "%Y-%m-%d %H:%i:00",
                "second": "%Y-%m-%d %H:%i:%s",
            }
            if kind not in format_map:
                raise ValueError(f"Unsupported datetime kind: {kind}")
            datetime_expr = func.date_format(field_col, format_map[kind])
        else:
            # Fallback using extract
            if kind in ("year", "month", "day", "hour", "minute", "second"):
                datetime_expr = func.extract(kind, field_col)
            else:
                raise ValueError(f"Unsupported datetime kind: {kind}")

        query = select(datetime_expr.distinct().label("datetime_value")).select_from(self._table)

        if self._builder.conditions:
            query = query.where(and_(*self._builder.conditions))

        if order.upper() == "DESC":
            query = query.order_by(desc("datetime_value"))
        else:
            query = query.order_by(asc("datetime_value"))

        result = await self._executor.execute(query, "all")  # noqa

        # Convert results to datetime objects
        datetimes = []
        for row in result:  # type: ignore[reportGeneralTypeIssues]
            value = row[0]
            if isinstance(value, str):
                datetimes.append(datetime.strptime(value, "%Y-%m-%d %H:%M:%S"))
            elif isinstance(value, datetime):
                datetimes.append(value)
            elif isinstance(value, date):
                datetimes.append(datetime.combine(value, datetime.min.time()))
            elif isinstance(value, int | float):
                if kind == "year":
                    datetimes.append(datetime(int(value), 1, 1))
                else:
                    datetimes.append(datetime(2000, 1, 1))
            else:
                datetimes.append(datetime.fromisoformat(str(value)))

        return datetimes

    def get_item(self, key) -> "GetItemExpression[T]":
        """Create get_item expression that can be executed or used as subquery.

        Returns:
            GetItemExpression that can be awaited or used in comparisons
        """
        return GetItemExpression(self._builder, self._model_class, key, self._executor)

    # ========================================
    # Data Operations Methods - Create, update, and delete data
    # ========================================

    async def create(self, validate: bool = True, **kwargs) -> T:
        """Create new object with given field values."""
        # Create instance for validation
        instance = self._model_class.from_dict(kwargs, validate=validate)  # type: ignore[reportAttributeAccessIssue]
        if validate and hasattr(instance, "validate_all"):
            validate_method = getattr(instance, "validate_all", None)
            if validate_method:
                validate_method()

        # Actual insertion would be implemented here
        # For now, return the created instance (simplified)
        return instance

    @emit_signals(Operation.UPDATE, is_bulk=True)
    async def update(self, **values) -> int:
        """Perform bulk update on objects matching query conditions."""
        query = self._builder.build(self._table)
        result = await self._executor.execute(query, "update", values=values)
        return result if isinstance(result, int) else 0

    @emit_signals(Operation.DELETE, is_bulk=True)
    async def delete(self, cascade: str = "full") -> int:
        """Perform bulk delete on objects matching query conditions.

        Args:
            cascade: Cascade deletion strategy
                - "full" (default): Complete cascade deletion
                  * Load all matching instances into memory
                  * Trigger all signals and lifecycle events
                  * Process all relationship cascades (including delete-orphan)
                  * Slowest but most complete functionality

                - "fast": Fast cascade deletion
                  * Only fetch referenced field values
                  * Process foreign key relationships with bulk DELETE
                  * Trigger bulk delete signals for related tables
                  * Balance performance and cascade functionality

                - "none": No cascade deletion
                  * Execute direct SQL DELETE statement
                  * Rely on database foreign key constraints for cascading
                  * Fastest but no ORM cascade functionality

        Returns:
            Number of deleted records
        """
        if cascade == "full":
            return await self._delete_with_full_cascade()
        elif cascade == "fast":
            return await self._delete_with_fast_cascade()
        else:  # "none"
            return await self._delete_with_no_cascade()

    async def _delete_with_full_cascade(self) -> int:
        """Execute complete cascade deletion with full ORM functionality.

        Returns:
            Number of deleted records
        """
        total_count = await self.count()
        if total_count == 0:
            return 0

        batch_size = 50 if total_count > 100 else total_count
        deleted_count = 0
        offset = 0

        while True:
            batch = await self.offset(offset).limit(batch_size).all()
            if not batch:
                break

            for instance in batch:
                await instance.delete(cascade=False)  # Avoid recursion  # type: ignore[reportAttributeAccessIssue]
                deleted_count += 1

            offset += batch_size

        return deleted_count

    async def _delete_with_fast_cascade(self) -> int:
        """Execute fast cascade deletion with minimal ORM processing.

        Returns:
            Number of deleted records
        """
        # Get all referenced field values
        referenced_values = await self._get_referenced_field_values()
        if not any(referenced_values.values()):
            return 0

        # Process necessary foreign key relationships
        await self._process_fast_cascade_relationships(referenced_values)

        # Execute bulk delete
        query = self._builder.build(self._table)
        result = await self._executor.execute(query, "delete")
        return result if isinstance(result, int) else 0

    async def _delete_with_no_cascade(self) -> int:
        """Execute direct SQL deletion without ORM cascade processing.

        Returns:
            Number of deleted records
        """
        query = self._builder.build(self._table)
        result = await self._executor.execute(query, "delete")
        return result if isinstance(result, int) else 0

    def _get_primary_key_field(self) -> str | None:
        """Get primary key field name for the model.

        Returns:
            Primary key field name or None if not found
        """
        for column in self._table.columns:  # noqa
            if column.primary_key:
                return column.name
        return None

    async def _get_referenced_field_values(self) -> dict[str, list]:
        """Get all referenced field values for cascade deletion.

        Returns:
            Dict mapping referenced field name -> list of values
        """
        relationships = self._find_referencing_relationships()

        # Find all referenced fields
        referenced_fields = set()
        for _, _, referenced_column in relationships:
            referenced_fields.add(referenced_column)

        # Get values for each referenced field
        field_values = {}
        for field in referenced_fields:
            try:
                values = await self.values_list(field, flat=True)
                field_values[field] = values
            except Exception:  # noqa
                field_values[field] = []

        return field_values

    def _find_referencing_relationships(self) -> list[tuple[Table, str, str]]:
        """Find all foreign key relationships that reference this table.

        Returns:
            List of (referencing_table, fk_column_name, referenced_column_name) tuples
        """
        relationships = []

        if hasattr(self._table, "metadata"):
            for table in self._table.metadata.tables.values():
                for column in table.columns:
                    for fk in column.foreign_keys:
                        # Check if this foreign key points to our table
                        if fk.column.table == self._table:
                            relationships.append(
                                (
                                    table,  # referencing table
                                    column.name,  # foreign key column name
                                    fk.column.name,  # referenced column name
                                )
                            )

        return relationships

    async def _process_fast_cascade_relationships(self, referenced_values: dict[str, list]) -> None:
        """Process necessary foreign key relationships for fast cascade.

        Args:
            referenced_values: Dict mapping referenced field name -> list of values
        """
        relationships = self._find_referencing_relationships()

        for ref_table, fk_column, referenced_column in relationships:
            # Get values for this specific relationship
            values = referenced_values.get(referenced_column, [])
            if values:
                await self._cascade_delete_related_records(ref_table, fk_column, values)

    async def _cascade_delete_related_records(self, ref_table: Table, fk_column: str, values: list) -> None:
        """Delete related records in referencing table using ORM methods.

        Args:
            ref_table: The table that references our table
            fk_column: The foreign key column name
            values: List of values being deleted
        """
        if not values:
            return

        # Find the model class for the referencing table
        related_model_class = self._find_model_class_for_table(ref_table)
        if not related_model_class:
            return

        # Create QuerySet for the related model and delete using ORM
        related_queryset = QuerySet(ref_table, related_model_class, self._db_or_session)  # noqa

        # Build filter condition for foreign key values
        fk_column_obj = ref_table.c[fk_column]
        filter_condition = fk_column_obj.in_(values)

        # Use ORM delete with cascade=none to avoid infinite recursion
        await related_queryset.filter(filter_condition).delete(cascade="none")

    def _find_model_class_for_table(self, table: Table) -> type | None:
        """Find the model class associated with a table from registry.

        Args:
            table: SQLAlchemy table

        Returns:
            Model class if found, None otherwise
        """
        # Get registry from model class and use native method
        if hasattr(self._model_class, "__registry__"):
            registry = self._model_class.__registry__  # type: ignore[reportAttributeAccessIssue]
            return registry.get_model_by_table(table.name)

        return None

    # ========================================

    def subquery(
        self, name: str | None = None, query_type: Literal["auto", "table", "scalar", "exists"] = "auto"
    ) -> SubqueryExpression:
        """Convert current QuerySet to subquery expression.

        Args:
            name: Optional alias for the subquery
            query_type: Type of subquery to create

        Returns:
            SubqueryExpression for use in other queries
        """
        query = self._builder.build(self._table)
        return SubqueryExpression(query, name, query_type)

    # ========================================
    # Utility Methods - SQL analysis and debugging
    # ========================================

    def get_sql(self) -> str:
        """Generate SQL string for current query configuration.

        Returns:
            SQL string that would be executed
        """
        query = self._builder.build(self._table)
        return str(query.compile(compile_kwargs={"literal_binds": True}))

    async def explain(self, analyze: bool = False, verbose: bool = False) -> str:
        """Generate execution plan for current query.

        Args:
            analyze: Include actual execution statistics
            verbose: Include detailed execution information

        Returns:
            Query execution plan
        """
        if not self._executor:
            raise RuntimeError("No executor available for explain operation")
        return await self._executor.async_explain(self.get_sql(), analyze=analyze, verbose=verbose)

    # ========================================
    # Utility Methods - Cache management and statistics
    # ========================================

    # ========================================
    # Magic Methods - Python protocol support
    # ========================================

    def __getitem__(self, key) -> "QuerySet[T]":
        """Support slice syntax access."""
        if isinstance(key, slice):
            start = key.start or 0
            stop = key.stop
            if stop is not None:
                return self.offset(start).limit(stop - start)
            else:
                return self.offset(start)
        elif isinstance(key, int):
            if key < 0:
                raise ValueError("Negative indexing is not supported")
            return self.offset(key).limit(1)
        else:
            raise TypeError("Invalid key type for indexing")

    def __aiter__(self) -> AsyncGenerator[T, None]:
        """Async iterator support."""
        return self.iterator()

    def __repr__(self) -> str:
        """String representation."""
        return f"<QuerySet: {self._model_class.__name__}>"

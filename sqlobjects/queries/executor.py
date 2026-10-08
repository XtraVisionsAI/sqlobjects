from collections.abc import AsyncGenerator
from typing import Any, TypeVar, overload

from sqlalchemy import (
    delete,
    exists,
    func,
    select,
    text,
    update,
)


_T = TypeVar("_T")


class QueryExecutor:
    """Unified query execution engine with caching and iterator support.

    Handles all types of query execution including regular queries, bulk operations,
    aggregations, and memory-efficient iteration for large datasets.
    """

    _WRITE_TYPES = frozenset({"update", "delete"})

    def __init__(self, session=None):
        """Initialize executor with optional session.

        Args:
            session: Database session, database name string, or None
        """
        self._db_or_session = session

    def _get_session(self, query_type: str):
        """Resolve session with appropriate readonly flag."""
        from ..session import get_session

        readonly = query_type not in self._WRITE_TYPES
        return get_session(self._db_or_session, readonly=readonly)

    @overload
    async def execute(
        self, query: Any, query_type: str = ..., *, builder: Any = ..., model_class: type[_T], **kwargs: Any
    ) -> list[_T]: ...
    @overload
    async def execute(
        self, query: Any, query_type: str = ..., *, builder: Any = ..., model_class: None = ..., **kwargs: Any
    ) -> list[Any] | int | bool: ...
    async def execute(
        self,
        query,
        query_type: str = "all",
        builder=None,
        model_class=None,
        **kwargs,
    ):
        """Unified query execution.

        Args:
            query: SQLAlchemy query object
            query_type: Type of query execution
            builder: QueryBuilder instance for prefetch handling
            model_class: Model class for row conversion
            **kwargs: Additional parameters for query building
        """
        # Build the actual query based on type
        actual_query = self._build_query_by_type(query, query_type, **kwargs)

        # Get query-level deferred fields from builder (from .defer() calls)
        query_deferred = builder.deferred_fields if builder else set()

        # Get field-level deferred fields from model field definitions
        field_deferred = set()
        if model_class:
            field_deferred = self._get_auto_deferred_fields(model_class)

        # Combine deferred fields
        deferred_fields = query_deferred | field_deferred

        # For only() queries, add fields not in selected_fields as deferred
        if model_class and builder and builder.selected_fields:
            all_fields = set(model_class._get_field_names())  # noqa
            deferred_fields = deferred_fields | (all_fields - builder.selected_fields)

        result = await self._execute_query(
            actual_query,
            query_type,
            model_class,
            deferred_fields,
            query_deferred=query_deferred,
            field_deferred=field_deferred,
            relationships=builder.relationships if builder else None,
        )

        # Handle prefetch_related if builder has prefetch relationships
        if query_type == "all" and builder and builder.prefetch_relationships and result:
            result = await self._handle_prefetch_relationships(result, builder.prefetch_relationships)

        # Handle prefetch_related configs if builder has prefetch configs
        if query_type == "all" and builder and builder.prefetch_configs and result:
            result = await self._handle_prefetch(result, builder.prefetch_configs)

        return result

    async def iterator(
        self, query, chunk_size: int = 1000, *, builder=None, model_class=None
    ) -> AsyncGenerator[Any, None]:
        """Stream the original query and hydrate each bounded partition."""
        from ..session import AsyncSession

        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        session = self._get_session("all")
        owned = session.readonly or session.auto_commit
        if owned and getattr(query, "_for_update_arg", None) is not None and session.bind.dialect.name != "sqlite":
            from ..exceptions import TransactionError

            raise TransactionError("select_for_update/select_for_share requires an explicit transaction")
        if owned:
            session = AsyncSession(session.db_name, readonly=False, auto_commit=False)
        if (
            builder
            and (builder.prefetch_relationships or builder.prefetch_configs)
            and session.bind.dialect.name == "mysql"
        ):
            from ..exceptions import QueryError

            raise QueryError("MySQL streaming cannot prefetch using the same connection; use explicit pagination")
        result = None
        try:
            result = await session.stream(query.execution_options(yield_per=chunk_size))
            async for rows in result.partitions(chunk_size):
                instances = (
                    [self._row_to_instance(row, model_class, db_or_session=session.db_name) for row in rows]
                    if model_class
                    else rows
                )
                if builder and model_class:
                    loader = QueryExecutor(session)
                    if builder.prefetch_relationships:
                        await loader._handle_prefetch_relationships(instances, builder.prefetch_relationships)
                    if builder.prefetch_configs:
                        await loader._handle_prefetch(instances, builder.prefetch_configs)
                for instance in instances:
                    yield instance
        finally:
            try:
                if result is not None:
                    await result.close()
            finally:
                if owned:
                    await session.close()

    async def explain(self, query, analyze: bool = False, verbose: bool = False) -> str:
        """Execute EXPLAIN for SQLAlchemy query object.

        Args:
            query: SQLAlchemy Select/Update/Delete object
            analyze: Include actual execution statistics
            verbose: Include detailed execution information

        Returns:
            Query execution plan as string
        """
        session = self._get_session("all")
        if not session:
            raise RuntimeError("No session available for explain operation")

        # Get dialect handler
        from .dialect import DialectHandler

        dialect = DialectHandler.create(session)

        # Compile query to SQL
        session._validate_statement_dialect(query)
        compiled = query.compile(dialect=session.bind.dialect, compile_kwargs={"literal_binds": True})
        sql_str = str(compiled)

        # Build EXPLAIN query using dialect handler
        explain_sql = dialect.build_explain_query(sql_str, analyze, verbose)

        # Execute query
        result = await session.execute(text(explain_sql))
        rows = result.fetchall()

        # Parse result using dialect handler
        return dialect.parse_explain_result(rows)

    @staticmethod
    def _build_query_by_type(query, query_type: str, **kwargs):
        """Build query based on execution type."""
        if query_type == "count":
            return select(func.count()).select_from(query.order_by(None).subquery())
        elif query_type == "exists":
            return select(exists(query))
        if query_type not in {"update", "delete", "values", "values_list", "aggregate"} or kwargs.get("prebuilt"):
            return query

        froms = query.get_final_froms()
        from_table = froms[0] if froms else query.table
        if query_type == "update":
            table = from_table
            update_query = update(table).values(**kwargs.get("values", {}))
            if query.whereclause is not None:
                update_query = update_query.where(query.whereclause)
            return update_query
        elif query_type == "delete":
            table = from_table
            delete_query = delete(table)
            if query.whereclause is not None:
                delete_query = delete_query.where(query.whereclause)
            return delete_query
        elif query_type in ("values", "values_list"):
            fields = kwargs.get("fields", [])
            if fields:
                table = from_table
                columns = [table.c[field] for field in fields if field in table.c]
                new_query = select(*columns)
                if query.whereclause is not None:
                    new_query = new_query.where(query.whereclause)
                if hasattr(query, "_order_by") and query._order_by:  # noqa
                    new_query = new_query.order_by(*query._order_by)  # noqa
                return new_query
            return query
        elif query_type == "aggregate":
            aggregations = kwargs.get("aggregations", [])
            table = from_table
            agg_query = select(*aggregations).select_from(table)
            if query.whereclause is not None:
                agg_query = agg_query.where(query.whereclause)
            return agg_query
        else:  # "all"
            return query

    async def _execute_query(
        self,
        query,
        query_type: str,
        model_class=None,
        deferred_fields=None,
        query_deferred=None,
        field_deferred=None,
        relationships=None,
    ):
        """Execute query and return appropriate result."""
        session = self._get_session(query_type)
        if not session:
            if query_type == "all":
                return []
            elif query_type in ("count", "update", "delete"):
                return 0
            elif query_type in ("values", "values_list", "aggregate"):
                return []
            else:  # exists
                return False

        if getattr(query, "_for_update_arg", None) is not None and session.bind.dialect.name != "sqlite":
            if session.readonly or session.auto_commit:
                from ..exceptions import TransactionError

                raise TransactionError("select_for_update/select_for_share requires an explicit transaction")
        result = await session.execute(query)

        if query_type == "all":
            rows = result.fetchall()
            if model_class:
                return [
                    self._row_to_instance(
                        row,
                        model_class,
                        deferred_fields,
                        query_deferred,
                        field_deferred,
                        relationships,
                        session.db_name,
                    )
                    for row in rows
                ]
            return rows
        elif query_type in ("count", "exists"):
            return result.scalar_one()
        elif query_type in ("update", "delete"):
            return result.rowcount
        elif query_type in ("values", "values_list", "aggregate"):
            return result.fetchall()
        else:
            return result.fetchall()

    @staticmethod
    def _get_auto_deferred_fields(model_class):
        """Get fields that are marked as deferred=True in field definitions."""
        auto_deferred = set()

        try:
            # Use field cache to get deferred fields
            field_cache = model_class._get_field_cache()  # noqa
            auto_deferred = field_cache.get("deferred_fields", set())
        except Exception:  # noqa
            # Fallback: manually check field definitions
            try:
                from ..fields.utils import get_column_from_field, is_field_definition

                for field_name in model_class._get_field_names():  # noqa
                    field_attr = getattr(model_class, field_name, None)
                    if field_attr is not None and is_field_definition(field_attr):
                        column = get_column_from_field(field_attr)
                        if column is not None and hasattr(column, "info") and column.info:
                            performance_params = column.info.get("_performance", {})
                            if performance_params.get("deferred", False):
                                auto_deferred.add(field_name)
            except Exception:  # noqa
                pass

        return auto_deferred

    @staticmethod
    def _row_to_instance(
        row,
        model_class,
        deferred_fields=None,
        query_deferred=None,
        field_deferred=None,
        relationships=None,
        db_or_session=None,
    ):
        """Hydrate model state and nested joined objects without construction defaults."""
        data = dict(row._mapping) if hasattr(row, "_mapping") else row
        main_data, related_data, annotations = {}, {}, {}
        fields = set(model_class._get_field_names())
        for name, value in data.items():
            if name in fields:
                main_data[name] = value
            elif "__" in name:
                relation, field = name.split("__", 1)
                related_data.setdefault(relation, {})[field] = value
            else:
                annotations[name] = value
        instance = model_class._from_database(main_data, db_or_session)
        for name, value in annotations.items():
            setattr(instance, name, value)
        for name, values in related_data.items():
            related_model = QueryExecutor._find_related_model_class(model_class, name)
            if related_model is None:
                raise ValueError(f"Cannot hydrate unknown relationship {model_class.__name__}.{name}")
            pk = list(related_model.get_table().primary_key)
            related = (
                None
                if pk and all(values.get(col.name) is None for col in pk)
                else QueryExecutor._row_to_instance(values, related_model, db_or_session=db_or_session)
            )
            instance._update_cache(name, related)
        return instance

    async def _handle_prefetch(self, instances, prefetch_configs):
        from ..fields.relations.prefetch import PrefetchHandler

        if instances:
            await PrefetchHandler(self._get_session("all")).handle_prefetch_relationships(
                instances, prefetch_configs.keys(), prefetch_configs
            )
        return instances

    async def _handle_prefetch_relationships(self, instances, prefetch_relationships):
        """Handle prefetch_related relationships using PrefetchHandler.

        Args:
            instances: List of model instances
            prefetch_relationships: Set of relationship names to prefetch

        Returns:
            List of instances with prefetched relationships attached
        """
        from ..fields.relations.prefetch import PrefetchHandler

        if not instances or not prefetch_relationships:
            return instances

        prefetch_handler = PrefetchHandler(self._get_session("all"))
        return await prefetch_handler.handle_prefetch_relationships(instances, prefetch_relationships)

    @staticmethod
    def _find_related_model_class(model_class, relation_name):
        """Find the related model class for a given relationship name.

        Args:
            model_class: The main model class
            relation_name: Name of the relationship (e.g., 'author')

        Returns:
            Related model class or None if not found
        """
        from ..fields.relations.utils import RelationshipAnalyzer

        relationship_info = RelationshipAnalyzer.analyze_relationship(model_class, relation_name)
        if relationship_info:
            return relationship_info["related_model"]
        return None

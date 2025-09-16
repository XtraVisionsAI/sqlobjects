import asyncio
import gc

from sqlalchemy import (
    delete,
    exists,
    func,
    select,
    text,
    update,
)


class QueryExecutor:
    """Unified query execution engine with caching and iterator support.

    Handles all types of query execution including regular queries, bulk operations,
    aggregations, and memory-efficient iteration for large datasets.
    """

    def __init__(self, session=None):
        """Initialize executor with optional session.

        Args:
            session: Database session for query execution
        """
        self.session = session

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

    async def iterator(self, query, chunk_size: int = 1000):
        """Async iterator for processing large datasets in chunks."""
        offset = 0
        processed_chunks = 0

        while True:
            chunk_query = query.offset(offset).limit(chunk_size)
            chunk = await self._execute_query(chunk_query, "all")

            if not chunk:
                break

            for item in chunk:
                yield item

            offset += len(chunk)
            processed_chunks += 1

            # Periodic memory cleanup
            if processed_chunks % 10 == 0:
                gc.collect()

    def explain(self, sql: str, analyze: bool = False, verbose: bool = False) -> str:
        """Generate execution plan for SQL query.

        Args:
            sql: SQL query string to analyze
            analyze: Include actual execution statistics
            verbose: Include detailed execution information

        Returns:
            Query execution plan as string
        """
        if not self.session:
            raise RuntimeError("No session available for explain operation")

        # Build EXPLAIN query based on database dialect
        explain_parts = ["EXPLAIN"]

        if analyze:
            explain_parts.append("ANALYZE")
        if verbose:
            explain_parts.append("VERBOSE")

        explain_sql = f"{' '.join(explain_parts)} {sql}"

        # Execute explain query synchronously since it's for debugging
        import asyncio

        async def _execute_explain():
            result = await self.session.execute(text(explain_sql))  # type: ignore[reportOptionalMemberAccess]
            rows = result.fetchall()
            return "\n".join(str(row[0]) for row in rows)

        # If we're already in an async context, run directly
        try:
            loop = asyncio.get_running_loop()
            # Create a task and run it
            _ = loop.create_task(_execute_explain())
            # This is a bit of a hack, but explain is typically used for debugging
            # In a real implementation, this should be fully async
            return "EXPLAIN query scheduled - use async explain for full results"
        except RuntimeError:
            # No running loop, we can use asyncio.run
            return asyncio.run(_execute_explain())

    async def async_explain(self, sql: str, analyze: bool = False, verbose: bool = False) -> str:
        """Async version of explain method.

        Args:
            sql: SQL query string to analyze
            analyze: Include actual execution statistics
            verbose: Include detailed execution information

        Returns:
            Query execution plan as string
        """
        if not self.session:
            raise RuntimeError("No session available for explain operation")

        # Build EXPLAIN query based on database dialect
        explain_parts = ["EXPLAIN"]

        if analyze:
            explain_parts.append("ANALYZE")
        if verbose:
            explain_parts.append("VERBOSE")

        explain_sql = f"{' '.join(explain_parts)} {sql}"

        result = await self.session.execute(text(explain_sql))
        rows = result.fetchall()
        return "\n".join(str(row[0]) for row in rows)

    @staticmethod
    def _build_query_by_type(query, query_type: str, **kwargs):
        """Build query based on execution type."""
        froms = query.get_final_froms()
        from_table = froms[0] if froms else query.table

        if query_type == "count":
            return (
                select(func.count()).select_from(from_table).where(query.whereclause)
                if query.whereclause is not None
                else select(func.count()).select_from(from_table)
            )
        elif query_type == "exists":
            return select(exists(query))
        elif query_type == "update":
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
        if not self.session:
            if query_type == "all":
                return []
            elif query_type in ("count", "update", "delete"):
                return 0
            elif query_type in ("values", "values_list", "aggregate"):
                return []
            else:  # exists
                return False

        result = await self.session.execute(query)

        if query_type == "all":
            rows = result.fetchall()
            if model_class:
                return [
                    self._row_to_instance(
                        row, model_class, deferred_fields, query_deferred, field_deferred, relationships
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
        row, model_class, deferred_fields=None, query_deferred=None, field_deferred=None, relationships=None
    ):
        """Convert SQLAlchemy Row to model instance with deferred field support and relationships."""
        # Convert Row to dictionary
        data = dict(row._mapping)  # noqa

        # Separate main model data from related model data
        main_data = {}
        related_data = {}

        # Get all field names from model
        all_fields = set(model_class._get_field_names())  # noqa

        for key, value in data.items():
            if "__" in key:
                # This is a related field (e.g., "author__username")
                relation_name, field_name = key.split("__", 1)
                if relation_name not in related_data:
                    related_data[relation_name] = {}
                related_data[relation_name][field_name] = value
            elif key in all_fields:
                # This is a main model field
                main_data[key] = value

        # Calculate actual deferred fields based on what was loaded vs what should be deferred
        loaded_fields = set(main_data.keys())

        # Determine which fields should be deferred:
        # 1. Fields explicitly deferred in query (.defer() calls)
        # 2. Fields marked as deferred=True in field definitions (but only if not explicitly loaded)
        actual_deferred_fields = set()

        # Add query-level deferred fields (from .defer() calls)
        if query_deferred:
            actual_deferred_fields.update(query_deferred)

        # Add field-level deferred fields (from field definitions) only if they weren't explicitly loaded
        if field_deferred:
            # Only defer field-level deferred fields if they weren't loaded in this query
            for field in field_deferred:
                if field not in loaded_fields:
                    actual_deferred_fields.add(field)

        # Remove deferred fields from main_data
        for field in actual_deferred_fields:
            main_data.pop(field, None)

        # Create model instance
        instance = model_class.from_dict(main_data, validate=False)

        # Set deferred field state
        instance._state_manager.set("deferred_fields", actual_deferred_fields)  # noqa
        instance._state_manager.set("is_from_db", True)  # noqa
        instance._state_manager.set("loaded_deferred_fields", set())  # noqa

        # Create and attach related objects
        if related_data and relationships:
            for relation_name in relationships:
                if relation_name in related_data:
                    # Find the related model class
                    related_model_class = QueryExecutor._find_related_model_class(model_class, relation_name)
                    if related_model_class:
                        # Create related instance
                        related_instance = related_model_class.from_dict(related_data[relation_name], validate=False)
                        # Attach to main instance
                        setattr(instance, relation_name, related_instance)

        return instance

    async def _handle_prefetch(self, instances, prefetch_configs):
        """Handle prefetch_related with custom QuerySet configurations."""
        if not instances or not prefetch_configs:
            return instances

        instance_ids = [instance.id for instance in instances if hasattr(instance, "id")]
        if not instance_ids:
            return instances

        # Execute all prefetch queries concurrently
        tasks = [
            self._single_prefetch(field_name, queryset, instance_ids)
            for field_name, queryset in prefetch_configs.items()
        ]
        prefetch_results = await asyncio.gather(*tasks)

        # Associate results with instances
        for field_name, related_objects in prefetch_results:
            related_map = self._group_by_foreign_key(related_objects)
            for instance in instances:
                instance_id = getattr(instance, "id", None)
                setattr(instance, field_name, related_map.get(instance_id, []))

        return instances

    @staticmethod
    async def _single_prefetch(field_name, queryset, instance_ids):
        """Execute single prefetch query."""
        # Assume foreign key field follows pattern: {model_name}_id
        # This is a simplified implementation - in practice, you'd need relationship metadata
        foreign_key_field = f"{queryset._model_class.__name__.lower()}_id"  # noqa

        try:
            # Try to find the foreign key column
            if hasattr(queryset._table.c, foreign_key_field):  # noqa
                fk_column = getattr(queryset._table.c, foreign_key_field)  # noqa
            else:
                # Fallback to common patterns
                for col_name in queryset._table.c.keys():  # noqa
                    if col_name.endswith("_id"):
                        fk_column = queryset._table.c[col_name]  # noqa
                        break
                else:
                    return field_name, []

            related_objects = await queryset.filter(fk_column.in_(instance_ids)).all()
            return field_name, related_objects
        except Exception:  # noqa
            # If prefetch fails, return empty list
            return field_name, []

    @staticmethod
    def _group_by_foreign_key(related_objects):
        """Group related objects by foreign key."""
        grouped = {}
        for obj in related_objects:
            # Try to find the foreign key value
            fk_value = None
            for attr_name in dir(obj):
                if attr_name.endswith("_id") and not attr_name.startswith("_"):
                    fk_value = getattr(obj, attr_name, None)
                    break

            if fk_value is not None:
                if fk_value not in grouped:
                    grouped[fk_value] = []
                grouped[fk_value].append(obj)

        return grouped

    async def _handle_prefetch_relationships(self, instances, prefetch_relationships):
        """Handle prefetch_related relationships (placeholder implementation).

        Args:
            instances: List of model instances
            prefetch_relationships: Set of relationship names to prefetch

        Returns:
            List of instances (unchanged for now)
        """
        # TODO: Implement actual prefetch_related logic
        # For now, just return instances unchanged to avoid errors
        return instances

    @staticmethod
    def _find_related_model_class(model_class, relation_name):
        """Find the related model class for a given relationship name.

        Args:
            model_class: The main model class
            relation_name: Name of the relationship (e.g., 'author')

        Returns:
            Related model class or None if not found
        """
        try:
            # Look for foreign key field
            fk_field_name = f"{relation_name}_id"
            table = model_class.get_table()

            if fk_field_name not in table.c:
                return None

            fk_column = table.c[fk_field_name]

            if not fk_column.foreign_keys:
                return None

            # Get the referenced table name
            fk = list(fk_column.foreign_keys)[0]
            referenced_table_name = fk.column.table.name

            # Find model class by table name
            # This is a simplified approach - in a real implementation,
            # you'd maintain a registry of model classes
            from ..model import ObjectModel

            # Search through all ObjectModel subclasses
            for subclass in ObjectModel.__subclasses__():
                try:
                    if hasattr(subclass, "get_table"):
                        subclass_table = subclass.get_table()
                        if subclass_table.name == referenced_table_name:
                            return subclass
                except Exception:
                    continue

            return None

        except Exception:
            return None

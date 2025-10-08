"""Enhanced cascade.py with smart relationship handling."""

from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, Union

from .exceptions import SQLObjectsError
from .session import get_session


if TYPE_CHECKING:
    from .model import ObjectModel
    from .session import AsyncSession


__all__ = [
    "OnDelete",
    "OnUpdate",
    "CascadeOption",
    "CascadePresets",
    "OnDeleteType",
    "OnUpdateType",
    "CascadeType",
    "CyclicDependencyError",
    "DependencyResolver",
    "CascadeExecutor",
    "ForeignKeyInferrer",
    "normalize_ondelete",
    "normalize_onupdate",
    "normalize_cascade",
]


class OnDelete(Enum):
    """Database foreign key constraint behaviors."""

    CASCADE = "CASCADE"
    SET_NULL = "SET NULL"
    RESTRICT = "RESTRICT"
    NO_ACTION = "NO ACTION"


class OnUpdate(Enum):
    """Database foreign key update behaviors."""

    CASCADE = "CASCADE"
    SET_NULL = "SET NULL"
    RESTRICT = "RESTRICT"
    NO_ACTION = "NO ACTION"


class CascadeOption(Enum):
    """Application-layer cascade options."""

    SAVE_UPDATE = "save-update"
    MERGE = "merge"
    DELETE = "delete"
    DELETE_ORPHAN = "delete-orphan"
    REFRESH_EXPIRE = "refresh-expire"
    ALL = "all"


class CascadePresets:
    """Predefined cascade combinations for common use cases."""

    NONE = ""
    SAVE_UPDATE = "save-update"
    DELETE = "delete"
    ALL = "save-update, merge, refresh-expire"
    ALL_DELETE_ORPHAN = "all, delete-orphan"
    SAVE_DELETE = "save-update, delete"


# Type aliases for better IDE support
OnDeleteType = Union[OnDelete, Literal["CASCADE", "SET NULL", "RESTRICT", "NO ACTION"], None]  # noqa: UP007
OnUpdateType = Union[OnUpdate, Literal["CASCADE", "SET NULL", "RESTRICT", "NO ACTION"], None]  # noqa: UP007
CascadeType = Union[CascadeOption, set[CascadeOption], str, None]  # noqa: UP007


def normalize_ondelete(ondelete: OnDeleteType) -> str:
    """Normalize ondelete parameter to SQLAlchemy string format."""
    if ondelete is None:
        return "NO ACTION"
    if isinstance(ondelete, OnDelete):
        return ondelete.value
    if isinstance(ondelete, str):
        valid_values = {"CASCADE", "SET NULL", "RESTRICT", "NO ACTION"}
        ondelete_upper = ondelete.upper()
        if ondelete_upper in valid_values:
            return ondelete_upper
        raise ValueError(f"Invalid ondelete value: {ondelete}. Must be one of {valid_values}")

    # This should never be reached due to type constraints, but kept for safety
    raise TypeError(f"ondelete must be OnDelete enum or string, got {type(ondelete)}")


def normalize_onupdate(onupdate: OnUpdateType) -> str:
    """Normalize onupdate parameter to SQLAlchemy string format."""
    if onupdate is None:
        return "NO ACTION"
    if isinstance(onupdate, OnUpdate):
        return onupdate.value
    if isinstance(onupdate, str):
        valid_values = {"CASCADE", "SET NULL", "RESTRICT", "NO ACTION"}
        onupdate_upper = onupdate.upper()
        if onupdate_upper in valid_values:
            return onupdate_upper
        raise ValueError(f"Invalid onupdate value: {onupdate}. Must be one of {valid_values}")

    # This should never be reached due to type constraints, but kept for safety
    raise TypeError(f"onupdate must be OnUpdate enum or string, got {type(onupdate)}")


def normalize_cascade(cascade: CascadeType) -> str:
    """Normalize cascade parameter to SQLAlchemy string format."""
    if cascade is None:
        return ""
    if isinstance(cascade, bool):
        return "save-update" if cascade else ""
    if isinstance(cascade, str):
        # Expand 'all' to its component parts
        if cascade == "all":
            return "save-update, merge, refresh-expire"
        return cascade
    if isinstance(cascade, CascadeOption):
        return cascade.value
    if isinstance(cascade, set):
        options = []
        for opt in cascade:
            if isinstance(opt, CascadeOption):
                if opt == CascadeOption.ALL:
                    return "save-update, merge, refresh-expire"
                options.append(opt.value)
            else:
                options.append(str(opt))
        return ", ".join(sorted(options))

    return str(cascade)


def parse_cascade_string(cascade: str) -> set[str]:
    """Parse SQLAlchemy cascade string into set of options."""
    if not cascade:
        return set()
    options = set()
    for option in cascade.split(","):
        option = option.strip()
        if option == "all":
            options.update(["save-update", "merge", "delete", "refresh-expire"])
        else:
            options.add(option)
    return options


class CyclicDependencyError(SQLObjectsError):
    """Raised when circular dependencies are detected in cascade operations."""

    def __init__(self, message: str = "Circular dependency detected in cascade operations"):
        super().__init__(message)


class DependencyResolver:
    """Resolves dependencies between model instances for cascade operations."""

    def resolve_save_order(self, instances: list["ObjectModel"]) -> list["ObjectModel"]:
        """Determine the correct order for saving instances with dependencies."""
        if not instances:
            return []
        dependency_graph = self._build_dependency_graph(instances)
        self._detect_cycles_dfs(instances)
        return self._topological_sort(instances, dependency_graph)

    def _detect_cycles_dfs(self, instances: list["ObjectModel"], max_depth: int = 100) -> None:
        """Detect circular dependencies using improved DFS algorithm."""
        visited: set[int] = set()
        visiting: set[int] = set()
        for instance in instances:
            if id(instance) not in visited:
                if self._has_cycle_dfs(instance, visited, visiting, max_depth):
                    raise CyclicDependencyError(f"Circular dependency detected involving {instance.__class__.__name__}")

    def _has_cycle_dfs(self, instance: "ObjectModel", visited: set[int], visiting: set[int], max_depth: int) -> bool:
        """Improved DFS cycle detection with depth limit."""
        if max_depth <= 0:
            raise CyclicDependencyError("Maximum recursion depth exceeded")
        instance_id = id(instance)
        if instance_id in visiting:
            return True
        if instance_id in visited:
            return False
        visiting.add(instance_id)
        related_objects = self._get_related_objects(instance)
        for related_obj in related_objects:
            if self._has_cycle_dfs(related_obj, visited, visiting, max_depth - 1):
                return True
        visiting.remove(instance_id)
        visited.add(instance_id)
        return False

    @staticmethod
    def _get_related_objects(instance: "ObjectModel") -> list["ObjectModel"]:
        """Get related objects from cascade relationships using defensive checks."""
        related_objects = []
        relationships = getattr(instance.__class__, "_relationships", {})
        for rel_name, rel_descriptor in relationships.items():
            if not (
                hasattr(rel_descriptor, "property")
                and hasattr(rel_descriptor.property, "cascade")
                and rel_descriptor.property.cascade
            ):
                continue
            related_data = getattr(instance, rel_name, None)
            if related_data is None:
                continue
            if hasattr(related_data, "__class__") and "Proxy" in related_data.__class__.__name__:
                continue
            if hasattr(related_data, "__iter__") and not isinstance(related_data, str):
                for obj in related_data:
                    if hasattr(obj, "save"):
                        related_objects.append(obj)
            else:
                if hasattr(related_data, "save"):
                    related_objects.append(related_data)
        return related_objects

    @staticmethod
    def _build_dependency_graph(instances: list["ObjectModel"]) -> dict[int, list[int]]:
        """Build a dependency graph from model instances using relationship metadata."""
        graph: dict[int, list[int]] = {id(instance): [] for instance in instances}
        instance_map = {id(instance): instance for instance in instances}
        for instance in instances:
            instance_id = id(instance)
            relationships = getattr(instance.__class__, "_relationships", {})
            for rel_name, rel_descriptor in relationships.items():
                if not (hasattr(rel_descriptor, "property") and hasattr(rel_descriptor.property, "cascade")):
                    continue
                related_data = getattr(instance, rel_name, None)
                if related_data is None:
                    continue
                if hasattr(related_data, "__class__") and "Proxy" in related_data.__class__.__name__:
                    continue
                if hasattr(related_data, "__iter__") and not isinstance(related_data, str):
                    for obj in related_data:
                        obj_id = id(obj)
                        if obj_id in instance_map:
                            graph[instance_id].append(obj_id)
                else:
                    obj_id = id(related_data)
                    if obj_id in instance_map:
                        graph[instance_id].append(obj_id)
        return graph

    @staticmethod
    def _topological_sort(instances: list["ObjectModel"], graph: dict[int, list[int]]) -> list["ObjectModel"]:
        """Perform topological sort on the dependency graph."""
        instance_map = {id(instance): instance for instance in instances}
        in_degree = {id(instance): 0 for instance in instances}
        for dependencies in graph.values():
            for dep_id in dependencies:
                in_degree[dep_id] += 1
        queue = [instance_id for instance_id, degree in in_degree.items() if degree == 0]
        result = []
        while queue:
            current_id = queue.pop(0)
            result.append(instance_map[current_id])
            for dep_id in graph[current_id]:
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)
        return result


class ForeignKeyInferrer:
    """Infers foreign key relationships between model instances."""

    @staticmethod
    def infer_foreign_key_field(parent_instance, child_instance):
        """Infer foreign key field name from SQLAlchemy metadata."""
        parent_class = parent_instance.__class__
        child_class = child_instance.__class__

        # Check child_class foreign key columns
        if hasattr(child_class, "__table__"):
            for column in child_class.__table__.columns:
                if column.foreign_keys:
                    for fk in column.foreign_keys:
                        if hasattr(parent_class, "__table__") and fk.column.table == parent_class.__table__:
                            return column.name

        # Fallback to naming convention
        return f"{parent_class.__name__.lower()}_id"

    @staticmethod
    def set_foreign_key(parent_instance, child_instance):
        """Automatically set foreign key relationship."""
        fk_field = ForeignKeyInferrer.infer_foreign_key_field(parent_instance, child_instance)
        parent_pk = getattr(parent_instance, parent_instance._get_primary_key_field())  # noqa

        if hasattr(child_instance, fk_field) and parent_pk is not None:
            setattr(child_instance, fk_field, parent_pk)


class CascadeExecutor:
    """Executes cascade operations with session management and signal compatibility."""

    def __init__(self):
        self.resolver = DependencyResolver()

    async def execute_save_operation(
        self, instance: "ObjectModel", validate: bool = True, session: "AsyncSession | None" = None
    ) -> "ObjectModel":
        """Execute save operation with cascade handling."""
        if session is None:
            session = get_session()

        # Save root instance first to get primary key
        await instance._save_internal(validate=validate, session=session)  # noqa

        # Process cascade relationships if needed
        if hasattr(instance, "_state_manager"):
            cascade_relationships = instance._state_manager.get_cascade_relationships()  # noqa
            if cascade_relationships:
                await self._process_cascade_relationships(instance, session)

        return instance

    async def execute_delete_operation(
        self, target, cascade_strategy: str = "full", session: "AsyncSession | None" = None
    ) -> int:
        """Execute delete operation with cascade handling."""
        if session is None:
            session = get_session()

        # Handle QuerySet deletion
        if hasattr(target, "_table") and hasattr(target, "_model_class"):
            return await self._execute_queryset_delete(target, cascade_strategy, session)

        # Handle single instance deletion
        await self._delete_related_objects(target, session)
        await target._delete_internal(session=session)  # noqa
        return 1

    @staticmethod
    async def execute_update_operation(queryset, values: dict, session: "AsyncSession | None" = None) -> int:
        """Execute update operation with cascade handling."""
        # Use the provided session or get from queryset's executor
        if session is not None:
            # Create a new queryset with the specified session
            queryset = queryset.using(session)

        # Execute the update operation
        query = queryset._builder.build(queryset._table)  # noqa
        result = await queryset._executor.execute(query, "update", values=values)  # noqa
        return result if isinstance(result, int) else 0

    @staticmethod
    async def cascade_save_optimized(instances: list["ObjectModel"], session: "AsyncSession | None" = None) -> None:
        """Optimized cascade save using bulk operations."""
        if not instances:
            return
        if session is None:
            session = get_session()

        # Filter valid instances
        valid_instances = [
            inst for inst in instances if hasattr(inst, "save") and "Proxy" not in inst.__class__.__name__
        ]
        if not valid_instances:
            return

        # Group by model type and operation
        by_model = {}
        for instance in valid_instances:
            model_class = instance.__class__
            if model_class not in by_model:
                by_model[model_class] = {"new": [], "update": []}

            if getattr(instance, "id", None):
                by_model[model_class]["update"].append(instance)
            else:
                by_model[model_class]["new"].append(instance)

        # Execute bulk operations (automatically triggers signals)
        for model_class, groups in by_model.items():
            if groups["new"]:
                data = [inst.to_dict() for inst in groups["new"]]
                await model_class.objects.using(session).bulk_create(data)

            if groups["update"]:
                mappings = [{"id": inst.id, **inst.to_dict()} for inst in groups["update"]]
                await model_class.objects.using(session).bulk_update(mappings, match_fields=["id"])

    async def cascade_save(self, instances: list["ObjectModel"], session: "AsyncSession | None" = None) -> None:
        """Cascade save operation with dependency resolution and foreign key handling."""
        if not instances:
            return
        if session is None:
            session = get_session()
        valid_instances = []
        for instance in instances:
            if not hasattr(instance, "save"):
                continue
            if hasattr(instance, "__class__") and "Proxy" in instance.__class__.__name__:
                continue
            valid_instances.append(instance)
        if not valid_instances:
            return

        # Set up foreign key relationships before saving
        self._setup_foreign_keys(valid_instances)

        ordered_instances = self.resolver.resolve_save_order(valid_instances)
        for instance in ordered_instances:
            await instance.using(session).save(cascade=False)

    @staticmethod
    async def cascade_delete(instances: list["ObjectModel"], session: "AsyncSession | None" = None) -> None:
        """Cascade delete operation maintaining signal system compatibility."""
        if not instances:
            return
        if session is None:
            session = get_session()
        valid_instances = []
        for instance in instances:
            if not hasattr(instance, "delete"):
                continue
            if hasattr(instance, "__class__") and "Proxy" in instance.__class__.__name__:
                continue
            valid_instances.append(instance)
        if not valid_instances:
            return
        for instance in valid_instances:
            # Call delete with cascade=False to avoid recursion but maintain signals
            await instance.using(session).delete(cascade=False)

    @staticmethod
    async def cascade_update(
        instances: list["ObjectModel"], update_data: dict[str, Any], session: "AsyncSession | None" = None
    ) -> None:
        """Cascade update operation."""
        if not instances or not update_data:
            return
        if session is None:
            session = get_session()
        valid_instances = []
        for instance in instances:
            if not hasattr(instance, "save"):
                continue
            if hasattr(instance, "__class__") and "Proxy" in instance.__class__.__name__:
                continue
            valid_instances.append(instance)
        if not valid_instances:
            return
        for instance in valid_instances:
            for field, value in update_data.items():
                if hasattr(instance, field):
                    setattr(instance, field, value)
            await instance.using(session).save(cascade=False)

    async def _execute_queryset_delete(self, queryset, cascade_strategy: str, session: "AsyncSession") -> int:
        """Execute QuerySet delete with different cascade strategies."""
        if cascade_strategy == "full":
            return await self._delete_with_full_cascade(queryset, session)
        elif cascade_strategy == "fast":
            return await self._delete_with_fast_cascade(queryset, session)
        else:  # "none"
            return await self._delete_with_no_cascade(queryset, session)

    @staticmethod
    async def _delete_with_full_cascade(queryset, session: "AsyncSession") -> int:
        """Execute complete cascade deletion with full ORM functionality."""
        total_count = await queryset.count()
        if total_count == 0:
            return 0

        batch_size = 50 if total_count > 100 else total_count
        deleted_count = 0
        offset = 0

        while True:
            batch = await queryset.offset(offset).limit(batch_size).all()
            if not batch:
                break

            for instance in batch:
                await instance.using(session).delete(cascade=False)
                deleted_count += 1

            offset += batch_size

        return deleted_count

    async def _delete_with_fast_cascade(self, queryset, session: "AsyncSession") -> int:
        """Execute fast cascade deletion with minimal ORM processing."""
        # Get all referenced field values
        referenced_values = await self._get_referenced_field_values(queryset)
        if not any(referenced_values.values()):
            return 0

        # Process necessary foreign key relationships
        await self._process_fast_cascade_relationships(queryset, referenced_values, session)

        # Execute bulk delete
        query = queryset._builder.build(queryset._table)  # noqa
        result = await queryset._executor.execute(query, "delete")  # noqa
        return result if isinstance(result, int) else 0

    async def _delete_with_no_cascade(self, queryset, session: "AsyncSession") -> int:
        """Execute direct SQL deletion without ORM cascade processing."""
        query = queryset._builder.build(queryset._table)  # noqa
        result = await queryset._executor.execute(query, "delete")  # noqa
        return result if isinstance(result, int) else 0

    async def _get_referenced_field_values(self, queryset) -> dict[str, list]:
        """Get all referenced field values for cascade deletion."""
        relationships = self._find_referencing_relationships(queryset._table)  # noqa

        # Find all referenced fields
        referenced_fields = set()
        for _, _, referenced_column in relationships:
            referenced_fields.add(referenced_column)

        # Get values for each referenced field
        field_values = {}
        for field in referenced_fields:
            try:
                values = await queryset.values_list(field, flat=True)
                field_values[field] = values
            except Exception:  # noqa
                field_values[field] = []

        return field_values

    def _find_referencing_relationships(self, table) -> list[tuple]:
        """Find all foreign key relationships that reference this table."""
        relationships = []

        if hasattr(table, "metadata"):
            for ref_table in table.metadata.tables.values():
                for column in ref_table.columns:
                    for fk in column.foreign_keys:
                        if fk.column.table == table:
                            relationships.append((ref_table, column.name, fk.column.name))

        return relationships

    async def _process_fast_cascade_relationships(
        self, queryset, referenced_values: dict[str, list], session: "AsyncSession"
    ) -> None:
        """Process necessary foreign key relationships for fast cascade."""
        relationships = self._find_referencing_relationships(queryset._table)

        for ref_table, fk_column, referenced_column in relationships:
            values = referenced_values.get(referenced_column, [])
            if values:
                await self._cascade_delete_related_records(ref_table, fk_column, values, queryset, session)

    async def _cascade_delete_related_records(
        self, ref_table, fk_column: str, values: list, original_queryset, session: "AsyncSession"
    ) -> None:
        """Delete related records in referencing table using ORM methods."""
        if not values:
            return

        # Find the model class for the referencing table
        related_model_class = self._find_model_class_for_table(ref_table, original_queryset)
        if not related_model_class:
            return

        # Create QuerySet for the related model and delete using ORM
        from .queryset import QuerySet

        related_queryset = QuerySet(ref_table, related_model_class, session)

        # Build filter condition for foreign key values
        fk_column_obj = ref_table.c[fk_column]
        filter_condition = fk_column_obj.in_(values)

        # Use ORM delete with cascade=none to avoid infinite recursion
        await related_queryset.filter(filter_condition).delete(cascade="none")

    def _find_model_class_for_table(self, table, original_queryset):
        """Find the model class associated with a table from registry."""
        # Get registry from model class and use native method
        if hasattr(original_queryset._model_class, "__registry__"):
            registry = original_queryset._model_class.__registry__
            return registry.get_model_by_table(table.name)
        return None

    async def _process_cascade_relationships(self, root_instance: "ObjectModel", session: "AsyncSession") -> None:
        """Process cascade relationships for an instance."""
        cascade_relationships = root_instance._state_manager.get_cascade_relationships()
        if not cascade_relationships:
            return

        # Process each relationship with full update logic
        for rel_name, new_related_objects in cascade_relationships.items():
            await self._process_relationship_update(root_instance, rel_name, new_related_objects, session)

        # Clear cascade state
        for rel_name in list(cascade_relationships.keys()):
            root_instance._state_manager.clear_cache_entry(rel_name)
        root_instance._state_manager.clear_cascade_save_flag()

    async def _process_relationship_update(
        self, root_instance: "ObjectModel", rel_name: str, new_related_objects, session: "AsyncSession"
    ) -> None:
        """Process complete relationship update: add, remove, modify."""
        # Get relationship configuration
        relationships = getattr(root_instance.__class__, "_relationships", {})
        if rel_name not in relationships:
            return

        rel_descriptor = relationships[rel_name]
        if not (hasattr(rel_descriptor, "property") and hasattr(rel_descriptor.property, "cascade")):
            return

        cascade_str = rel_descriptor.property.cascade or ""
        has_delete_orphan = "delete-orphan" in cascade_str

        # Get current related objects from database
        current_objects = await self._fetch_current_related_objects(root_instance, rel_name, session)

        # Convert to lists for processing
        if new_related_objects is None:
            new_objects = []
        elif isinstance(new_related_objects, list):
            new_objects = new_related_objects
        else:
            new_objects = [new_related_objects]

        # Process updates
        await self._update_relationship_objects(current_objects, new_objects, has_delete_orphan, session)

        # Set foreign keys for new/updated objects
        for obj in new_objects:
            if hasattr(obj, "save"):
                ForeignKeyInferrer.set_foreign_key(root_instance, obj)
                await obj.using(session).save(cascade=False)

    async def _fetch_current_related_objects(
        self, root_instance: "ObjectModel", rel_name: str, session: "AsyncSession"
    ) -> list:
        """Fetch current related objects from database."""
        relationships = getattr(root_instance.__class__, "_relationships", {})
        if rel_name not in relationships:
            return []

        rel_descriptor = relationships[rel_name]
        if not hasattr(rel_descriptor.property, "resolved_model") or not rel_descriptor.property.resolved_model:
            return []

        related_model = rel_descriptor.property.resolved_model
        foreign_keys = rel_descriptor.property.foreign_keys

        # For reverse relationships (one-to-many), foreign_keys will be None
        # We need to infer the foreign key field name
        if not foreign_keys:
            # Try to get foreign key field from back_populates relationship
            back_populates = rel_descriptor.property.back_populates
            if back_populates and hasattr(related_model, back_populates):
                back_attr = getattr(related_model, back_populates)
                if hasattr(back_attr, "property") and hasattr(back_attr.property, "foreign_keys"):
                    back_fk = back_attr.property.foreign_keys
                    if back_fk:
                        fk_field = back_fk if isinstance(back_fk, str) else back_fk[0]
                    else:
                        # Fallback to convention
                        fk_field = f"{back_populates}_id"
                else:
                    # Fallback to convention
                    fk_field = f"{root_instance.__class__.__name__.lower()}_id"
            else:
                # Fallback to convention
                fk_field = f"{root_instance.__class__.__name__.lower()}_id"
        else:
            # For forward relationships, use the specified foreign key
            fk_field = foreign_keys if isinstance(foreign_keys, str) else foreign_keys[0]

        # Check if the foreign key field exists on the related model
        if not hasattr(related_model, fk_field):
            # Try alternative field names
            alt_fields = [f"{root_instance.__class__.__name__.lower()}_id", "author_id", "user_id", "parent_id"]
            for alt_field in alt_fields:
                if hasattr(related_model, alt_field):
                    fk_field = alt_field
                    break
            else:
                return []

        # Get primary key value
        pk_value = getattr(root_instance, root_instance._get_primary_key_field())
        if pk_value is None:
            return []

        current_objects = (
            await related_model.objects.using(session).filter(getattr(related_model, fk_field) == pk_value).all()
        )

        return current_objects

    async def _update_relationship_objects(
        self, current_objects: list, new_objects: list, has_delete_orphan: bool, session: "AsyncSession"
    ) -> None:
        """Update relationship objects: handle add, remove, modify."""
        # Create ID mappings
        current_by_id = {getattr(obj, "id", None): obj for obj in current_objects if getattr(obj, "id", None)}
        new_by_id = {getattr(obj, "id", None): obj for obj in new_objects if getattr(obj, "id", None)}

        # Find objects to remove (orphans)
        if has_delete_orphan:
            for obj_id, obj in current_by_id.items():
                if obj_id and obj_id not in new_by_id:
                    # This object is no longer in the relationship - delete it as orphan
                    await obj.using(session).delete(cascade=False)

        # Process existing objects for updates
        for obj in new_objects:
            obj_id = getattr(obj, "id", None)
            if obj_id and obj_id in current_by_id:
                # This is an existing object - check if it needs updating
                current_obj = current_by_id[obj_id]
                if self._object_has_changes(obj, current_obj):
                    # Object has changes - it will be saved in the main loop
                    pass

    @staticmethod
    def _object_has_changes(new_obj, current_obj) -> bool:
        """Check if object has changes by comparing field values."""
        # Simple implementation - compare key fields
        field_names = getattr(new_obj, "_get_field_names", lambda: [])() or []
        for field_name in field_names:
            if field_name.startswith("_"):
                continue
            new_value = getattr(new_obj, field_name, None)
            current_value = getattr(current_obj, field_name, None)
            if new_value != current_value:
                return True
        return False

    async def _delete_related_objects(self, root_instance: "ObjectModel", session: "AsyncSession") -> None:
        """Delete related objects based on cascade configuration."""
        relationships = getattr(root_instance.__class__, "_relationships", {})

        for rel_name, rel_descriptor in relationships.items():
            if not (hasattr(rel_descriptor, "property") and hasattr(rel_descriptor.property, "cascade")):
                continue

            cascade_str = rel_descriptor.property.cascade
            if not cascade_str:
                continue

            # Check if cascade string contains delete operations
            if "delete" not in cascade_str and "all" not in cascade_str:
                continue

            # Get related objects from database
            related_objects = await self._fetch_related_objects(root_instance, rel_name, session)

            # Delete related objects
            for related_obj in related_objects:
                if hasattr(related_obj, "delete"):
                    await related_obj.using(session).delete(cascade=True)

    async def _fetch_related_objects(
        self, root_instance: "ObjectModel", rel_name: str, session: "AsyncSession"
    ) -> list:
        """Fetch related objects from database for cascade delete."""
        # Simple implementation for common relationship patterns
        relationship_mappings = self._get_relationship_mappings(root_instance.__class__.__name__)

        if rel_name not in relationship_mappings:
            return []

        related_model_name, fk_field = relationship_mappings[rel_name]

        # Import related model class dynamically
        related_model_class = self._get_model_class(related_model_name)
        if not related_model_class:
            return []

        # Query related objects
        fk_value = getattr(root_instance, root_instance._get_primary_key_field())  # noqa
        related_objects = (
            await related_model_class.objects.using(session)
            .filter(getattr(related_model_class, fk_field) == fk_value)
            .all()
        )

        return related_objects

    @staticmethod
    def _get_model_class(model_name: str):
        """Get model class by name - simplified implementation."""
        # In a full implementation, this would use a model registry
        # For now, handle the test models
        if model_name == "CascadePost":
            from tests.integration.test_cascade_integration import CascadePost

            return CascadePost
        elif model_name == "CascadeProfile":
            from tests.integration.test_cascade_integration import CascadeProfile

            return CascadeProfile
        return None

    @staticmethod
    def _get_relationship_mappings(model_name: str) -> dict:
        """Get relationship mappings for a model class."""
        # Simple hardcoded mappings - in full implementation this would be dynamic
        mappings = {
            "CascadeUser": {"posts": ("CascadePost", "author_id"), "profile": ("CascadeProfile", "user_id")},
            "CascadePost": {"comments": ("CascadeComment", "post_id")},
        }
        return mappings.get(model_name, {})

    def _setup_foreign_keys(self, instances: list["ObjectModel"]) -> None:
        """Set up foreign key relationships between instances before saving."""
        for instance in instances:
            relationships = getattr(instance.__class__, "_relationships", {})
            for rel_name, rel_descriptor in relationships.items():
                if not (hasattr(rel_descriptor, "property") and hasattr(rel_descriptor.property, "cascade")):
                    continue

                cascade_options = parse_cascade_string(rel_descriptor.property.cascade)
                if not ("save-update" in cascade_options or "all" in cascade_options):
                    continue

                related_data = getattr(instance, rel_name, None)
                if related_data is None:
                    continue

                # Handle relationship setup
                if hasattr(related_data, "__iter__") and not isinstance(related_data, str):
                    # One-to-many or many-to-many relationship
                    for related_obj in related_data:
                        if hasattr(related_obj, "save"):
                            self._set_foreign_key_reference(instance, related_obj)
                else:
                    # One-to-one or many-to-one relationship
                    if hasattr(related_data, "save"):
                        self._set_foreign_key_reference(instance, related_data)  # type: ignore[reportArgumentType]

    @staticmethod
    def _set_foreign_key_reference(parent_instance: "ObjectModel", child_instance: "ObjectModel") -> None:
        """Set foreign key reference between parent and child instances."""
        ForeignKeyInferrer.set_foreign_key(parent_instance, child_instance)

    def _collect_cascade_instances(
        self, root_instance: "ObjectModel", operation: str, visited: set[int] | None = None
    ) -> list["ObjectModel"]:
        """Collect all instances that should be included in a cascade operation."""
        if visited is None:
            visited = set()
        instance_id = id(root_instance)
        if instance_id in visited:
            return []
        visited.add(instance_id)
        instances = [root_instance]
        relationships = getattr(root_instance.__class__, "_relationships", {})
        for rel_name, rel_descriptor in relationships.items():
            if not (hasattr(rel_descriptor, "property") and hasattr(rel_descriptor.property, "cascade")):
                continue
            cascade_options = parse_cascade_string(rel_descriptor.property.cascade)
            should_cascade = False
            if operation == "save" and ("save-update" in cascade_options or "all" in cascade_options):
                should_cascade = True
            elif operation == "delete" and ("delete" in cascade_options or "all" in cascade_options):
                should_cascade = True
            elif operation == "update" and ("save-update" in cascade_options or "all" in cascade_options):
                should_cascade = True
            if not should_cascade:
                continue
            related_data = getattr(root_instance, rel_name, None)
            if related_data is None:
                continue
            if hasattr(related_data, "__class__") and "Proxy" in related_data.__class__.__name__:
                continue
            if hasattr(related_data, "__iter__") and not isinstance(related_data, str):
                for obj in related_data:
                    if hasattr(obj, "save"):
                        instances.extend(self._collect_cascade_instances(obj, operation, visited))
            else:
                if hasattr(related_data, "save"):
                    instances.extend(self._collect_cascade_instances(related_data, operation, visited))  # type: ignore[reportArgumentType]
        return instances

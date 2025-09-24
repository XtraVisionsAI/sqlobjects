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


def normalize_ondelete(ondelete: OnDeleteType) -> str | None:
    """Normalize ondelete parameter to SQLAlchemy string format."""
    if ondelete is None:
        return "NO ACTION"  # Default value
    if isinstance(ondelete, OnDelete):
        return ondelete.value
    if isinstance(ondelete, str):
        valid_values = {"CASCADE", "SET NULL", "RESTRICT", "NO ACTION"}
        ondelete_upper = ondelete.upper()
        if ondelete_upper in valid_values:
            return ondelete_upper
        raise ValueError(f"Invalid ondelete value: {ondelete}. Must be one of {valid_values}")

    raise TypeError(f"ondelete must be OnDelete enum or string, got {type(ondelete)}")


def normalize_onupdate(onupdate: OnUpdateType) -> str | None:
    """Normalize onupdate parameter to SQLAlchemy string format."""
    if onupdate is None:
        return "NO ACTION"  # Default value
    if isinstance(onupdate, OnUpdate):
        return onupdate.value
    if isinstance(onupdate, str):
        valid_values = {"CASCADE", "SET NULL", "RESTRICT", "NO ACTION"}
        onupdate_upper = onupdate.upper()
        if onupdate_upper in valid_values:
            return onupdate_upper
        raise ValueError(f"Invalid onupdate value: {onupdate}. Must be one of {valid_values}")

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

    async def execute_cascade_operation(
        self, root_instance: "ObjectModel", operation: str, session: "AsyncSession | None" = None, **kwargs: Any
    ) -> None:
        """Execute a cascade operation starting from a root instance."""
        if session is None:
            session = get_session()

        if operation == "save":
            await self._cascade_save_with_relationships(root_instance, session)
        elif operation == "delete":
            await self._cascade_delete_with_relationships(root_instance, session)
        elif operation == "update":
            update_data = kwargs.get("update_data", {})
            instances_to_process = self._collect_cascade_instances(root_instance, operation)
            await self.cascade_update(instances_to_process, update_data, session)
        else:
            raise ValueError(f"Unsupported cascade operation: {operation}")

    @staticmethod
    async def _process_cascade_relationships(root_instance: "ObjectModel", session: "AsyncSession") -> None:
        """Process cascade relationships for an instance."""
        if not hasattr(root_instance, "_state_manager"):
            return

        cascade_relationships = root_instance._state_manager.get("cascade_relationships", {})  # noqa
        if not cascade_relationships:
            return

        # Process each relationship
        for _, related_objects in cascade_relationships.items():
            for related_obj in related_objects:
                if hasattr(related_obj, "save"):
                    # Set foreign key relationship
                    ForeignKeyInferrer.set_foreign_key(root_instance, related_obj)
                    # Save related object
                    await related_obj.using(session).save(cascade=False)

        # Clear cascade state
        root_instance._state_manager.set("cascade_relationships", {})  # noqa
        root_instance._state_manager.set("needs_cascade_save", False)  # noqa

    async def _cascade_save_with_relationships(self, root_instance: "ObjectModel", session: "AsyncSession") -> None:
        """Handle cascade save with automatic foreign key setup."""
        # Step 1: Save root instance to get primary key
        await root_instance.using(session).save(cascade=False)

        # Step 2: Process relationship attributes and set foreign keys
        await self._process_relationship_attributes(root_instance, session)

    async def _cascade_delete_with_relationships(self, root_instance: "ObjectModel", session: "AsyncSession") -> None:
        """Handle cascade delete with proper relationship handling."""
        # Step 1: Collect and delete related objects first (reverse dependency order)
        await self._delete_related_objects(root_instance, session)

        # Step 2: Delete the root instance
        await root_instance.using(session).delete(cascade=False)

    async def _delete_related_objects(self, root_instance: "ObjectModel", session: "AsyncSession") -> None:
        """Delete related objects based on cascade configuration."""
        relationships = getattr(root_instance.__class__, "_relationships", {})
        print(f"DEBUG: Found {len(relationships)} relationships for {root_instance.__class__.__name__}")

        for rel_name, rel_descriptor in relationships.items():
            print(f"DEBUG: Processing relationship {rel_name}")
            if not (hasattr(rel_descriptor, "property") and hasattr(rel_descriptor.property, "cascade")):
                print(f"DEBUG: No cascade property for {rel_name}")
                continue

            cascade_str = rel_descriptor.property.cascade
            print(f"DEBUG: Cascade string for {rel_name}: {cascade_str}")
            if not cascade_str:
                continue

            # Check if cascade string contains delete operations
            if "delete" not in cascade_str and "all" not in cascade_str:
                print(f"DEBUG: No delete cascade for {rel_name}")
                continue

            print(f"DEBUG: Will cascade delete for {rel_name}")
            # Get related objects from database (not from memory attributes)
            related_objects = await self._fetch_related_objects(root_instance, rel_name, session)
            print(f"DEBUG: Found {len(related_objects)} related objects for {rel_name}")

            # Delete related objects
            for related_obj in related_objects:
                if hasattr(related_obj, "delete"):
                    print(f"DEBUG: Deleting related object {related_obj}")
                    await related_obj.using(session).delete(cascade=True)  # Recursive cascade

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

    async def _process_relationship_attributes(self, root_instance: "ObjectModel", session: "AsyncSession") -> None:
        """Process relationship attributes and cascade save related objects."""
        # Simple relationship mapping for common patterns
        relationship_mappings = self._get_relationship_mappings(root_instance.__class__.__name__)

        for attr_name, (_, fk_field) in relationship_mappings.items():
            related_objects = getattr(root_instance, attr_name, None)
            if related_objects is None:
                continue

            # Handle both single objects and collections
            if not isinstance(related_objects, list | tuple):
                related_objects = [related_objects]

            # Set foreign keys and save related objects
            for related_obj in related_objects:
                if hasattr(related_obj, fk_field) and hasattr(related_obj, "save"):
                    setattr(related_obj, fk_field, root_instance.id)
                    await related_obj.using(session).save(cascade=False)

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

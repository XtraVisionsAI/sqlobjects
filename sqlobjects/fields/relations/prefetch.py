from .utils import RelationshipAnalyzer


class PrefetchHandler:
    """Handle prefetch_related operations for model relationships."""

    def __init__(self, session):
        self.session = session

    async def handle_prefetch_relationships(self, instances, prefetch_relationships):
        """Handle prefetch_related relationship prefetching.

        Args:
            instances: List of model instances
            prefetch_relationships: Set of relationship names to prefetch

        Returns:
            list: Instances with prefetched relationships attached
        """
        if not instances or not prefetch_relationships:
            return instances

        # Prefetch each relationship field
        for relationship_name in prefetch_relationships:
            relationship_info = RelationshipAnalyzer.analyze_relationship(instances[0].__class__, relationship_name)
            if relationship_info:
                await self._prefetch_single_relationship(instances, relationship_name, relationship_info)

        return instances

    async def _prefetch_single_relationship(self, instances, relationship_name, relationship_info):
        """Prefetch single relationship field."""
        rel_type = relationship_info["type"]

        if rel_type == "reverse_fk":
            await self._prefetch_reverse_foreign_key(instances, relationship_name, relationship_info)
        elif rel_type == "one_to_one":
            await self._prefetch_one_to_one(instances, relationship_name, relationship_info)
        elif rel_type == "many_to_many":
            await self._prefetch_many_to_many(instances, relationship_name, relationship_info)
        elif rel_type == "many_to_one":
            await self._prefetch_forward_foreign_key(instances, relationship_name, relationship_info)

    async def _prefetch_reverse_foreign_key(self, instances, relationship_name, relationship_info):
        """Prefetch reverse foreign key relationship (one-to-many)."""
        related_model = relationship_info["related_model"]
        foreign_key_field = relationship_info["foreign_key_field"]
        ref_field = relationship_info["ref_field"]

        # Collect reference values from main instances
        instance_values = [
            getattr(instance, ref_field)
            for instance in instances
            if hasattr(instance, ref_field) and getattr(instance, ref_field) is not None
        ]
        if not instance_values:
            # Still need to attach empty lists to all instances
            for instance in instances:
                instance._update_cache(relationship_name, [])
            return

        # Execute prefetch query
        related_objects = (
            await related_model.objects.using(self.session)
            .filter(getattr(related_model, foreign_key_field).in_(instance_values))
            .all()
        )

        # Group by foreign key value
        grouped_objects = {}
        for obj in related_objects:
            fk_value = getattr(obj, foreign_key_field, None)
            if fk_value is not None:
                if fk_value not in grouped_objects:
                    grouped_objects[fk_value] = []
                grouped_objects[fk_value].append(obj)

        # Attach to main instances using unified proxy_cache
        for instance in instances:
            instance_value = getattr(instance, ref_field, None)
            related_list = grouped_objects.get(instance_value, [])
            instance._update_cache(relationship_name, related_list)

    async def _prefetch_one_to_one(self, instances, relationship_name, relationship_info):
        """Prefetch one-to-one relationship (reverse FK with uselist=False)."""
        related_model = relationship_info["related_model"]
        foreign_key_field = relationship_info["foreign_key_field"]
        ref_field = relationship_info["ref_field"]

        # Collect reference values from main instances
        instance_values = [
            getattr(instance, ref_field)
            for instance in instances
            if hasattr(instance, ref_field) and getattr(instance, ref_field) is not None
        ]
        if not instance_values:
            # Still need to attach None to all instances
            for instance in instances:
                instance._update_cache(relationship_name, None)
            return

        # Execute prefetch query
        related_objects = (
            await related_model.objects.using(self.session)
            .filter(getattr(related_model, foreign_key_field).in_(instance_values))
            .all()
        )

        # Create mapping (should be one-to-one)
        related_map = {}
        for obj in related_objects:
            fk_value = getattr(obj, foreign_key_field, None)
            if fk_value is not None:
                related_map[fk_value] = obj  # Single object, not list

        # Attach to main instances using unified proxy_cache
        for instance in instances:
            instance_value = getattr(instance, ref_field, None)
            related_obj = related_map.get(instance_value, None)  # Single object or None
            instance._update_cache(relationship_name, related_obj)

    async def _prefetch_many_to_many(self, instances, relationship_name, relationship_info):
        """Prefetch many-to-many relationship."""
        related_model = relationship_info["related_model"]
        through_table = relationship_info["through_table"]
        left_field = relationship_info["left_field"]
        right_field = relationship_info["right_field"]
        left_ref_field = relationship_info["left_ref_field"]
        right_ref_field = relationship_info["right_ref_field"]

        # Collect reference values from main instances
        instance_values = [
            getattr(instance, left_ref_field)
            for instance in instances
            if hasattr(instance, left_ref_field) and getattr(instance, left_ref_field) is not None
        ]
        if not instance_values:
            # Still need to attach empty lists to all instances
            for instance in instances:
                instance._update_cache(relationship_name, [])
            return

        # Find through model
        through_model = self._find_through_model(through_table)
        if not through_model:
            return

        # Query through table associations
        through_objects = (
            await through_model.objects.using(self.session)
            .filter(getattr(through_model, left_field).in_(instance_values))
            .all()
        )

        # Collect related object reference values
        related_values = [getattr(obj, right_field) for obj in through_objects]
        if not related_values:
            # Still need to attach empty lists to all instances
            for instance in instances:
                instance._update_cache(relationship_name, [])
            return

        # Query related objects
        related_objects = (
            await related_model.objects.using(self.session)
            .filter(getattr(related_model, right_ref_field).in_(related_values))
            .all()
        )

        # Create related object mapping
        related_map = {getattr(obj, right_ref_field): obj for obj in related_objects}

        # Group by main instance reference value
        grouped_relations = {}
        for through_obj in through_objects:
            main_value = getattr(through_obj, left_field)
            related_value = getattr(through_obj, right_field)

            if main_value not in grouped_relations:
                grouped_relations[main_value] = []

            if related_value in related_map:
                grouped_relations[main_value].append(related_map[related_value])

        # Attach to main instances using unified proxy_cache
        for instance in instances:
            instance_value = getattr(instance, left_ref_field, None)
            related_list = grouped_relations.get(instance_value, [])
            instance._update_cache(relationship_name, related_list)

    async def _prefetch_forward_foreign_key(self, instances, relationship_name, relationship_info):
        """Prefetch forward foreign key relationship (many-to-one)."""
        related_model = relationship_info["related_model"]
        foreign_key_field = relationship_info["foreign_key_field"]
        ref_field = relationship_info["ref_field"]

        # Collect foreign key values
        fk_values = [
            getattr(instance, foreign_key_field)
            for instance in instances
            if hasattr(instance, foreign_key_field) and getattr(instance, foreign_key_field) is not None
        ]
        if not fk_values:
            # Still need to attach None to all instances
            for instance in instances:
                instance._update_cache(relationship_name, None)
            return

        # Query related objects
        related_objects = (
            await related_model.objects.using(self.session)
            .filter(getattr(related_model, ref_field).in_(fk_values))
            .all()
        )

        # Create mapping
        related_map = {getattr(obj, ref_field): obj for obj in related_objects}

        # Attach to main instances using unified proxy_cache
        for instance in instances:
            fk_value = getattr(instance, foreign_key_field, None)
            if fk_value in related_map:
                instance._update_cache(relationship_name, related_map[fk_value])
            else:
                # Store None for instances without related objects
                instance._update_cache(relationship_name, None)

    @staticmethod
    def _find_through_model(through_table):
        """Find through table model."""
        from ...model import ObjectModel

        for subclass in ObjectModel.__subclasses__():
            try:
                if hasattr(subclass, "get_table"):
                    table = subclass.get_table()
                    if table.name == through_table:
                        return subclass
            except Exception:  # noqa
                continue
        return None

from sqlalchemy import tuple_

from .utils import RelationshipAnalyzer


class PrefetchHandler:
    """Handle prefetch_related operations for model relationships."""

    def __init__(self, session):
        self.session = session

    async def handle_prefetch_relationships(self, instances, prefetch_relationships):
        if not instances or not prefetch_relationships:
            return instances

        for relationship_name in prefetch_relationships:
            relationship_info = RelationshipAnalyzer.analyze_relationship(instances[0].__class__, relationship_name)
            if relationship_info:
                await self._prefetch_single_relationship(instances, relationship_name, relationship_info)

        return instances

    async def _prefetch_single_relationship(self, instances, relationship_name, relationship_info):
        rel_type = relationship_info["type"]

        if rel_type == "reverse_fk":
            await self._prefetch_by_fields(
                instances,
                relationship_name,
                relationship_info["related_model"],
                relationship_info["ref_fields"],
                relationship_info["foreign_key_fields"],
                [],
            )
        elif rel_type == "one_to_one":
            info = relationship_info
            await self._prefetch_by_fields(
                instances,
                relationship_name,
                info["related_model"],
                info["ref_fields"],
                info["foreign_key_fields"],
                None,
            )
        elif rel_type == "many_to_one":
            info = relationship_info
            await self._prefetch_by_fields(
                instances,
                relationship_name,
                info["related_model"],
                info["foreign_key_fields"],
                info["ref_fields"],
                None,
            )
        elif rel_type == "many_to_many":
            await self._prefetch_many_to_many(instances, relationship_name, relationship_info)

    async def _prefetch_by_fields(
        self, instances, relationship_name, related_model, lookup_fields, group_fields, empty
    ):
        """Unified prefetch for FK-based relationships."""
        composite = len(lookup_fields) > 1

        def make_key(obj, fields):
            return tuple(getattr(obj, f) for f in fields) if composite else getattr(obj, fields[0])

        lookup_values = [
            make_key(inst, lookup_fields)
            for inst in instances
            if all(getattr(inst, f, None) is not None for f in lookup_fields)
        ]
        if not lookup_values:
            for inst in instances:
                inst._update_cache(relationship_name, [] if isinstance(empty, list) else empty)
            return

        if composite:
            cols = [getattr(related_model, f) for f in group_fields]
            qs = related_model.objects.using(self.session).filter(tuple_(*cols).in_(lookup_values))
        else:
            qs = related_model.objects.using(self.session).filter(
                getattr(related_model, group_fields[0]).in_(lookup_values)
            )
        related_objects = await qs.all()

        if isinstance(empty, list):
            grouped = {}
            for obj in related_objects:
                grouped.setdefault(make_key(obj, group_fields), []).append(obj)
            for inst in instances:
                inst._update_cache(relationship_name, grouped.get(make_key(inst, lookup_fields), []))
        else:
            related_map = {make_key(obj, group_fields): obj for obj in related_objects}
            for inst in instances:
                inst._update_cache(relationship_name, related_map.get(make_key(inst, lookup_fields)))

    async def _prefetch_many_to_many(self, instances, relationship_name, relationship_info):
        """Prefetch many-to-many via through table."""
        related_model = relationship_info["related_model"]
        through_table = relationship_info["through_table"]
        left_field = relationship_info["left_field"]
        right_field = relationship_info["right_field"]
        left_ref_field = relationship_info["left_ref_field"]
        right_ref_field = relationship_info["right_ref_field"]

        instance_values = [
            getattr(inst, left_ref_field) for inst in instances if getattr(inst, left_ref_field, None) is not None
        ]
        if not instance_values:
            for inst in instances:
                inst._update_cache(relationship_name, [])
            return

        through_model = self._find_through_model(through_table)
        if not through_model:
            return

        through_objects = await (
            through_model.objects.using(self.session)
            .filter(getattr(through_model, left_field).in_(instance_values))
            .all()
        )

        related_values = [getattr(obj, right_field) for obj in through_objects]
        if not related_values:
            for inst in instances:
                inst._update_cache(relationship_name, [])
            return

        related_objects = await (
            related_model.objects.using(self.session)
            .filter(getattr(related_model, right_ref_field).in_(related_values))
            .all()
        )

        related_map = {getattr(obj, right_ref_field): obj for obj in related_objects}

        grouped = {}
        for through_obj in through_objects:
            main_val = getattr(through_obj, left_field)
            rel_val = getattr(through_obj, right_field)
            if rel_val in related_map:
                grouped.setdefault(main_val, []).append(related_map[rel_val])

        for inst in instances:
            key = getattr(inst, left_ref_field, None)
            inst._update_cache(relationship_name, grouped.get(key, []))

    @staticmethod
    def _find_through_model(through_table):
        from ...model import ObjectModel

        for subclass in ObjectModel.__subclasses__():
            try:
                if hasattr(subclass, "get_table") and subclass.get_table().name == through_table:
                    return subclass
            except Exception:  # noqa
                continue
        return None

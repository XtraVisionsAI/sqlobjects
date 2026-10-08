from sqlalchemy import tuple_

from .utils import RelationshipAnalyzer


class PrefetchHandler:
    """Handle prefetch_related operations for model relationships."""

    def __init__(self, session):
        self.session = session

    async def handle_prefetch_relationships(self, instances, prefetch_relationships, configs=None):
        if not instances:
            return instances
        for path in sorted(prefetch_relationships):
            name, _, remainder = path.partition("__")
            info = RelationshipAnalyzer.analyze_relationship(instances[0].__class__, name)
            if not info:
                raise ValueError(f"Invalid relationship '{name}'")
            custom = (configs or {}).get(path) if not remainder else None
            await self._prefetch_single_relationship(instances, name, info, custom)
            if remainder:
                related = []
                for instance in instances:
                    value = instance._state_manager.get_object_cache().get(name)
                    related.extend(value if isinstance(value, list) else [value] if value is not None else [])
                await self.handle_prefetch_relationships(
                    related, {remainder}, {remainder: configs[path]} if configs and path in configs else None
                )
        return instances

    async def _prefetch_single_relationship(self, instances, relationship_name, relationship_info, queryset=None):
        info = relationship_info
        if queryset is not None and queryset._model_class is not info["related_model"]:
            raise ValueError(f"Prefetch queryset model does not match relationship '{relationship_name}'")
        if info["type"] == "many_to_many":
            await self._prefetch_many_to_many(instances, relationship_name, info, queryset)
            return
        local, remote = (
            (info["foreign_key_fields"], info["ref_fields"])
            if info["type"] == "many_to_one"
            else (info["ref_fields"], info["foreign_key_fields"])
        )
        empty = [] if info["type"] == "reverse_fk" else None
        await self._prefetch_by_fields(
            instances, relationship_name, info["related_model"], local, remote, empty, queryset
        )

    async def _prefetch_by_fields(
        self, instances, relationship_name, related_model, lookup_fields, group_fields, empty, queryset=None
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

        qs = related_model.objects.using(self.session) if queryset is None else queryset
        if queryset is not None and queryset._db_or_session is None:
            qs = queryset.using(self.session)
        if queryset is not None and (
            queryset._builder.limits is not None or queryset._builder.offset_value is not None
        ):
            raise ValueError(
                "Sliced prefetch querysets are not supported; a global limit would truncate related collections"
            )
        if queryset is not None and queryset._builder.selected_fields:
            qs = qs.only(*group_fields)
        if composite:
            qs = qs.filter(tuple_(*(getattr(related_model, f) for f in group_fields)).in_(lookup_values))
        else:
            qs = qs.filter(getattr(related_model, group_fields[0]).in_(lookup_values))
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

    async def _prefetch_many_to_many(self, instances, relationship_name, relationship_info, queryset=None):
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

        from sqlalchemy import select

        table = instances[0].__class__.__registry__.tables[through_table]
        result = await self.session.execute(
            select(table.c[left_field], table.c[right_field]).where(table.c[left_field].in_(instance_values))
        )
        through_objects = result.fetchall()
        related_values = [getattr(obj, right_field) for obj in through_objects]
        if not related_values:
            for inst in instances:
                inst._update_cache(relationship_name, [])
            return
        qs = related_model.objects.using(self.session) if queryset is None else queryset
        if queryset is not None:
            if queryset._builder.limits is not None or queryset._builder.offset_value is not None:
                raise ValueError("Sliced prefetch querysets are not supported")
            if queryset._db_or_session is None:
                qs = qs.using(self.session)
            if queryset._builder.selected_fields:
                qs = qs.only(right_ref_field)
        related_objects = await qs.filter(getattr(related_model, right_ref_field).in_(related_values)).all()

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

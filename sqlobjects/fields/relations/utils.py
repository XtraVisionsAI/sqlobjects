from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy import Column, ForeignKey, Table

from ...cascade import CascadeType, normalize_cascade
from .descriptors import RelationshipProperty, RelationshipType


T = TypeVar("T")

if TYPE_CHECKING:
    from ...model import ObjectModel


@dataclass
class M2MTable:
    """Many-to-Many table definition with flexible field mapping.

    Supports custom field names and non-primary key references for complex scenarios.
    """

    table_name: str
    left_model: str
    right_model: str
    left_field: str | None = None  # M2M table left foreign key field name
    right_field: str | None = None  # M2M table right foreign key field name
    left_ref_field: str | None = None  # Left model reference field name
    right_ref_field: str | None = None  # Right model reference field name

    def __post_init__(self):
        """Fill default field names if not provided."""
        if self.left_field is None:
            self.left_field = f"{self.left_model.lower()}_id"
        if self.right_field is None:
            self.right_field = f"{self.right_model.lower()}_id"
        if self.left_ref_field is None:
            self.left_ref_field = "id"
        if self.right_ref_field is None:
            self.right_ref_field = "id"

    def create_table(self, metadata: Any, left_table: Any, right_table: Any) -> Table:
        """Create SQLAlchemy Table for this M2M relationship.

        Args:
            metadata: SQLAlchemy MetaData instance
            left_table: Left model's table
            right_table: Right model's table

        Returns:
            SQLAlchemy Table instance for the M2M relationship
        """
        # Get reference columns
        left_ref_col = left_table.c[self.left_ref_field]
        right_ref_col = right_table.c[self.right_ref_field]

        return Table(
            self.table_name,
            metadata,
            Column(
                self.left_field,
                left_ref_col.type,
                ForeignKey(f"{left_table.name}.{self.left_ref_field}"),
                primary_key=True,
            ),
            Column(
                self.right_field,
                right_ref_col.type,
                ForeignKey(f"{right_table.name}.{self.right_ref_field}"),
                primary_key=True,
            ),
        )


class RelationshipResolver:
    """Relationship type resolver."""

    @staticmethod
    def resolve_relationship_type(property_: RelationshipProperty) -> str:
        if property_.secondary:
            property_.is_many_to_many = True
            property_.uselist = True
            return RelationshipType.MANY_TO_MANY
        elif property_.foreign_keys:
            if property_.uselist is None:
                property_.uselist = False
            return RelationshipType.MANY_TO_ONE
        else:
            # remote_fields or no hint — one_to_many or one_to_one
            if property_.uselist is None:
                property_.uselist = True
            return RelationshipType.ONE_TO_ONE if property_.uselist is False else RelationshipType.ONE_TO_MANY


def relationship(
    argument: str | type["ObjectModel"],
    *,
    foreign_keys: str | list[str] | None = None,
    remote_fields: str | list[str] | None = None,
    back_populates: str | None = None,
    backref: str | None = None,
    lazy: str = "select",
    uselist: bool | None = None,
    secondary: str | M2MTable | None = None,
    primaryjoin: str | None = None,
    secondaryjoin: str | None = None,
    order_by: str | list[str] | None = None,
    cascade: CascadeType = None,
    passive_deletes: bool = False,
    **kwargs: Any,
) -> Any:
    """Define model relationship.

    Args:
        argument: Target model class or string name
        foreign_keys: FK field name(s) on this model (many_to_one side)
        remote_fields: FK field name(s) on the related model (one_to_many/one_to_one side)
        back_populates: Name of reverse relationship attribute
        backref: Name for automatic reverse relationship
        lazy: Loading strategy
        uselist: Whether relationship returns a list
        secondary: M2M table name or M2MTable instance
        primaryjoin: Custom primary join condition
        secondaryjoin: Custom secondary join condition for M2M
        order_by: Default ordering for collections
        cascade: Cascade behavior
        passive_deletes: Whether to use passive deletes
    """
    if back_populates and backref:
        raise ValueError("Cannot specify both 'back_populates' and 'backref'")

    cascade_str = normalize_cascade(cascade)

    secondary_table_name = None
    m2m_def = None
    if isinstance(secondary, M2MTable):
        m2m_def = secondary
        secondary_table_name = secondary.table_name
    elif isinstance(secondary, str):
        secondary_table_name = secondary

    property_ = RelationshipProperty(
        argument=argument,
        foreign_keys=foreign_keys,
        remote_fields=remote_fields,
        back_populates=back_populates,
        backref=backref,
        lazy=lazy,
        uselist=uselist,
        secondary=secondary_table_name,
        primaryjoin=primaryjoin,
        secondaryjoin=secondaryjoin,
        order_by=order_by,
        cascade=cascade_str,
        passive_deletes=passive_deletes,
        **kwargs,
    )

    if m2m_def:
        property_.m2m_definition = m2m_def  # type: ignore[reportAttributeAccessIssue]
        property_.is_many_to_many = True

    from ..core import Related

    return Related(is_relationship=True, relationship_property=property_, m2m_definition=m2m_def)


class RelationshipAnalyzer:
    """Analyze model relationships and extract metadata for prefetch operations."""

    @staticmethod
    @lru_cache(maxsize=256)
    def analyze_relationship(model_class, relationship_name):
        try:
            if hasattr(model_class, relationship_name):
                field_attr = getattr(model_class, relationship_name)
                if hasattr(field_attr, "property"):
                    return RelationshipAnalyzer._extract_relationship_info(model_class, field_attr.property)
            return RelationshipAnalyzer._infer_reverse_relationship(model_class, relationship_name)
        except Exception:  # noqa
            return None

    @staticmethod
    def _extract_relationship_info(model_class, prop):
        related_model = RelationshipAnalyzer._resolve_model_class(prop.argument)
        if not related_model:
            return None

        # many_to_many
        if prop.secondary:
            m2m_def = getattr(prop, "m2m_definition", None)
            if not m2m_def:
                return None
            return {
                "type": "many_to_many",
                "related_model": related_model,
                "through_table": prop.secondary,
                "left_field": m2m_def.left_field,
                "right_field": m2m_def.right_field,
                "left_ref_field": m2m_def.left_ref_field,
                "right_ref_field": m2m_def.right_ref_field,
            }

        # many_to_one — FK is on this model
        if prop.foreign_keys:
            from .descriptors import _normalize_fields

            fks = _normalize_fields(prop.foreign_keys)
            ref_fields = RelationshipAnalyzer._scan_ref_fields(model_class, fks, related_model)
            return {
                "type": "many_to_one",
                "related_model": related_model,
                "foreign_key_fields": fks,
                "ref_fields": ref_fields,
            }

        # one_to_many / one_to_one — FK is on the related model
        rel_type = "one_to_one" if prop.uselist is False else "reverse_fk"

        if prop.remote_fields:
            from .descriptors import _normalize_fields

            rf = prop.remote_fields
            foreign_key_fields = _normalize_fields(rf) if isinstance(rf, (str, list)) else None
            if not foreign_key_fields:
                foreign_key_fields, ref_fields = RelationshipAnalyzer._scan_fk_fields(related_model, model_class, prop)
            else:
                ref_fields = RelationshipAnalyzer._scan_ref_fields(related_model, foreign_key_fields, model_class)
        else:
            foreign_key_fields, ref_fields = RelationshipAnalyzer._scan_fk_fields(related_model, model_class, prop)

        return {
            "type": rel_type,
            "related_model": related_model,
            "foreign_key_fields": foreign_key_fields,
            "ref_fields": ref_fields,
        }

    @staticmethod
    def _scan_fk_fields(related_model, current_model, prop):
        """Scan related model's columns to find FK(s) pointing to current model's table."""
        try:
            current_table = current_model.__table__
            related_table = related_model.__table__
        except AttributeError:
            raise ValueError(
                f"Cannot resolve relationship: model tables not available. "
                f"Use 'remote_fields' to specify the FK field on {related_model.__name__}."
            ) from None

        candidates = [
            (col.name, [fk.column.name for fk in col.foreign_keys if fk.column.table == current_table])
            for col in related_table.columns
            if any(fk.column.table == current_table for fk in col.foreign_keys)
        ]

        if not candidates:
            # Fallback: try back_populates
            if prop.back_populates and hasattr(related_model, prop.back_populates):
                back_attr = getattr(related_model, prop.back_populates)
                if hasattr(back_attr, "property") and back_attr.property.foreign_keys:
                    fks = back_attr.property.foreign_keys
                    refs = [RelationshipAnalyzer._extract_ref_field(fk) for fk in fks]
                    return fks, refs
            raise ValueError(
                f"No foreign key found on '{related_model.__name__}' pointing to '{current_model.__name__}'. "
                f"Use 'remote_fields' to specify the FK field."
            )

        if len(candidates) > 1:
            names = [c[0] for c in candidates]
            raise ValueError(
                f"Multiple foreign keys found on '{related_model.__name__}' pointing to "
                f"'{current_model.__name__}': {names}. Use 'remote_fields' to specify which one."
            )

        fk_col_name, ref_col_names = candidates[0]
        return [fk_col_name], ref_col_names if ref_col_names else ["id"]

    @staticmethod
    def _scan_ref_fields(related_model, foreign_key_fields, current_model):
        """Given FK field names on related model, find the referenced columns on current model."""
        try:
            related_table = related_model.__table__
        except AttributeError:
            return ["id"] * len(foreign_key_fields)

        ref_fields = []
        for fk_name in foreign_key_fields:
            if fk_name in related_table.c:
                col = related_table.c[fk_name]
                refs = [fk.column.name for fk in col.foreign_keys]
                ref_fields.append(refs[0] if refs else "id")
            else:
                ref_fields.append("id")
        return ref_fields

    @staticmethod
    def _extract_ref_field(foreign_key_spec):
        if isinstance(foreign_key_spec, str) and "." in foreign_key_spec:
            return foreign_key_spec.split(".", 1)[1]
        return foreign_key_spec if isinstance(foreign_key_spec, str) else "id"

    @staticmethod
    def _infer_reverse_relationship(model_class, relationship_name):
        return None

    @staticmethod
    def _resolve_model_class(argument):
        if isinstance(argument, str):
            from ...model import ObjectModel

            for subclass in ObjectModel.__subclasses__():
                if hasattr(subclass, "__registry__"):
                    try:
                        return subclass.__registry__.get_model(argument)
                    except Exception:
                        continue

            def find_subclass(base_class):
                for subclass in base_class.__subclasses__():
                    if subclass.__name__ == argument:
                        return subclass
                    found = find_subclass(subclass)
                    if found:
                        return found
                return None

            return find_subclass(ObjectModel)
        return argument

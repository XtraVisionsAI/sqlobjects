from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, ForeignKey, Table

from ...cascade import CascadeType, normalize_cascade
from .descriptors import RelationshipProperty, RelationshipType


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
        """Automatically infer relationship type based on parameters.

        Args:
            property_: RelationshipProperty instance to analyze

        Returns:
            String representing the relationship type
        """
        # Handle explicit uselist setting
        if property_.uselist is False:
            return RelationshipType.MANY_TO_ONE if property_.foreign_keys else RelationshipType.ONE_TO_ONE
        elif property_.uselist:
            return RelationshipType.MANY_TO_MANY if property_.secondary else RelationshipType.ONE_TO_MANY

        # Auto-infer based on parameters
        if property_.secondary:
            property_.is_many_to_many = True
            property_.uselist = True
            return RelationshipType.MANY_TO_MANY
        elif property_.foreign_keys:
            property_.uselist = False
            return RelationshipType.MANY_TO_ONE
        else:
            property_.uselist = True
            return RelationshipType.ONE_TO_MANY


def relationship(
    argument: str | type["ObjectModel"],
    *,
    foreign_keys: str | list[str] | None = None,
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
):
    """Define model relationship with SQLAlchemy-compatible cascade behavior.

    Args:
        argument: Target model class or string name
        foreign_keys: Foreign key field name(s)
        back_populates: Name of reverse relationship attribute
        backref: Name for automatic reverse relationship
        lazy: Loading strategy ('select', 'dynamic', 'noload', 'raise')
        uselist: Whether relationship returns a list
        secondary: M2M table name or M2MTable instance
        primaryjoin: Custom primary join condition
        secondaryjoin: Custom secondary join condition for M2M
        order_by: Default ordering for collections
        cascade: Application-layer cascade behavior (SQLAlchemy compatible)
        passive_deletes: Whether to use passive deletes
        **kwargs: Additional relationship options

    Returns:
        Column instance marked as relationship field with cascade configuration

    Raises:
        ValueError: If both back_populates and backref are specified

    Example:
        # Type-safe enum usage
        posts = relationship("Post", cascade={CascadeOption.ALL, CascadeOption.DELETE_ORPHAN})

        # Preset constants
        comments = relationship("Comment", cascade=CascadePresets.ALL_DELETE_ORPHAN)

        # SQLAlchemy string format
        tags = relationship("Tag", cascade="all, delete-orphan")
    """

    # Validate mutually exclusive parameters
    if back_populates and backref:
        raise ValueError("Cannot specify both 'back_populates' and 'backref'")

    # Normalize cascade parameter to SQLAlchemy string format
    cascade_str = normalize_cascade(cascade)

    # Handle M2M table definition
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
        back_populates=back_populates,
        backref=backref,
        lazy=lazy,
        uselist=uselist,
        secondary=secondary_table_name,
        primaryjoin=primaryjoin,
        secondaryjoin=secondaryjoin,
        order_by=order_by,
        cascade=cascade_str,  # Use normalized string
        passive_deletes=passive_deletes,
        **kwargs,
    )

    # Set M2M definition if provided
    if m2m_def:
        property_.m2m_definition = m2m_def  # type: ignore[reportAttributeAccessIssue]
        property_.is_many_to_many = True

    # Return our own Column instance, marked as relationship field
    from ..core import Column

    return Column[Any](is_relationship=True, relationship_property=property_)


class RelationshipAnalyzer:
    """Analyze model relationships and extract metadata for prefetch operations."""

    @staticmethod
    def analyze_relationship(model_class, relationship_name):
        """Analyze relationship type and extract related information.

        Args:
            model_class: Main model class
            relationship_name: Relationship field name

        Returns:
            dict: Relationship info dict with type, related model, field mappings
        """
        try:
            # Check explicit relationship definition
            if hasattr(model_class, relationship_name):
                field_attr = getattr(model_class, relationship_name)
                if hasattr(field_attr, "property"):
                    return RelationshipAnalyzer._extract_relationship_info(model_class, field_attr.property)

            # Infer reverse relationship
            return RelationshipAnalyzer._infer_reverse_relationship(model_class, relationship_name)
        except Exception:  # noqa
            return None

    @staticmethod
    def _extract_relationship_info(model_class, prop):
        """Extract information from relationship property."""
        related_model = RelationshipAnalyzer._resolve_model_class(prop.argument)
        if not related_model:
            return None

        if prop.secondary:  # Many-to-many relationship
            m2m_def = getattr(prop, "m2m_definition", None)
            if m2m_def:
                return {
                    "type": "many_to_many",
                    "related_model": related_model,
                    "through_table": prop.secondary,
                    "left_field": m2m_def.left_field,
                    "right_field": m2m_def.right_field,
                    "left_ref_field": m2m_def.left_ref_field,
                    "right_ref_field": m2m_def.right_ref_field,
                }
            else:
                # String-only secondary table - cannot determine field mappings without M2MTable definition
                return None

        elif prop.foreign_keys:  # Many-to-one (forward foreign key)
            return {
                "type": "many_to_one",
                "related_model": related_model,
                "foreign_key_field": prop.foreign_keys,
                "ref_field": RelationshipAnalyzer._extract_ref_field(prop.foreign_keys),
            }

        else:  # One-to-many or one-to-one (reverse relationship)
            # Try to find the correct foreign key field from back_populates
            foreign_key_field = f"{model_class.__name__.lower()}_id"  # Default

            if prop.back_populates:
                # Look for the corresponding relationship in the related model
                if hasattr(related_model, prop.back_populates):
                    back_attr = getattr(related_model, prop.back_populates)
                    if hasattr(back_attr, "property") and back_attr.property.foreign_keys:
                        foreign_key_field = back_attr.property.foreign_keys

            # Determine if it's one-to-one or one-to-many based on uselist
            rel_type = "one_to_one" if prop.uselist is False else "reverse_fk"

            return {
                "type": rel_type,
                "related_model": related_model,
                "foreign_key_field": foreign_key_field,
                "ref_field": "id",
            }

    @staticmethod
    def _extract_ref_field(foreign_key_spec):
        """Extract reference field from foreign key specification."""
        if isinstance(foreign_key_spec, str) and "." in foreign_key_spec:
            return foreign_key_spec.split(".", 1)[1]
        return "id"  # Default to primary key

    @staticmethod
    def _infer_reverse_relationship(model_class, relationship_name):
        """Infer reverse relationship (e.g., User.posts)."""
        # posts -> Post, comments -> Comment
        related_model_name = relationship_name.rstrip("s").capitalize()
        related_model = RelationshipAnalyzer._resolve_model_class(related_model_name)

        if related_model:
            # Check if related model has foreign key pointing to current model
            foreign_key_field = f"{model_class.__name__.lower()}_id"
            try:
                if hasattr(related_model, foreign_key_field):
                    return {
                        "type": "reverse_fk",
                        "related_model": related_model,
                        "foreign_key_field": foreign_key_field,
                        "ref_field": "id",
                    }
            except Exception:  # noqa
                pass

        return None

    @staticmethod
    def _resolve_model_class(argument):
        """Resolve model class from string or class argument."""
        if isinstance(argument, str):
            from ...model import ObjectModel

            # Try to get any ObjectModel subclass to access the registry
            for subclass in ObjectModel.__subclasses__():
                if hasattr(subclass, "__registry__"):
                    try:
                        return subclass.__registry__.get_model(argument)
                    except Exception:
                        continue

            # Fallback to recursive search if registry lookup fails
            def find_subclass(base_class):
                """Recursively find subclass by name."""
                for subclass in base_class.__subclasses__():
                    if subclass.__name__ == argument:
                        return subclass
                    # Recursively search in subclasses
                    found = find_subclass(subclass)
                    if found:
                        return found
                return None

            return find_subclass(ObjectModel)
        return argument

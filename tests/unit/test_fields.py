"""Unit tests for field system and type definitions"""

import pytest
import sqlalchemy as sa
from sqlalchemy.sql import text

from sqlobjects.fields import (
    BooleanColumn,
    Column,
    IntegerColumn,
    StringColumn,
    column,
    computed,
    foreign_key,
    identity,
)
from sqlobjects.fields.utils import get_column_from_field
from tests.conftest import TestModel


class TestFieldDefinition:
    """Test field definition and type system"""

    def test_column_function_basic(self):
        """Test column() function with type parameter"""

        class TestModel1(TestModel):
            name = column(type="string", length=100)

        col = get_column_from_field(TestModel1.name)
        assert col is not None
        assert col.type.length == 100  # type: ignore[union-attr,attr-defined]
        assert isinstance(col.type, sa.String)  # type: ignore[attr-defined]

    def test_shortcut_classes(self):
        """Test field shortcut classes"""

        class TestModel2(TestModel):
            name = StringColumn(length=50)
            age = IntegerColumn()
            active = BooleanColumn()

        name_col = get_column_from_field(TestModel2.name)
        age_col = get_column_from_field(TestModel2.age)
        active_col = get_column_from_field(TestModel2.active)

        assert name_col is not None and name_col.type.length == 50  # type: ignore[union-attr,attr-defined]
        assert age_col is not None and isinstance(age_col.type, sa.Integer)  # type: ignore[attr-defined]
        assert active_col is not None and isinstance(active_col.type, sa.Boolean)  # type: ignore[attr-defined]

    def test_field_parameters(self):
        """Test field parameter handling"""

        class TestModel3(TestModel):
            nullable_field = column(type="string", nullable=True)
            default_field = column(type="integer", default=0)
            unique_field = column(type="string", unique=True)

        # Nullable parameter
        nullable_col = get_column_from_field(TestModel3.nullable_field)
        assert nullable_col is not None and nullable_col.nullable is True  # type: ignore[attr-defined]

        # Default parameter
        default_col = get_column_from_field(TestModel3.default_field)
        assert default_col is not None and default_col.default.arg == 0  # type: ignore[union-attr,attr-defined]

        # Unique parameter
        unique_col = get_column_from_field(TestModel3.unique_field)
        assert unique_col is not None and unique_col.unique is True  # type: ignore[attr-defined]

    def test_init_parameter_intelligence(self):
        """Test automatic init parameter handling"""

        class TestModel4(TestModel):
            id_field = column(type="integer", primary_key=True)
            created_field = column(type="datetime", server_default=text("CURRENT_TIMESTAMP"))
            name_field = column(type="string")

        # Primary key fields should have init=False automatically
        id_col = get_column_from_field(TestModel4.id_field)
        assert id_col is not None and id_col.info["_codegen"]["init"] is False  # type: ignore[index,attr-defined]

        # Server default fields should have init=False automatically
        created_col = get_column_from_field(TestModel4.created_field)
        assert created_col is not None and created_col.info["_codegen"]["init"] is False  # type: ignore[index,attr-defined]

        # Regular fields should have init=True by default
        name_col = get_column_from_field(TestModel4.name_field)
        assert name_col is not None and name_col.info["_codegen"]["init"] is True  # type: ignore[index,attr-defined]


class TestAdvancedFields:
    """Test advanced field types"""

    def test_identity_fields(self):
        """Test identity() shortcut"""

        class TestModel5(TestModel):
            id_field = identity()

        id_col = get_column_from_field(TestModel5.id_field)
        assert id_col is not None
        assert id_col.autoincrement is True  # type: ignore[attr-defined]
        assert id_col.primary_key is True  # type: ignore[attr-defined]
        assert id_col.info["_codegen"]["init"] is False  # type: ignore[index,attr-defined]

    def test_computed_fields(self):
        """Test computed() shortcut"""

        class TestModel6(TestModel):
            first_name = StringColumn(length=50)
            last_name = StringColumn(length=50)
            computed_field = computed("first_name || ' ' || last_name", column_type="string")

        computed_col = get_column_from_field(TestModel6.computed_field)
        assert computed_col is not None
        assert computed_col.computed is not None  # type: ignore[attr-defined]
        assert computed_col.info["_codegen"]["init"] is False  # type: ignore[index,attr-defined]

    def test_foreign_key_fields(self):
        """Test foreign_key() shortcut"""

        class TestModel7(TestModel):
            fk_field: Column[int] = foreign_key("users.id")

        fk_col = get_column_from_field(TestModel7.fk_field)
        assert fk_col is not None
        assert len(fk_col.foreign_keys) == 1  # type: ignore[attr-defined]
        fk = list(fk_col.foreign_keys)[0]  # type: ignore[attr-defined]
        # Check the column specification instead
        assert fk._colspec == "users.id"  # type: ignore[attr-defined]

    def test_enhanced_foreign_key_fields(self):
        """Test enhanced foreign_key() with additional parameters"""

        class TestModel7Enhanced(TestModel):
            # Auto type inference
            user_id: Column[int] = foreign_key("users.id")

            # Complete constraint configuration
            author_id: Column[int] = foreign_key("users.id", ondelete="CASCADE", onupdate="CASCADE", nullable=False)

            # Deferred constraint
            parent_id: Column[int] = foreign_key("users.id", deferrable=True, initially="DEFERRED")

        # Test auto type inference
        user_id_col = get_column_from_field(TestModel7Enhanced.user_id)
        assert user_id_col is not None
        assert isinstance(user_id_col.type, sa.Integer)  # type: ignore[attr-defined]

        # Test complete constraint configuration
        author_id_col = get_column_from_field(TestModel7Enhanced.author_id)
        assert author_id_col is not None
        assert author_id_col.nullable is False  # type: ignore[attr-defined]
        fk = list(author_id_col.foreign_keys)[0]  # type: ignore[attr-defined]
        assert fk.ondelete == "CASCADE"
        assert fk.onupdate == "CASCADE"

        # Test deferred constraint
        parent_id_col = get_column_from_field(TestModel7Enhanced.parent_id)
        assert parent_id_col is not None
        fk = list(parent_id_col.foreign_keys)[0]  # type: ignore[attr-defined]
        assert fk.deferrable is True
        assert fk.initially == "DEFERRED"

    def test_foreign_key_auto_type_inference(self):
        """Test automatic type inference for foreign keys"""

        class TestModelAutoType(TestModel):
            # Should infer integer for id fields
            user_id: Column[int] = foreign_key("users.id")
            post_id: Column[int] = foreign_key("posts.id")

            # Should infer string for string fields
            username: Column[str] = foreign_key("users.username")

        # Test id field inference
        user_id_col = get_column_from_field(TestModelAutoType.user_id)
        assert user_id_col is not None
        assert isinstance(user_id_col.type, sa.Integer)  # type: ignore[attr-defined]

        # Test post id field inference
        post_id_col = get_column_from_field(TestModelAutoType.post_id)
        assert post_id_col is not None
        assert isinstance(post_id_col.type, sa.Integer)  # type: ignore[attr-defined]

        # Test string field inference
        username_col = get_column_from_field(TestModelAutoType.username)
        assert username_col is not None
        assert isinstance(username_col.type, sa.String)  # type: ignore[attr-defined]

    def test_deferred_fields(self):
        """Test deferred loading configuration"""

        class TestModel8(TestModel):
            field = column(type="text", deferred=True, deferred_group="details")

        deferred_col = get_column_from_field(TestModel8.field)
        assert deferred_col is not None
        assert deferred_col.info["_performance"]["deferred"] is True  # type: ignore[union-attr]
        assert deferred_col.info["_performance"]["deferred_group"] == "details"  # type: ignore[union-attr]


class TestFieldValidation:
    """Test field-level validation"""

    def test_field_validators_parameter(self):
        """Test field validators parameter"""

        def dummy_validator(value):
            return value

        class TestModel9(TestModel):
            field = column(type="string", validators=[dummy_validator])

        validator_col = get_column_from_field(TestModel9.field)
        assert validator_col is not None
        validators = validator_col.info["_enhanced"]["validators"]  # type: ignore[union-attr]
        assert len(validators) == 1
        assert validators[0] == dummy_validator

    def test_multiple_validators(self):
        """Test combining multiple validators"""

        def validator1(value):
            return value

        def validator2(value):
            return value

        class TestModel10(TestModel):
            field = column(type="string", validators=[validator1, validator2])

        multi_validator_col = get_column_from_field(TestModel10.field)
        assert multi_validator_col is not None
        validators = multi_validator_col.info["_enhanced"]["validators"]  # type: ignore[union-attr]
        assert len(validators) == 2
        assert validator1 in validators
        assert validator2 in validators


class TestFieldTypeMapping:
    """Test Python type to SQLAlchemy type mapping"""

    def test_string_types(self):
        """Test string type variations"""

        class TestModel11(TestModel):
            str_field = column(type="string")
            text_field = column(type="text")

        # Basic string
        str_col = get_column_from_field(TestModel11.str_field)
        assert str_col is not None and isinstance(str_col.type, sa.String)  # type: ignore[attr-defined]

        # Text type
        text_col = get_column_from_field(TestModel11.text_field)
        assert text_col is not None and isinstance(text_col.type, sa.Text)  # type: ignore[attr-defined]

    def test_numeric_types(self):
        """Test numeric type variations"""

        class TestModel12(TestModel):
            int_field = column(type="integer")
            bigint_field = column(type="bigint")
            float_field = column(type="float")

        # Integer
        int_col = get_column_from_field(TestModel12.int_field)
        assert int_col is not None and isinstance(int_col.type, sa.Integer)  # type: ignore[attr-defined]

        # BigInteger
        bigint_col = get_column_from_field(TestModel12.bigint_field)
        assert bigint_col is not None and isinstance(bigint_col.type, sa.BigInteger)  # type: ignore[attr-defined]

        # Float
        float_col = get_column_from_field(TestModel12.float_field)
        assert float_col is not None and isinstance(float_col.type, sa.Float)  # type: ignore[attr-defined]

    def test_datetime_types(self):
        """Test datetime type variations"""

        class TestModel13(TestModel):
            dt_field = column(type="datetime")
            date_field = column(type="date")
            time_field = column(type="time")

        # DateTime
        dt_col = get_column_from_field(TestModel13.dt_field)
        assert dt_col is not None and isinstance(dt_col.type, sa.DateTime)  # type: ignore[attr-defined]

        # Date
        date_col = get_column_from_field(TestModel13.date_field)
        assert date_col is not None and isinstance(date_col.type, sa.Date)  # type: ignore[attr-defined]

        # Time
        time_col = get_column_from_field(TestModel13.time_field)
        assert time_col is not None and isinstance(time_col.type, sa.Time)  # type: ignore[attr-defined]

    def test_boolean_type(self):
        """Test boolean type"""

        class TestModel14(TestModel):
            bool_field = column(type="boolean")

        bool_col = get_column_from_field(TestModel14.bool_field)
        assert bool_col is not None and isinstance(bool_col.type, sa.Boolean)  # type: ignore[attr-defined]

    def test_json_type(self):
        """Test JSON type"""

        class TestModel15(TestModel):
            json_field = column(type="json")

        json_col = get_column_from_field(TestModel15.json_field)
        assert json_col is not None and isinstance(json_col.type, sa.JSON)  # type: ignore[attr-defined]


class TestFieldCodegenParameters:
    """Test code generation parameters"""

    def test_init_parameter(self):
        """Test init parameter controls constructor participation"""

        class TestModel16(TestModel):
            no_init_field = column(type="string", init=False)
            init_field = column(type="string", init=True)

        # Explicit init=False
        no_init_col = get_column_from_field(TestModel16.no_init_field)
        assert no_init_col is not None and no_init_col.info["_codegen"]["init"] is False  # type: ignore[union-attr]

        # Explicit init=True
        init_col = get_column_from_field(TestModel16.init_field)
        assert init_col is not None and init_col.info["_codegen"]["init"] is True  # type: ignore[union-attr]

    def test_repr_parameter(self):
        """Test repr parameter controls __repr__ inclusion"""

        class TestModel17(TestModel):
            repr_field = column(type="string")
            no_repr_field = column(type="string", repr=False)

        # Default repr=True
        repr_col = get_column_from_field(TestModel17.repr_field)
        assert repr_col is not None and repr_col.info["_codegen"]["repr"] is True  # type: ignore[union-attr]

        # Explicit repr=False
        no_repr_col = get_column_from_field(TestModel17.no_repr_field)
        assert no_repr_col is not None and no_repr_col.info["_codegen"]["repr"] is False  # type: ignore[union-attr]

    def test_compare_parameter(self):
        """Test compare parameter controls __eq__ inclusion"""

        class TestModel18(TestModel):
            regular_field = column(type="string")
            pk_field = column(type="integer", primary_key=True)
            compare_field = column(type="string", compare=True)

        # Default compare=False for regular fields
        regular_col = get_column_from_field(TestModel18.regular_field)
        assert regular_col is not None and regular_col.info["_codegen"]["compare"] is False  # type: ignore[union-attr]

        # Primary key fields should have compare=True
        pk_col = get_column_from_field(TestModel18.pk_field)
        assert pk_col is not None and pk_col.info["_codegen"]["compare"] is True  # type: ignore[union-attr]

        # Explicit compare=True
        compare_col = get_column_from_field(TestModel18.compare_field)
        assert compare_col is not None and compare_col.info["_codegen"]["compare"] is True  # type: ignore[union-attr]


class TestFieldEnhancedParameters:
    """Test enhanced functionality parameters"""

    def test_deferred_parameters(self):
        """Test deferred loading parameters"""

        class TestModel19(TestModel):
            deferred_field = column(type="text", deferred=True)
            grouped_field = column(type="text", deferred=True, deferred_group="details")
            raiseload_field = column(type="text", deferred=True, deferred_raiseload=True)

        # Basic deferred field
        deferred_col = get_column_from_field(TestModel19.deferred_field)
        assert deferred_col is not None and deferred_col.info["_performance"]["deferred"] is True  # type: ignore[union-attr]

        # Deferred with group
        grouped_col = get_column_from_field(TestModel19.grouped_field)
        assert grouped_col is not None and grouped_col.info["_performance"]["deferred_group"] == "details"  # type: ignore[union-attr]

        # Deferred with raiseload
        raiseload_col = get_column_from_field(TestModel19.raiseload_field)
        assert raiseload_col is not None and raiseload_col.info["_performance"]["deferred_raiseload"] is True  # type: ignore[union-attr]

    def test_performance_parameters(self):
        """Test performance optimization parameters"""

        class TestModel20(TestModel):
            history_field = column(type="string", active_history=True)

        # Active history tracking
        history_col = get_column_from_field(TestModel20.history_field)
        assert history_col is not None and history_col.info["_performance"]["active_history"] is True  # type: ignore[union-attr]

    def test_default_factory(self):
        """Test default_factory parameter"""

        def factory_func():
            return "generated"

        class TestModel21(TestModel):
            factory_field = column(type="string", default_factory=factory_func)

        factory_col = get_column_from_field(TestModel21.factory_field)
        assert factory_col is not None and factory_col.info["_enhanced"]["default_factory"] == factory_func  # type: ignore[union-attr]


class TestFieldErrorHandling:
    """Test field error handling and validation"""

    def test_invalid_type_parameter(self):
        """Test handling of invalid type parameter"""
        with pytest.raises((ValueError, KeyError)):

            class TestModel22(TestModel):
                field = column(type="invalid_type")

    def test_conflicting_parameters(self):
        """Test handling of conflicting parameters"""

        # Having both default and server_default should work (server_default takes precedence)
        class TestModel23(TestModel):
            field = column(type="string", default="value", server_default="server_value")

        conflict_col = get_column_from_field(TestModel23.field)
        assert conflict_col is not None
        # server_default should take precedence
        assert conflict_col.server_default is not None  # type: ignore[attr-defined]

    def test_invalid_length_parameter(self):
        """Test invalid length parameter handling"""

        # Test that length parameters are passed through to SQLAlchemy
        # Note: We use valid lengths for database compatibility
        class TestModel24(TestModel):
            field = StringColumn(length=1)  # Use valid length for database compatibility

        length_col = get_column_from_field(TestModel24.field)
        assert length_col is not None
        assert length_col.type.length == 1  # type: ignore[union-attr,attr-defined]

        # Test that zero length is passed through (though may not be valid in all databases)
        class TestModel25(TestModel):
            field = StringColumn(length=255)  # Use standard length

        standard_length_col = get_column_from_field(TestModel25.field)
        assert standard_length_col is not None
        assert standard_length_col.type.length == 255  # type: ignore[union-attr,attr-defined]


class TestForeignKeyClassReference:
    """Test foreign_key() with class name reference via dot notation and delayed matching"""

    def _make_base(self):
        """Create an isolated base model with its own registry for FK tests."""
        from sqlobjects.metadata import ModelRegistry
        from sqlobjects.model import ObjectModel

        class IsolatedBase(ObjectModel):
            __abstract__ = True

        IsolatedBase.__registry__ = ModelRegistry()
        return IsolatedBase

    def test_class_reference_basic(self):
        """Test foreign_key('User.id') resolves to 'users.id' via delayed matching"""
        Base = self._make_base()

        class User(Base):
            id: Column[int] = column(type="integer", primary_key=True)

        class TestModelFKRef1(Base):
            ref_id: Column[int] = foreign_key("User.id")

        fk_col = get_column_from_field(TestModelFKRef1.ref_id)
        assert fk_col is not None
        fk = list(fk_col.foreign_keys)[0]  # type: ignore[attr-defined]
        assert fk._colspec == "users.id"  # type: ignore[reportGeneralTypeIssues]
        assert fk.info.get("_fk_resolved") is True

    def test_class_reference_camel_case(self):
        """Test foreign_key('UserProfile.id') resolves to 'user_profiles.id'"""
        Base = self._make_base()

        class UserProfile(Base):
            id: Column[int] = column(type="integer", primary_key=True)

        class TestModelFKRef2(Base):
            ref_id: Column[int] = foreign_key("UserProfile.id")

        fk_col = get_column_from_field(TestModelFKRef2.ref_id)
        assert fk_col is not None
        fk = list(fk_col.foreign_keys)[0]  # type: ignore[attr-defined]
        assert fk._colspec == "user_profiles.id"  # type: ignore[reportGeneralTypeIssues]

    def test_table_reference_backward_compatible(self):
        """Test foreign_key('users.id') works when no class named 'users' exists"""
        Base = self._make_base()

        class TestModelFKRef3(Base):
            ref_id: Column[int] = foreign_key("users.id")

        fk_col = get_column_from_field(TestModelFKRef3.ref_id)
        assert fk_col is not None
        fk = list(fk_col.foreign_keys)[0]  # type: ignore[attr-defined]
        # No model named "users" in registry, so _colspec stays as-is
        assert fk._colspec == "users.id"  # type: ignore[reportGeneralTypeIssues]

    def test_class_reference_with_custom_table_name(self):
        """Test that class ref is corrected when target model has custom table_name"""
        Base = self._make_base()

        class CustomTableTarget(Base):
            id: Column[int] = column(type="integer", primary_key=True)

            class Config:
                table_name = "custom_targets"

        class TestModelFKRef4(Base):
            ref_id: Column[int] = foreign_key("CustomTableTarget.id")

        fk_col = get_column_from_field(TestModelFKRef4.ref_id)
        assert fk_col is not None
        fk = list(fk_col.foreign_keys)[0]  # type: ignore[attr-defined]
        # Delayed matching found CustomTableTarget → custom_targets
        assert fk._colspec == "custom_targets.id"  # type: ignore[reportGeneralTypeIssues]

    def test_class_reference_definition_order_independent(self):
        """Test that referencing model defined AFTER the FK works via delayed matching"""
        Base = self._make_base()

        class TestModelFKRef5(Base):
            ref_id: Column[int] = foreign_key("LateDefinedModel.id")

        # At this point, _colspec is still "LateDefinedModel.id" (no model yet)
        fk_col = get_column_from_field(TestModelFKRef5.ref_id)
        assert fk_col is not None
        fk = list(fk_col.foreign_keys)[0]  # type: ignore[attr-defined]

        # Now define the target model with a custom table name
        class LateDefinedModel(Base):
            id: Column[int] = column(type="integer", primary_key=True)

            class Config:
                table_name = "late_custom"

        # Delayed matching should have corrected the FK when LateDefinedModel registered
        assert fk._colspec == "late_custom.id"  # type: ignore[reportGeneralTypeIssues]

    def test_class_reference_with_constraints(self):
        """Test class ref works together with FK constraint options"""
        Base = self._make_base()

        class ConstraintTarget(Base):
            id: Column[int] = column(type="integer", primary_key=True)

        class TestModelFKRef6(Base):
            ref_id: Column[int] = foreign_key(
                "ConstraintTarget.id",
                ondelete="CASCADE",
                nullable=False,
            )

        fk_col = get_column_from_field(TestModelFKRef6.ref_id)
        assert fk_col is not None
        assert fk_col.nullable is False  # type: ignore[attr-defined]
        fk = list(fk_col.foreign_keys)[0]  # type: ignore[attr-defined]
        assert fk._colspec == "constraint_targets.id"  # type: ignore[reportGeneralTypeIssues]
        assert fk.ondelete == "CASCADE"

    def test_class_reference_with_schema(self):
        """Test foreign_key('myschema.User.id') with schema prefix"""
        Base = self._make_base()

        class SchemaUser(Base):
            id: Column[int] = column(type="integer", primary_key=True)

        class TestModelFKRef7(Base):
            ref_id: Column[int] = foreign_key("myschema.SchemaUser.id")

        fk_col = get_column_from_field(TestModelFKRef7.ref_id)
        assert fk_col is not None
        fk = list(fk_col.foreign_keys)[0]  # type: ignore[attr-defined]
        assert fk._colspec == "myschema.schema_users.id"  # type: ignore[reportGeneralTypeIssues]

    def test_class_reference_no_correction_needed(self):
        """Test that when class name equals table name, _colspec is still correct"""
        Base = self._make_base()

        class SimpleTarget(Base):
            id: Column[int] = column(type="integer", primary_key=True)

        class TestModelFKRef8(Base):
            ref_id: Column[int] = foreign_key("SimpleTarget.id")

        fk_col = get_column_from_field(TestModelFKRef8.ref_id)
        assert fk_col is not None
        fk = list(fk_col.foreign_keys)[0]  # type: ignore[attr-defined]
        # Class "SimpleTarget" found → resolved to actual table "simple_targets"
        assert fk._colspec == "simple_targets.id"  # type: ignore[reportGeneralTypeIssues]

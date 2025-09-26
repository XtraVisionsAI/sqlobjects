"""Integration tests for signal system

Tests signal triggering, context information, and integration with CRUD operations.
"""

import pytest

from sqlobjects.fields import Column, IntegerColumn, StringColumn, identity
from sqlobjects.signals import Operation, SignalContext

# Import TestModel from conftest to use the same registry
from tests.conftest import TestModel


class SignalTestUser(TestModel):
    """Test model with signal handlers for signal testing"""

    __test__ = False

    id: Column[int] = identity()
    username: Column[str] = StringColumn(length=50)
    email: Column[str] = StringColumn(length=100)
    age: Column[int] = IntegerColumn(nullable=True)

    # Track signal calls for testing
    signal_calls = []

    async def before_save(self, context: SignalContext):
        """Universal save signal handler"""
        self.signal_calls.append(("before_save", context.operation, context.actual_operation))

    async def after_save(self, context: SignalContext):
        """Universal save signal handler"""
        self.signal_calls.append(("after_save", context.operation, context.actual_operation))

    async def before_create(self, context: SignalContext):
        """CREATE-specific signal handler"""
        self.signal_calls.append(("before_create", context.operation, context.actual_operation))

    async def after_create(self, context: SignalContext):
        """CREATE-specific signal handler"""
        self.signal_calls.append(("after_create", context.operation, context.actual_operation))

    async def before_update(self, context: SignalContext):
        """UPDATE-specific signal handler"""
        self.signal_calls.append(("before_update", context.operation, context.actual_operation))

    async def after_update(self, context: SignalContext):
        """UPDATE-specific signal handler"""
        self.signal_calls.append(("after_update", context.operation, context.actual_operation))

    async def before_delete(self, context: SignalContext):
        """DELETE signal handler"""
        self.signal_calls.append(("before_delete", context.operation, context.actual_operation))

    async def after_delete(self, context: SignalContext):
        """DELETE signal handler"""
        self.signal_calls.append(("after_delete", context.operation, context.actual_operation))

    @classmethod
    def clear_signal_calls(cls):
        """Clear signal call history for testing"""
        cls.signal_calls.clear()


class TestInstanceSignals:
    """Test instance-level signal triggering"""

    def setup_method(self):
        """Clear signal calls before each test"""
        SignalTestUser.clear_signal_calls()

    async def test_create_operation_signals(self, session):
        """Test signals triggered during CREATE operations"""
        # Create new user (should trigger CREATE signals)
        user = SignalTestUser(username="signal_test", email="signal@example.com", age=25)
        await user.using(session).save()

        # Verify signal sequence for CREATE
        expected_signals = [
            ("before_save", Operation.SAVE, Operation.CREATE),
            ("before_create", Operation.SAVE, Operation.CREATE),
            ("after_save", Operation.SAVE, Operation.CREATE),
            ("after_create", Operation.SAVE, Operation.CREATE),
        ]

        assert SignalTestUser.signal_calls == expected_signals

    async def test_update_operation_signals(self, session):
        """Test signals triggered during UPDATE operations"""
        # Create user first
        user = SignalTestUser(username="update_test", email="update@example.com", age=30)
        await user.using(session).save()

        # Clear signals from creation
        SignalTestUser.clear_signal_calls()

        # Update user (should trigger UPDATE signals)
        user.email = "updated@example.com"
        await user.save()

        # Verify signal sequence for UPDATE
        expected_signals = [
            ("before_save", Operation.SAVE, Operation.UPDATE),
            ("before_update", Operation.SAVE, Operation.UPDATE),
            ("after_save", Operation.SAVE, Operation.UPDATE),
            ("after_update", Operation.SAVE, Operation.UPDATE),
        ]

        assert SignalTestUser.signal_calls == expected_signals

    async def test_delete_operation_signals(self, session):
        """Test signals triggered during DELETE operations"""
        # Create user first
        user = SignalTestUser(username="delete_test", email="delete@example.com", age=35)
        await user.using(session).save()

        # Clear signals from creation
        SignalTestUser.clear_signal_calls()

        # Delete user (should trigger DELETE signals)
        await user.delete()

        # Verify signal sequence for DELETE
        expected_signals = [
            ("before_delete", Operation.DELETE, Operation.DELETE),
            ("after_delete", Operation.DELETE, Operation.DELETE),
        ]

        assert SignalTestUser.signal_calls == expected_signals

    async def test_detached_instance_signals(self, session):
        """Test signals for detached instance operations"""
        # Create detached instance with primary key (should trigger UPDATE)
        detached_user = SignalTestUser.from_dict(
            {"id": 999, "username": "detached_test", "email": "detached@example.com", "age": 40}
        )

        await detached_user.using(session).save()

        # Should trigger UPDATE signals (has primary key)
        update_signals = [call for call in SignalTestUser.signal_calls if "update" in call[0]]
        assert len(update_signals) > 0


class TestSignalContext:
    """Test signal context information"""

    def setup_method(self):
        """Clear signal calls before each test"""
        SignalTestUser.clear_signal_calls()

    async def test_signal_context_information(self, session):
        """Test that signal context contains correct information"""
        context_info = []

        # Create user instance and override signal method
        user = SignalTestUser(username="context_test", email="context@example.com")

        # Override the before_save method for this instance
        async def capture_context(context: SignalContext):
            context_info.append(
                {
                    "operation": context.operation,
                    "actual_operation": context.actual_operation,
                    "session": context.session,
                    "model_class": context.model_class,
                    "instance": context.instance,
                    "is_bulk": context.is_bulk,
                    "is_single": context.is_single,
                }
            )

        # Use object.__setattr__ to avoid triggering dirty field tracking
        object.__setattr__(user, "before_save", capture_context)

        # Test CREATE operation context
        await user.using(session).save()

        assert len(context_info) == 1
        ctx = context_info[0]
        assert ctx["operation"] == Operation.SAVE
        assert ctx["actual_operation"] == Operation.CREATE
        assert ctx["session"] is not None
        assert ctx["model_class"] == SignalTestUser
        assert ctx["instance"] == user
        assert ctx["is_bulk"] is False
        assert ctx["is_single"] is True

    async def test_update_context_information(self, session):
        """Test context information for UPDATE operations"""
        context_info = []

        # Create user first
        user = SignalTestUser(username="update_context", email="update@example.com")
        await user.using(session).save()

        # Clear dirty fields to avoid issues with method override
        user._state_manager.clear_dirty_fields()

        # Override the before_save method for this instance using setattr to avoid dirty field tracking
        async def capture_context(context: SignalContext):
            context_info.append(
                {
                    "operation": context.operation,
                    "actual_operation": context.actual_operation,
                }
            )

        # Use setattr to avoid triggering dirty field tracking
        object.__setattr__(user, "before_save", capture_context)

        # Update user
        user.email = "updated@example.com"
        await user.save()

        assert len(context_info) == 1
        ctx = context_info[0]
        assert ctx["operation"] == Operation.SAVE
        assert ctx["actual_operation"] == Operation.UPDATE


class TestSignalIntegration:
    """Test signal integration with CRUD operations"""

    def setup_method(self):
        """Clear signal calls before each test"""
        SignalTestUser.clear_signal_calls()

    async def test_signal_error_handling(self, session):
        """Test signal behavior when errors occur"""
        error_raised = False

        user = SignalTestUser(username="error_test", email="error@example.com")

        # Override the before_save method to raise an error
        async def error_signal(context: SignalContext):
            nonlocal error_raised
            error_raised = True
            raise ValueError("Signal error")

        # Use object.__setattr__ to avoid triggering dirty field tracking
        object.__setattr__(user, "before_save", error_signal)

        # Signal error should prevent save operation
        with pytest.raises(ValueError, match="Signal error"):
            await user.using(session).save()

        assert error_raised is True

    async def test_signal_timing_order(self, session):
        """Test that signals are called in correct order"""
        signal_order = []

        user = SignalTestUser(username="order_test", email="order@example.com")

        # Override signal methods to track order
        async def before_save_handler(context: SignalContext):
            signal_order.append("before_save")

        async def before_create_handler(context: SignalContext):
            signal_order.append("before_create")

        async def after_save_handler(context: SignalContext):
            signal_order.append("after_save")

        async def after_create_handler(context: SignalContext):
            signal_order.append("after_create")

        # Use object.__setattr__ to avoid triggering dirty field tracking
        object.__setattr__(user, "before_save", before_save_handler)
        object.__setattr__(user, "before_create", before_create_handler)
        object.__setattr__(user, "after_save", after_save_handler)
        object.__setattr__(user, "after_create", after_create_handler)

        await user.using(session).save()

        # Verify correct signal order
        expected_order = ["before_save", "before_create", "after_save", "after_create"]
        assert signal_order == expected_order

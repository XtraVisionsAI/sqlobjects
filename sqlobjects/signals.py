import inspect
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession


__all__ = [
    "Operation",
    "SignalContext",
    "SignalMixin",
    "event",
]


class Operation(Enum):
    """Enumeration of database operation types for signal handling.

    This enum defines the types of database operations that can trigger
    signals in the SQLObjects system, allowing models to respond to
    lifecycle events.

    Values:
        SAVE: Create or update operations on individual model instances
        DELETE: Delete operations on individual instances or bulk deletions
        UPDATE: Bulk update operations affecting multiple records

    Examples:
        >>> # Used in signal context
        >>> context = SignalContext(
        ...     operation=Operation.SAVE, session=session, model_class=User, instance=user_instance
        ... )
    """

    SAVE = "save"
    DELETE = "delete"
    UPDATE = "update"


@dataclass
class SignalContext:
    """Context object containing information about a database operation for signal handlers.

    This class provides all the necessary information about a database operation
    to signal handlers, including the operation type, affected data, and session
    information.

    Attributes:
        operation: Type of database operation being performed
        session: Database session used for the operation
        model_class: Model class involved in the operation
        instance: Specific model instance (for single-instance operations)
        affected_count: Number of rows affected (for bulk operations)
        update_data: Data being updated (for update operations)

    Examples:
        >>> # Single instance save operation
        >>> context = SignalContext(operation=Operation.SAVE, session=session, model_class=User, instance=user)
        >>> # Bulk update operation
        >>> context = SignalContext(
        ...     operation=Operation.UPDATE,
        ...     session=session,
        ...     model_class=User,
        ...     affected_count=10,
        ...     update_data={"status": "active"},
        ... )
    """

    operation: Operation
    session: AsyncSession
    model_class: Any  # Target model class (for both single and batch operations)
    instance: Any | None = None  # Instance object for single instance operations
    affected_count: int | None = None  # Number of rows affected by batch operations
    update_data: dict[str, Any] | None = None  # Data for update operations

    @property
    def is_bulk(self) -> bool:
        """Check if this is a bulk operation affecting multiple records.

        Returns:
            True if this is a bulk operation, False for single-instance operations

        Examples:
            >>> # Bulk operation context
            >>> context = SignalContext(operation=Operation.UPDATE, session=session, model_class=User)
            >>> context.is_bulk  # True
            >>> # Single instance context
            >>> context = SignalContext(operation=Operation.SAVE, session=session, model_class=User, instance=user)
            >>> context.is_bulk  # False
        """
        return self.instance is None

    @property
    def is_single(self) -> bool:
        """Check if this is a single-instance operation.

        Returns:
            True if this is a single-instance operation, False for bulk operations

        Examples:
            >>> # Single instance context
            >>> context = SignalContext(operation=Operation.SAVE, session=session, model_class=User, instance=user)
            >>> context.is_single  # True
            >>> # Bulk operation context
            >>> context = SignalContext(operation=Operation.UPDATE, session=session, model_class=User)
            >>> context.is_single  # False
        """
        return self.instance is not None


class SignalMixin:
    """Mixin class that provides signal handling capabilities to model classes.

    This mixin enables models to define signal handlers that are automatically
    called before and after database operations. It supports both synchronous
    and asynchronous signal handlers.

    Signal Handler Methods:
        - before_save(context): Called before save operations
        - after_save(context): Called after save operations
        - before_delete(context): Called before delete operations
        - after_delete(context): Called after delete operations
        - before_update(context): Called before bulk update operations
        - after_update(context): Called after bulk update operations

    Examples:
        >>> class User(ObjectModel, SignalMixin):
        ...     name: Column[str] = column(type="string")
        ...
        ...     async def before_save(self, context: SignalContext) -> None:
        ...         # Called before saving the user
        ...         print(f"About to save user: {self.name}")
        ...
        ...     async def after_save(self, context: SignalContext) -> None:
        ...         # Called after saving the user
        ...         print(f"User saved: {self.name}")
    """

    async def _emit_signal(self, timing: str, context: SignalContext) -> None:
        """Emit an instance-level signal for the specified timing and operation.

        This method looks for signal handler methods on the instance and calls
        them if they exist. It supports both sync and async handlers.

        Args:
            timing: Signal timing ("before" or "after")
            context: Signal context containing operation details

        Examples:
            >>> # This is called internally by the ORM
            >>> await instance._emit_signal("before", context)
        """
        signal_name = f"{timing}_{context.operation.value}"
        handler = getattr(self, signal_name, None)

        if handler and callable(handler):
            if inspect.iscoroutinefunction(handler):
                await handler(context)
            else:
                handler(context)

    @classmethod
    async def _emit_class_signal(cls, timing: str, context: SignalContext) -> None:
        """Emit a class-level signal for the specified timing and operation.

        This method looks for class-level signal handler methods and calls
        them if they exist. Class-level signals are typically used for
        bulk operations that don't involve specific instances.

        Args:
            timing: Signal timing ("before" or "after")
            context: Signal context containing operation details

        Examples:
            >>> class User(ObjectModel, SignalMixin):
            ...     @classmethod
            ...     async def before_update(cls, context: SignalContext) -> None:
            ...         print(f"About to update {context.affected_count} users")
            >>> # This is called internally by the ORM
            >>> await User._emit_class_signal("before", context)
        """
        signal_name = f"{timing}_{context.operation.value}"
        handler = getattr(cls, signal_name, None)

        if handler and callable(handler):
            if inspect.iscoroutinefunction(handler):
                await handler(context)
            else:
                handler(context)

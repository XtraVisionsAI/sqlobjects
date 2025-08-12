import functools
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession


__all__ = [
    "Operation",
    "SignalContext",
    "SignalMixin",
    "emit_signals",
    "event",
]

F = TypeVar("F", bound=Callable[..., Any])


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


def emit_signals(operation: Operation, is_bulk: bool = False):
    """Decorator to automatically emit pre/post signals for database operations.

    Args:
        operation: The database operation type (Operation.SAVE, Operation.DELETE, Operation.UPDATE)
        is_bulk: Whether this is a bulk operation (affects signal emission strategy)

    Returns:
        Decorated function that emits signals before and after execution

    Examples:
        @emit_signals(Operation.SAVE)
        async def save(self, validate: bool = True):
            # Method implementation
            pass

        @emit_signals(Operation.UPDATE, is_bulk=True)
        async def update(self, values: dict[str, Any]) -> int:
            # Method implementation
            pass
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract self/cls and session from arguments
            self_or_cls = args[0]
            session = _extract_session(self_or_cls, kwargs)

            # Create signal context
            context = _create_signal_context(
                operation=operation, session=session, self_or_cls=self_or_cls, is_bulk=is_bulk, kwargs=kwargs
            )

            # Emit pre signal
            await _emit_pre_signal(self_or_cls, context, is_bulk)

            try:
                # Execute original method
                result = await func(*args, **kwargs)

                # Update context with result if needed
                _update_context_with_result(context, result)

                # Emit post signal
                await _emit_post_signal(self_or_cls, context, is_bulk)

                return result

            except Exception:
                raise

        return wrapper  # type: ignore

    return decorator


def _extract_session(self_or_cls, kwargs) -> Any:
    """Extract session from method arguments or instance."""
    # Try to get session from kwargs first
    if "session" in kwargs:
        return kwargs["session"]

    # Try to get session from instance/class - support both property and method
    if hasattr(self_or_cls, "_session"):
        session_attr = self_or_cls._session  # noqa
        # Handle both property and method cases
        return session_attr() if callable(session_attr) else session_attr
    elif hasattr(self_or_cls, "_get_session"):
        return self_or_cls._get_session()  # noqa

    # Fallback to default session
    from .session import SessionContextManager

    return SessionContextManager.get_session()


def _create_signal_context(operation: Operation, session, self_or_cls, is_bulk: bool, kwargs: dict) -> SignalContext:
    """Create appropriate signal context based on operation type."""
    if is_bulk:
        # Bulk operation context - support ObjectsManager and QuerySet
        if hasattr(self_or_cls, "_model"):
            model_class = self_or_cls._model  # noqa
        elif hasattr(self_or_cls, "__table__"):
            model_class = self_or_cls.__class__
        else:
            model_class = self_or_cls

        return SignalContext(
            operation=operation,
            session=session,
            model_class=model_class,
            instance=None,
            affected_count=kwargs.get("affected_count") or _extract_affected_count(kwargs),
            update_data=kwargs.get("values") or kwargs.get("update_data"),
        )
    else:
        # Single instance operation context
        instance = self_or_cls if hasattr(self_or_cls, "__table__") else None
        model_class = self_or_cls.__class__ if instance else self_or_cls
        return SignalContext(operation=operation, session=session, model_class=model_class, instance=instance)


async def _emit_pre_signal(self_or_cls, context: SignalContext, is_bulk: bool):
    """Emit pre-operation signal."""
    if is_bulk:
        # Class-level signal for bulk operations
        model_class = context.model_class
        if hasattr(model_class, "_emit_class_signal"):
            await model_class._emit_class_signal("before", context)  # noqa
    else:
        # Instance-level signal
        if hasattr(self_or_cls, "_emit_signal"):
            await self_or_cls._emit_signal("before", context)  # noqa


async def _emit_post_signal(self_or_cls, context: SignalContext, is_bulk: bool):
    """Emit post-operation signal."""
    if is_bulk:
        # Class-level signal for bulk operations
        model_class = context.model_class
        if hasattr(model_class, "_emit_class_signal"):
            await model_class._emit_class_signal("after", context)  # noqa
    else:
        # Instance-level signal
        if hasattr(self_or_cls, "_emit_signal"):
            await self_or_cls._emit_signal("after", context)  # noqa


def _extract_affected_count(kwargs: dict) -> int | None:
    """Extract affected count from method arguments."""
    # For bulk operations, try to extract count from various argument patterns
    if "mappings" in kwargs and isinstance(kwargs["mappings"], list):
        return len(kwargs["mappings"])
    elif "ids" in kwargs and isinstance(kwargs["ids"], list):
        return len(kwargs["ids"])
    elif "objects" in kwargs and isinstance(kwargs["objects"], list):
        return len(kwargs["objects"])
    return None


def _update_context_with_result(context: SignalContext, result):
    """Update signal context with method execution result."""
    if context.is_bulk and isinstance(result, int):
        # Update affected_count for bulk operations that return row count
        context.affected_count = result

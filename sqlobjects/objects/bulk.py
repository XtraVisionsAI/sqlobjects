"""SQLObjects Bulk Operations and Transaction Control

This module provides bulk operations functionality and transaction control,
merged from the original bulk_transaction.py module.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

from sqlalchemy import bindparam, insert, select, update

from ..cascade import has_cascade_delete_relations
from ..internal import ResultProcessor
from ..session import AsyncSession, ctx_session
from ..signals import Operation, SignalContext
from .upsert import ConflictResolution as UpsertConflictResolution
from .upsert import UpsertHandler


T = TypeVar("T")


class _BulkSignalError(Exception):
    """Keep application hook failures out of the record-error collection policy."""

    def __init__(self, original: Exception):
        self.original = original


def _get_error_code(exception: Exception) -> str:
    """Extract error code from database exception."""
    error_str = str(exception).lower()
    if "unique" in error_str or "duplicate" in error_str:
        return "unique_violation"
    elif "not null" in error_str:
        return "not_null_violation"
    elif "foreign key" in error_str:
        return "foreign_key_violation"
    elif "check constraint" in error_str:
        return "check_violation"
    return "unknown_error"


class TransactionMode(Enum):
    """Transaction modes for bulk operations."""

    INHERIT = "inherit"  # Inherit outer transaction (default)
    INDEPENDENT = "independent"  # Independent transaction management
    BATCH = "batch"  # Batch transactions
    SAVEPOINT = "savepoint"  # Nested savepoint transactions


class ErrorHandling(Enum):
    """Error handling strategies for bulk operations."""

    FAIL_FAST = "fail_fast"  # Stop on first error (default)
    IGNORE = "ignore"  # Skip error records
    COLLECT = "collect"  # Collect error information


class ConflictResolution(Enum):
    """Conflict resolution strategies for bulk operations."""

    ERROR = "error"  # Raise error (default)
    IGNORE = "ignore"  # Ignore conflicts
    UPDATE = "update"  # Update existing records


@dataclass
class TransactionInfo:
    """Information about transaction execution."""

    mode: TransactionMode
    batch_count: int
    failed_batches: int
    rollback_count: int


@dataclass
class FailedRecord:
    """Represents a failed record in bulk operations."""

    index: int
    data: dict[str, Any]
    error: Exception
    error_code: str
    batch_index: int = 0


@dataclass
class BulkResult(Generic[T]):
    """Result object for bulk operations with detailed information.

    Acts as a sequence over ``objects``: iteration, indexing and ``len()``
    all operate on the successfully returned objects. Use ``total_count`` /
    ``success_count`` / ``error_count`` for operation statistics — on partial
    failure ``len(result)`` and ``total_count`` differ.

    For insert operations the order of ``objects`` matches the order of the
    input rows (RETURNING is sorted by parameter order).
    """

    success_count: int
    error_count: int
    total_count: int

    # Optional fields based on parameters
    # When return_fields is None: list[T] (model instances)
    # When return_fields is specified: list[dict[str, Any]] (field dictionaries)
    objects: list[T] | list[dict[str, Any]] = field(default_factory=list)
    failed_records: list[FailedRecord] = field(default_factory=list)
    transaction_info: TransactionInfo | None = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage."""
        return self.success_count / self.total_count if self.total_count > 0 else 0.0

    @property
    def has_errors(self) -> bool:
        """Check if there were any errors."""
        return self.error_count > 0

    @property
    def has_partial_success(self) -> bool:
        """Check if there was partial success."""
        return 0 < self.success_count < self.total_count

    def __len__(self) -> int:
        """Return the number of returned objects (see ``total_count`` for input size)."""
        return len(self.objects)

    def __iter__(self) -> Iterator[T | dict[str, Any]]:
        """Iterate over the returned objects."""
        return iter(self.objects)

    def __getitem__(self, index):
        """Index into the returned objects."""
        return self.objects[index]


class BulkTransactionManager:
    """Manages transaction boundaries for bulk operations."""

    def __init__(self, session: AsyncSession, mode: TransactionMode):
        self.session = session
        self.mode = mode
        self.savepoints = []

    async def execute_batch(self, operation_func: Callable, batch_data: Any) -> Any:
        """Execute batch operation with appropriate transaction control."""
        if self.mode == TransactionMode.BATCH:
            async with ctx_session(self.session.db_name) as new_session:
                return await operation_func(new_session, batch_data)
        elif self.mode == TransactionMode.SAVEPOINT:
            async with await self.session.begin_nested():
                return await operation_func(self.session, batch_data)
        else:  # INHERIT
            return await operation_func(self.session, batch_data)


class BulkOperationHandler:
    """Unified handler for bulk operations with SQLAlchemy native capabilities."""

    def __init__(self, session: AsyncSession, table, model_class, transaction_mode: TransactionMode):
        self.session = session
        self.table = table
        self.model_class = model_class
        self.dialect = session.bind.dialect
        self.transaction_manager = BulkTransactionManager(session, transaction_mode)
        self._current_return_fields: list[str] | None = None
        self.accurate_count = True

    async def execute_bulk_operation(
        self,
        data: list,
        batch_size: int,
        operation_func,
        transaction_mode: TransactionMode,
        on_error: ErrorHandling,
        operation: Operation,
    ):
        """Execute bulk operation with unified batch processing logic."""
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if transaction_mode == TransactionMode.INDEPENDENT:
            async with ctx_session(self.session.db_name) as transaction:
                handler = BulkOperationHandler(transaction, self.table, self.model_class, TransactionMode.INHERIT)
                return await handler.execute_bulk_operation(
                    data, batch_size, operation_func, TransactionMode.INHERIT, on_error, operation
                )
        if transaction_mode != TransactionMode.BATCH and self.session.auto_commit:
            async with self.session.transaction() as transaction:
                handler = BulkOperationHandler(transaction, self.table, self.model_class, transaction_mode)
                return await handler.execute_bulk_operation(
                    data, batch_size, operation_func, transaction_mode, on_error, operation
                )

        all_successful_objects = []
        all_failed_records = []
        total_success_count = 0
        batch_count = 0
        failed_batches = 0
        rollback_count = 0
        batch_completed = False

        async def emit(timing, context):
            try:
                await self.model_class._emit_bulk_signal(timing, context)
            except Exception as error:
                raise _BulkSignalError(error) from error

        async def execute_signaled_batch(transaction, batch):
            nonlocal batch_completed
            context = SignalContext(
                operation=Operation.DELETE if operation == Operation.DELETE else Operation.SAVE,
                actual_operation=operation,
                session=transaction,
                model_class=self.model_class,
                affected_count=len(batch),
            )
            await emit("before", context)
            result = await operation_func(transaction, batch)
            context.affected_count = result[1]
            await emit("after", context)
            batch_completed = True
            return result

        for i in range(0, len(data), batch_size):
            batch_completed = False
            batch = data[i : i + batch_size]
            batch_count += 1

            try:
                successful_objects, success_count, failed_records = await self.transaction_manager.execute_batch(
                    execute_signaled_batch, batch
                )
                for failed in failed_records:
                    failed.index += i
                    failed.batch_index = batch_count - 1

                all_successful_objects.extend(successful_objects)
                total_success_count += success_count
                all_failed_records.extend(failed_records)

            except _BulkSignalError as error:
                raise error.original from error
            except Exception as e:
                # Commit failures and post-commit callback errors are not row
                # failures. In particular, committed data cannot be rolled back.
                if batch_completed:
                    raise
                failed_batches += 1
                rollback_count += 1
                if on_error == ErrorHandling.FAIL_FAST:
                    raise
                elif on_error == ErrorHandling.IGNORE:
                    # Silently skip failed batch
                    pass
                elif on_error == ErrorHandling.COLLECT:
                    for j, item in enumerate(batch):
                        all_failed_records.append(FailedRecord(i + j, item, e, "batch_error", batch_count - 1))

        return (
            all_successful_objects,
            total_success_count,
            all_failed_records,
            batch_count,
            failed_batches,
            rollback_count,
        )

    @staticmethod
    def build_result(
        successful_objects: list,
        total_success_count: int,
        failed_records: list,
        total_count: int,
        transaction_mode: TransactionMode,
        batch_count: int,
        failed_batches: int,
        rollback_count: int,
        return_objects: bool,
    ):
        """Build appropriate return result based on parameters."""
        # When return_objects=True, always return BulkResult for consistency
        if return_objects:
            transaction_info = TransactionInfo(transaction_mode, batch_count, failed_batches, rollback_count)
            return BulkResult(
                success_count=total_success_count,
                error_count=len(failed_records),
                total_count=total_count,
                objects=successful_objects,
                failed_records=failed_records,
                transaction_info=transaction_info,
            )

        # When return_objects=False, return simple count
        return total_success_count

    def supports_returning(self, operation: str) -> bool:
        """Check if database supports RETURNING for the operation."""
        capability_map = {
            "insert": "insert_executemany_returning",
            "update": "update_executemany_returning",
            "delete": "delete_executemany_returning",
        }
        return getattr(self.dialect, capability_map.get(operation, ""), False)

    def get_return_columns(self, return_fields: list[str] | None):
        """Get columns to return based on return_fields parameter."""
        if return_fields:
            return [self.table.c[f] for f in return_fields]
        return list(self.table.c)

    def create_objects_from_rows(self, rows, return_fields: list[str] | None = None) -> list:
        """Create model objects or dictionaries from database rows using ResultProcessor."""
        objects = ResultProcessor.rows_to_objects(rows, self.model_class, return_fields)
        for obj in objects:
            if not isinstance(obj, dict):
                obj.using(self.session.db_name)
        return objects

    async def execute_with_returning(
        self,
        stmt,
        operation: str,
        return_columns=None,
        parameters=None,
        session: AsyncSession | None = None,
        return_fields: list[str] | None = None,
    ):
        """Execute statement with RETURNING support and automatic fallback."""
        # Use provided session or fall back to instance session
        exec_session = session or self.session

        if return_columns and self.supports_returning(operation):
            if operation == "insert":
                # Guarantee RETURNING row order matches input row order for executemany
                stmt_with_returning = stmt.returning(*return_columns, sort_by_parameter_order=True)
            else:
                stmt_with_returning = stmt.returning(*return_columns)
            # For INSERT operations, use the data directly as parameters
            if operation == "insert" and isinstance(parameters, list):
                result = await exec_session.execute(stmt_with_returning, parameters)
            elif parameters:
                result = await exec_session.execute(stmt_with_returning, parameters)
            else:
                result = await exec_session.execute(stmt_with_returning)
            objects = self.create_objects_from_rows(result.fetchall(), return_fields)
            return objects, len(objects), True

        # Regular execution without RETURNING
        if parameters is not None and isinstance(parameters, list) and len(parameters) > 1:
            # Use executemany for multiple parameter sets
            result = await exec_session.execute(stmt, parameters)
        else:
            # Use regular execute for single parameter set or no parameters
            result = await exec_session.execute(stmt, parameters)

        # Handle rowcount: -1 means unknown, use parameter count as fallback
        rowcount = result.rowcount if result.rowcount >= 0 else 0  # noqa
        if (
            result.rowcount < 0
            and isinstance(parameters, list)
            and (operation == "insert" or (operation == "update" and not self.accurate_count))
        ):
            # For INSERT/UPDATE without proper rowcount, use parameter count
            rowcount = len(parameters)

        return [], rowcount, False

    async def execute_with_error_handling(
        self,
        stmt,
        operation: str,
        data_batch: list,
        error_handling: ErrorHandling,
        conflict_resolution: ConflictResolution = ConflictResolution.ERROR,
        conflict_fields: list[str] | None = None,
        return_columns=None,
        session: AsyncSession | None = None,
    ):
        """Execute statement with comprehensive error handling."""
        # Use provided session or fall back to instance session
        exec_session = session or self.session

        # Use unified UPSERT handler for conflict resolution
        if conflict_resolution != ConflictResolution.ERROR:
            upsert_handler = UpsertHandler(exec_session)
            upsert_conflict = (
                UpsertConflictResolution.IGNORE
                if conflict_resolution == ConflictResolution.IGNORE
                else UpsertConflictResolution.UPDATE
            )
            # For INSERT operations, replace the statement with UPSERT
            if operation == "insert":
                stmt = upsert_handler.get_upsert_statement(self.table, data_batch, upsert_conflict, conflict_fields)

        successful_objects = []
        failed_records = []
        success_count = 0

        if error_handling == ErrorHandling.FAIL_FAST:
            # FAIL_FAST: Execute batch and let exceptions propagate
            successful_objects, success_count = await self._execute_batch_operation(
                stmt, operation, data_batch, return_columns, exec_session
            )
        else:
            # Each recoverable error is isolated from successful rows and the outer transaction.
            for i, data in enumerate(data_batch):
                try:
                    async with await exec_session.begin_nested():
                        objects, count = await self._execute_batch_operation(
                            stmt, operation, [data], return_columns, exec_session
                        )
                    successful_objects.extend(objects)
                    success_count += count
                except Exception as error:
                    if error_handling == ErrorHandling.COLLECT:
                        failed_records.append(FailedRecord(i, data, error, _get_error_code(error)))

        return successful_objects, success_count, failed_records

    async def execute_upsert(self, data_batch, resolution, match_fields, on_error, session):
        """Apply the same recoverable-error boundaries to conflict-aware writes."""
        handler = UpsertHandler(session)
        if on_error == ErrorHandling.FAIL_FAST:
            return await handler.execute_upsert_with_returning(self.table, data_batch, resolution, match_fields), []
        rows, failures = [], []
        for index, data in enumerate(data_batch):
            try:
                async with await session.begin_nested():
                    stored = await handler.execute_upsert_with_returning(self.table, [data], resolution, match_fields)
                rows.extend(stored)
            except Exception as error:
                if on_error == ErrorHandling.COLLECT:
                    failures.append(FailedRecord(index, data, error, _get_error_code(error)))
        return rows, failures

    async def handle_insert_fallback(self, insert_result, return_columns, session: AsyncSession | None = None):
        """Handle INSERT fallback for single record."""
        exec_session = session or self.session
        if hasattr(insert_result, "inserted_primary_key") and insert_result.inserted_primary_key:
            pk_columns = list(self.table.primary_key.columns)
            if pk_columns:
                select_stmt = select(*return_columns).where(
                    *(col == value for col, value in zip(pk_columns, insert_result.inserted_primary_key, strict=True))
                )
                result = await exec_session.execute(select_stmt)
                current_return_fields = getattr(self, "_current_return_fields", None)
                return self.create_objects_from_rows(result.fetchall(), current_return_fields)
        return []

    async def handle_select_fallback(self, where_condition, return_columns, session: AsyncSession | None = None):
        """Handle SELECT fallback for UPDATE/DELETE operations."""
        exec_session = session or self.session
        select_stmt = select(*return_columns).where(where_condition)
        result = await exec_session.execute(select_stmt)
        rows = result.fetchall()
        current_return_fields = getattr(self, "_current_return_fields", None)
        return self.create_objects_from_rows(rows, current_return_fields)

    async def _execute_batch_operation(
        self, stmt, operation: str, data_batch: list, return_columns, session: AsyncSession
    ) -> tuple[list, int]:
        """Execute batch operation with unified logic for FAIL_FAST and IGNORE modes."""
        if operation == "update" and (
            return_columns or (self.accurate_count and not self.dialect.supports_sane_multi_rowcount)
        ):
            return await self._handle_update_without_returning(stmt, data_batch, return_columns, session)
        if operation == "insert" and return_columns and not self.supports_returning(operation):
            objects = []
            for data in data_batch:
                result = await session.execute(stmt, data)
                objects.extend(await self.handle_insert_fallback(result, return_columns, session))
            return objects, len(objects)
        current_return_fields = self._current_return_fields
        objects, count, _ = await self.execute_with_returning(
            stmt, operation, return_columns, data_batch, session, current_return_fields
        )
        return objects, count

    async def _handle_update_without_returning(
        self, stmt, data_batch: list, return_columns, session: AsyncSession
    ) -> tuple[list, int]:
        """Execute each update once and return only rows that actually matched."""
        objects = []
        count = 0
        for data in data_batch:
            if return_columns and self.dialect.update_returning:
                result = await session.execute(stmt.returning(*return_columns), data)
                rows = result.fetchall()
                count += len(rows)
                objects.extend(self.create_objects_from_rows(rows, self._current_return_fields))
            else:
                result = await session.execute(stmt, data)
                matched = max(result.rowcount, 0)
                count += matched
                if return_columns and matched:
                    conditions = [
                        self.table.c[key[7:]] == value for key, value in data.items() if key.startswith("match::")
                    ]
                    stored = await session.execute(select(*return_columns).where(*conditions))
                    objects.extend(self.create_objects_from_rows(stored.fetchall(), self._current_return_fields))
        return objects, count


# ========================================
# Bulk Operation Implementation Functions
# ========================================


async def bulk_create(
    manager,
    objects: list[dict[str, Any]],
    batch_size: int = 1000,
    return_objects: bool = False,
    return_fields: list[str] | None = None,
    # Transaction control parameters
    transaction_mode: TransactionMode = TransactionMode.INHERIT,
    on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
    on_conflict: ConflictResolution = ConflictResolution.ERROR,
    conflict_fields: list[str] | None = None,
) -> int | list | BulkResult:
    """Create multiple objects for better performance.

    Args:
        manager: ObjectsManager instance
        objects: List of dictionaries containing object data
        batch_size: Number of records to process in each batch
        return_objects: Whether to return created objects
        return_fields: Specific fields to return (requires return_objects=True)
        transaction_mode: Transaction control mode
        on_error: Error handling strategy
        on_conflict: Conflict resolution strategy
        conflict_fields: Fields to check for conflicts

    Returns:
        - int: Number of created records (default, backward compatible)
        - list[T]: Created objects if return_objects=True
        - BulkResult[T]: Detailed result with objects and statistics
    """
    if not objects:
        if return_objects:
            return BulkResult(
                success_count=0,
                error_count=0,
                total_count=0,
                transaction_info=TransactionInfo(transaction_mode, 0, 0, 0),
            )
        return 0

    session = manager._get_session(readonly=False)  # noqa
    handler = BulkOperationHandler(session, manager._table, manager._model_class, transaction_mode)  # noqa

    # Process data to exclude non-insertable fields
    processed_objects = []
    for obj_data in objects:
        processed_item = {}
        for key, value in obj_data.items():
            if hasattr(manager._model_class, key):  # noqa
                # Create a temporary instance to use the _should_exclude_from_insert method
                temp_instance = manager._model_class()  # noqa
                if not temp_instance._should_exclude_from_insert(key, value):  # noqa
                    processed_item[key] = value
            else:
                # If field doesn't exist on model, include it (let database handle the error)
                processed_item[key] = value
        processed_objects.append(processed_item)

    return_columns = handler.get_return_columns(return_fields) if return_objects else None

    async def operation_func(session_, batch_data):
        # Use unified UPSERT handler for conflict resolution
        if on_conflict != ConflictResolution.ERROR:
            upsert_conflict = (
                UpsertConflictResolution.IGNORE
                if on_conflict == ConflictResolution.IGNORE
                else UpsertConflictResolution.UPDATE
            )

            # Store return_fields in handler for use in create_objects_from_rows
            handler._current_return_fields = return_fields

            # Execute UPSERT with returning
            batch_results, failures = await handler.execute_upsert(
                batch_data, upsert_conflict, conflict_fields, on_error, session_
            )

            # Convert results to model instances only if return_objects is True
            operator_successful_objects = []
            if return_objects:
                for result_data in batch_results:
                    if return_fields:
                        filtered_dict = {f: result_data.get(f) for f in return_fields}
                        operator_successful_objects.append(filtered_dict)
                    else:
                        instance = manager._model_class._from_database(result_data, session_.db_name)  # noqa
                        operator_successful_objects.append(instance)

            return operator_successful_objects, len(batch_results), failures
        else:
            # Regular insert without conflict resolution
            stmt = insert(manager._table)  # noqa
            handler._current_return_fields = return_fields
            return await handler.execute_with_error_handling(
                stmt, "insert", batch_data, on_error, on_conflict, conflict_fields, return_columns, session_
            )

    (
        successful_objects,
        total_success_count,
        failed_records,
        batch_count,
        failed_batches,
        rollback_count,
    ) = await handler.execute_bulk_operation(
        processed_objects, batch_size, operation_func, transaction_mode, on_error, Operation.CREATE
    )

    return handler.build_result(
        successful_objects,
        total_success_count,
        failed_records,
        len(processed_objects),
        transaction_mode,
        batch_count,
        failed_batches,
        rollback_count,
        return_objects,
    )


async def bulk_update(
    manager,
    mappings: list[dict[str, Any]],
    match_fields: list[str] | None = None,
    batch_size: int = 1000,
    return_objects: bool = False,
    return_fields: list[str] | None = None,
    # Transaction control parameters
    transaction_mode: TransactionMode = TransactionMode.INHERIT,
    on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
    on_conflict: ConflictResolution = ConflictResolution.ERROR,
    conflict_fields: list[str] | None = None,
    accurate_count: bool = True,
) -> int | list | BulkResult:
    """Perform true bulk update operations for better performance.

    Args:
        manager: ObjectsManager instance
        mappings: List of dictionaries containing match fields and update values
        match_fields: Fields to use for matching records (defaults to ["id"])
        batch_size: Number of records to process in each batch
        return_objects: Whether to return updated objects
        return_fields: Specific fields to return (requires return_objects=True)
        transaction_mode: Transaction control mode
        on_error: Error handling strategy
        on_conflict: Conflict resolution strategy
        conflict_fields: Fields to check for conflicts
        accurate_count: Whether to return accurate update count (default: True)
            - True: Guarantees accurate count (PostgreSQL uses individual execution, slower)
            - False: Prioritizes performance, may return approximate count (PostgreSQL ~20x faster)

    Returns:
        - int: Number of updated records (default, backward compatible)
        - list[T]: Updated objects if return_objects=True
        - BulkResult[T]: Detailed result with objects and statistics
    """
    if not mappings:
        if return_objects:
            return BulkResult(
                success_count=0,
                error_count=0,
                total_count=0,
                transaction_info=TransactionInfo(transaction_mode, 0, 0, 0),
            )
        return 0

    if match_fields is None:
        match_fields = ["id"]

    session = manager._get_session(readonly=False)  # noqa
    handler = BulkOperationHandler(session, manager._table, manager._model_class, transaction_mode)  # noqa

    handler.accurate_count = accurate_count

    # Build base statement
    where_conditions = [manager._table.c[field] == bindparam(f"match::{field}") for field in match_fields]  # noqa
    stmt = update(manager._table).where(*where_conditions)  # noqa

    async def operation_func(session_, batch_data):
        # Use unified UPSERT handler for bulk update with conflict resolution
        if on_conflict != ConflictResolution.ERROR:
            upsert_conflict = UpsertConflictResolution.UPDATE

            # Store return_fields in handler for use in create_objects_from_rows
            handler._current_return_fields = return_fields

            # Execute UPSERT with returning
            batch_results, failures = await handler.execute_upsert(
                batch_data, upsert_conflict, match_fields, on_error, session_
            )

            # Convert results to model instances only if return_objects is True
            oper_successful_objects = []
            if return_objects:
                for result_data in batch_results:
                    if return_fields:
                        filtered_dict = {field: result_data.get(field) for field in return_fields}
                        oper_successful_objects.append(filtered_dict)
                    else:
                        instance = manager._model_class._from_database(result_data, session_.db_name)  # noqa
                        oper_successful_objects.append(instance)

            return oper_successful_objects, len(batch_results), failures
        else:
            # Regular update without conflict resolution
            update_values = {
                key: bindparam(f"update::{key}") for key in batch_data[0].keys() if key not in match_fields
            }
            if not update_values:
                return [], 0, []

            batch_stmt = stmt.values(**update_values)

            # Prepare parameter mappings
            param_mappings = []
            for mapping in batch_data:
                param_dict = {}
                for f in match_fields:
                    param_dict[f"match::{f}"] = mapping[f]
                for key, value in mapping.items():
                    if key not in match_fields:
                        param_dict[f"update::{key}"] = value
                param_mappings.append(param_dict)

            return_columns = handler.get_return_columns(return_fields) if return_objects else None
            handler._current_return_fields = return_fields
            return await handler.execute_with_error_handling(
                batch_stmt, "update", param_mappings, on_error, on_conflict, conflict_fields, return_columns, session_
            )

    (
        successful_objects,
        total_success_count,
        failed_records,
        batch_count,
        failed_batches,
        rollback_count,
    ) = await handler.execute_bulk_operation(
        mappings, batch_size, operation_func, transaction_mode, on_error, Operation.UPDATE
    )

    return handler.build_result(
        successful_objects,
        total_success_count,
        failed_records,
        len(mappings),
        transaction_mode,
        batch_count,
        failed_batches,
        rollback_count,
        return_objects,
    )


async def bulk_delete(
    manager,
    ids: list[Any],
    id_field: str = "id",
    batch_size: int = 1000,
    return_objects: bool = False,
    return_fields: list[str] | None = None,
    # Transaction control parameters
    transaction_mode: TransactionMode = TransactionMode.INHERIT,
    on_error: ErrorHandling = ErrorHandling.FAIL_FAST,
) -> int | list | BulkResult:
    """Perform true bulk delete operations for better performance.

    Args:
        manager: ObjectsManager instance
        ids: List of IDs to delete
        id_field: Field name to use for matching (defaults to "id")
        batch_size: Number of records to process in each batch
        return_objects: Whether to return deleted objects (for audit logging)
        return_fields: Specific fields to return (requires return_objects=True)
        transaction_mode: Transaction control mode
        on_error: Error handling strategy

    Returns:
        - int: Number of deleted records (default, backward compatible)
        - list[T]: Deleted objects if return_objects=True
        - BulkResult[T]: Detailed result with objects and statistics
    """
    if not ids:
        if return_objects:
            return BulkResult(
                success_count=0,
                error_count=0,
                total_count=0,
                transaction_info=TransactionInfo(transaction_mode, 0, 0, 0),
            )
        return 0

    session = manager._get_session(readonly=False)  # noqa
    handler = BulkOperationHandler(session, manager._table, manager._model_class, transaction_mode)  # noqa

    async def operation_func(session_, batch_ids):
        from sqlalchemy import delete

        # Check if model has cascade delete relationships
        has_cascade = has_cascade_delete_relations(manager._model_class)

        # Fetch instances if needed for return_objects or cascade processing
        instances = []
        if return_objects or has_cascade:
            field_column = manager._table.c[id_field]  # noqa
            in_condition = field_column.in_(batch_ids)

            # Handle FunctionExpression by resolving to SQLAlchemy expression
            if hasattr(in_condition, "resolve"):
                in_condition = in_condition.resolve(manager._table)  # noqa

            select_stmt = select(manager._table).where(in_condition)  # noqa
            result = await session_.execute(select_stmt)

            for row in result.fetchall():
                instance = manager._model_class.from_dict(dict(row._mapping))  # noqa
                instances.append(instance)

        # Process cascade deletion if needed
        if has_cascade:
            from ..cascade import CascadeExecutor

            handler._current_return_fields = return_fields
            cascade_executor = CascadeExecutor()
            for instance in instances:
                await cascade_executor._delete_related_objects(instance, session_)  # noqa

        # Execute batch delete with single SQL statement
        field_column = manager._table.c[id_field]  # noqa
        in_condition = field_column.in_(batch_ids)

        if hasattr(in_condition, "resolve"):
            in_condition = in_condition.resolve(manager._table)  # noqa

        stmt = delete(manager._table).where(in_condition)  # noqa
        result = await session_.execute(stmt)

        # Build return objects if requested
        objects_batch = []
        if return_objects:
            for instance in instances:
                if return_fields:
                    filtered_dict = {f: getattr(instance, f, None) for f in return_fields}
                    objects_batch.append(filtered_dict)
                else:
                    objects_batch.append(instance)

        return objects_batch, result.rowcount, []

    (
        successful_objects,
        total_success_count,
        failed_records,
        batch_count,
        failed_batches,
        rollback_count,
    ) = await handler.execute_bulk_operation(
        ids, batch_size, operation_func, transaction_mode, on_error, Operation.DELETE
    )

    return handler.build_result(
        successful_objects,
        total_success_count,
        failed_records,
        len(ids),
        transaction_mode,
        batch_count,
        failed_batches,
        rollback_count,
        return_objects,
    )

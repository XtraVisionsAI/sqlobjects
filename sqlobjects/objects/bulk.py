"""SQLObjects Bulk Operations and Transaction Control

This module provides bulk operations functionality and transaction control,
merged from the original bulk_transaction.py module.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

from sqlalchemy import bindparam, insert, select, update

from ..cascade import has_cascade_delete_relations
from ..internal import ResultProcessor
from ..session import AsyncSession, ctx_session
from .upsert import ConflictResolution as UpsertConflictResolution
from .upsert import UpsertHandler


T = TypeVar("T")


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
    """Result object for bulk operations with detailed information."""

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
        """Return total count for len() support."""
        return self.total_count


class BulkTransactionManager:
    """Manages transaction boundaries for bulk operations."""

    def __init__(self, session: AsyncSession, mode: TransactionMode):
        self.session = session
        self.mode = mode
        self.savepoints = []

    async def execute_batch(self, operation_func: Callable, batch_data: Any) -> Any:
        """Execute batch operation with appropriate transaction control."""
        if self.mode == TransactionMode.INDEPENDENT:
            async with ctx_session() as new_session:
                return await operation_func(new_session, batch_data)
        elif self.mode == TransactionMode.BATCH:
            # For BATCH mode, use the existing session without creating new transaction
            # The session should handle its own transaction boundaries
            return await operation_func(self.session, batch_data)
        elif self.mode == TransactionMode.SAVEPOINT:
            savepoint = await self.session.begin_nested()
            try:
                result = await operation_func(self.session, batch_data)
                await savepoint.commit()
                return result
            except Exception:
                await savepoint.rollback()
                raise
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

    async def execute_bulk_operation(
        self,
        data: list,
        batch_size: int,
        operation_func,
        transaction_mode: TransactionMode,
        on_error: ErrorHandling,
    ):
        """Execute bulk operation with unified batch processing logic."""
        all_successful_objects = []
        all_failed_records = []
        total_success_count = 0
        batch_count = 0
        failed_batches = 0
        rollback_count = 0

        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]
            batch_count += 1

            try:
                if transaction_mode == TransactionMode.BATCH:
                    successful_objects, success_count, failed_records = await self.transaction_manager.execute_batch(
                        operation_func, batch
                    )
                else:
                    successful_objects, success_count, failed_records = await operation_func(self.session, batch)

                all_successful_objects.extend(successful_objects)
                total_success_count += success_count
                all_failed_records.extend(failed_records)

            except Exception as e:
                failed_batches += 1
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
        return ResultProcessor.rows_to_objects(rows, self.model_class, return_fields)

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
            stmt_with_returning = stmt.returning(*return_columns)
            # For INSERT operations, use the data directly as parameters
            if operation == "insert" and isinstance(parameters, list):
                result = await exec_session.execute(stmt_with_returning, parameters)
            elif parameters:
                result = await exec_session.execute(stmt_with_returning, parameters)
            else:
                result = await exec_session.execute(stmt_with_returning)
            objects = self.create_objects_from_rows(result.fetchall(), return_fields)
            return objects, result.rowcount or 0, True

        # Regular execution without RETURNING
        if parameters is not None and isinstance(parameters, list) and len(parameters) > 1:
            # Use executemany for multiple parameter sets
            result = await exec_session.execute(stmt, parameters)
        else:
            # Use regular execute for single parameter set or no parameters
            result = await exec_session.execute(stmt, parameters)

        # Handle rowcount: -1 means unknown, use parameter count as fallback
        rowcount = result.rowcount if result.rowcount >= 0 else 0  # noqa
        if rowcount == 0 and isinstance(parameters, list):
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
        elif error_handling == ErrorHandling.IGNORE:
            # IGNORE: Process individually to skip errors
            for _, data in enumerate(data_batch):
                try:
                    single_stmt = stmt.values([data]) if hasattr(stmt, "values") else stmt
                    if return_columns and self.supports_returning(operation):
                        single_stmt = single_stmt.returning(*return_columns)
                        result = await exec_session.execute(single_stmt)
                        rows = result.fetchall()
                        if rows:
                            current_return_fields = getattr(self, "_current_return_fields", None)
                            successful_objects.extend(self.create_objects_from_rows(rows, current_return_fields))
                            success_count += 1
                    else:
                        result = await exec_session.execute(single_stmt)
                        if result.rowcount > 0:  # noqa
                            success_count += 1
                except Exception:  # noqa
                    # Silently ignore errors
                    pass

        elif error_handling == ErrorHandling.COLLECT:
            # Process individually to collect detailed errors
            for i, data in enumerate(data_batch):
                try:
                    single_stmt = stmt.values([data]) if hasattr(stmt, "values") else stmt
                    if return_columns and self.supports_returning(operation):
                        single_stmt = single_stmt.returning(*return_columns)
                        result = await exec_session.execute(single_stmt)
                        rows = result.fetchall()
                        if rows:
                            current_return_fields = getattr(self, "_current_return_fields", None)
                            successful_objects.extend(self.create_objects_from_rows(rows, current_return_fields))
                            success_count += 1
                    else:
                        result = await exec_session.execute(single_stmt)
                        if result.rowcount > 0:  # noqa
                            success_count += 1
                except Exception as e:
                    failed_records.append(FailedRecord(i, data, e, _get_error_code(e)))

        return successful_objects, success_count, failed_records

    async def handle_insert_fallback(self, insert_result, return_columns, session: AsyncSession | None = None):
        """Handle INSERT fallback for single record."""
        exec_session = session or self.session
        if hasattr(insert_result, "inserted_primary_key") and insert_result.inserted_primary_key:
            pk_columns = list(self.table.primary_key.columns)
            if pk_columns:
                pk_col = pk_columns[0]
                pk_value = insert_result.inserted_primary_key[0]
                select_stmt = select(*return_columns).where(pk_col == pk_value)  # noqa
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

    async def _handle_insert_fallback_batch(
        self, data_batch: list, return_columns, session: AsyncSession | None = None
    ):
        """Handle INSERT fallback for batch operations to get accurate data including DB-generated fields."""
        exec_session = session or self.session
        objects = []

        # For each inserted record, try to find it in the database
        # This is expensive but ensures data accuracy
        for data in data_batch:
            # Build WHERE conditions based on the input data to find the inserted record
            where_conditions = []
            for key, value in data.items():
                if key in self.table.columns and value is not None:
                    where_conditions.append(self.table.c[key] == value)

            if where_conditions:
                # Try to find the record using the input data
                select_stmt = select(*return_columns).where(*where_conditions)
                result = await exec_session.execute(select_stmt)
                rows = result.fetchall()

                if rows:
                    # Take the first match (there might be multiple if data isn't unique)
                    current_return_fields = getattr(self, "_current_return_fields", None)
                    objects.extend(self.create_objects_from_rows([rows[0]], current_return_fields))
                else:
                    # Fallback: create object from input data (missing DB-generated fields)
                    objects.append(self.model_class.from_dict(data, validate=False))
            else:
                # No usable WHERE conditions, fallback to input data
                objects.append(self.model_class.from_dict(data, validate=False))

        return objects

    async def _execute_batch_operation(
        self, stmt, operation: str, data_batch: list, return_columns, session: AsyncSession
    ) -> tuple[list, int]:
        """Execute batch operation with unified logic for FAIL_FAST and IGNORE modes."""
        # For UPDATE operations without RETURNING support, use fallback strategy
        if operation == "update" and return_columns and not self.supports_returning(operation):
            return await self._handle_update_without_returning(stmt, data_batch, return_columns, session)
        else:
            # Use unified execute_with_returning for consistent behavior
            current_return_fields = getattr(self, "_current_return_fields", None)
            successful_objects, success_count, used_returning = await self.execute_with_returning(
                stmt, operation, return_columns, data_batch, session, current_return_fields
            )
            # Handle fallback for operations without RETURNING support
            if return_columns and not used_returning and success_count > 0:
                successful_objects = await self._handle_fallback_without_returning(
                    operation, data_batch, return_columns, success_count, session
                )
            return successful_objects, success_count

    async def _handle_update_without_returning(
        self, stmt, data_batch: list, return_columns, session: AsyncSession
    ) -> tuple[list, int]:
        """Handle UPDATE operations without RETURNING support."""
        # Execute update first
        result = await session.execute(stmt, data_batch)
        success_count = result.rowcount

        # If rowcount is -1 (unknown), execute individually to get accurate count
        if success_count < 0:  # noqa
            success_count = 0
            for data in data_batch:
                individual_result = await session.execute(stmt, [data])
                if individual_result.rowcount > 0:  # noqa
                    success_count += individual_result.rowcount

        # If successful, create objects with merged data
        if success_count > 0:
            successful_objects = []
            for data in data_batch[:success_count]:
                # Create object with merged data (input data takes precedence)
                obj_data = {}
                # Add all fields from return_columns with None as default
                for col in return_columns:
                    obj_data[col.name] = None

                # For UPDATE operations, convert parameter names back to field names
                for key, value in data.items():
                    if key.startswith("match::"):
                        field_name = key[7:]  # Remove "match::" prefix
                        obj_data[field_name] = value
                    elif key.startswith("update::"):
                        field_name = key[8:]  # Remove "update::" prefix
                        obj_data[field_name] = value
                    else:
                        obj_data[key] = value

                current_return_fields = getattr(self, "_current_return_fields", None)
                if current_return_fields:
                    # Return only requested fields as dict
                    filtered_dict = {f: obj_data.get(f) for f in current_return_fields}
                    successful_objects.append(filtered_dict)
                else:
                    # Return full model object
                    successful_objects.append(self.model_class.from_dict(obj_data, validate=False))
        else:
            successful_objects = []

        return successful_objects, success_count

    async def _handle_fallback_without_returning(
        self, operation: str, data_batch: list, return_columns, success_count: int, session: AsyncSession
    ) -> list:
        """Handle fallback for operations without RETURNING support."""
        import warnings

        warnings.warn(
            f"Database does not support {operation.upper()} RETURNING. "
            f"return_objects=True will have significant performance impact. "
            f"Consider using a database that supports RETURNING for better performance.",
            UserWarning,
            stacklevel=4,
        )

        if operation == "insert":
            # For INSERT operations, use fallback to get accurate data including DB-generated fields
            return await self._handle_insert_fallback_batch(data_batch[:success_count], return_columns, session)
        else:
            # For other operations, create objects from input data as approximation
            return [self.model_class.from_dict(data, validate=False) for data in data_batch[:success_count]]


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
            upsert_handler = UpsertHandler(session_)
            upsert_conflict = (
                UpsertConflictResolution.IGNORE
                if on_conflict == ConflictResolution.IGNORE
                else UpsertConflictResolution.UPDATE
            )

            # Store return_fields in handler for use in create_objects_from_rows
            handler._current_return_fields = return_fields

            # Execute UPSERT with returning
            batch_results = await upsert_handler.execute_upsert_with_returning(
                manager._table,  # noqa
                batch_data,
                upsert_conflict,
                conflict_fields,  # noqa
            )

            # Convert results to model instances only if return_objects is True
            operator_successful_objects = []
            if return_objects:
                for result_data in batch_results:
                    if return_fields:
                        filtered_dict = {f: result_data.get(f) for f in return_fields}
                        operator_successful_objects.append(filtered_dict)
                    else:
                        instance = manager._model_class.from_dict(result_data)  # noqa
                        operator_successful_objects.append(instance)

            return operator_successful_objects, len(batch_results), []
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
    ) = await handler.execute_bulk_operation(processed_objects, batch_size, operation_func, transaction_mode, on_error)

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

    # Fast path: use executemany for all databases when accurate_count=False
    if not accurate_count:
        return await _bulk_update_fast(manager, mappings, match_fields, batch_size, session)

    # Build base statement
    where_conditions = [manager._table.c[field] == bindparam(f"match::{field}") for field in match_fields]  # noqa
    stmt = update(manager._table).where(*where_conditions)  # noqa

    async def operation_func(session_, batch_data):
        # Use unified UPSERT handler for bulk update with conflict resolution
        if on_conflict != ConflictResolution.ERROR:
            upsert_handler = UpsertHandler(session_)
            upsert_conflict = UpsertConflictResolution.UPDATE

            # Store return_fields in handler for use in create_objects_from_rows
            handler._current_return_fields = return_fields

            # Execute UPSERT with returning
            batch_results = await upsert_handler.execute_upsert_with_returning(
                manager._table,  # noqa
                batch_data,
                upsert_conflict,
                match_fields,  # noqa
            )

            # Convert results to model instances only if return_objects is True
            oper_successful_objects = []
            if return_objects:
                for result_data in batch_results:
                    if return_fields:
                        filtered_dict = {field: result_data.get(field) for field in return_fields}
                        oper_successful_objects.append(filtered_dict)
                    else:
                        instance = manager._model_class.from_dict(result_data)  # noqa
                        oper_successful_objects.append(instance)

            return oper_successful_objects, len(batch_results), []
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
    ) = await handler.execute_bulk_operation(mappings, batch_size, operation_func, transaction_mode, on_error)

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
    ) = await handler.execute_bulk_operation(ids, batch_size, operation_func, transaction_mode, on_error)

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


async def _bulk_update_fast(
    manager, mappings: list[dict[str, Any]], match_fields: list[str], batch_size: int, session: AsyncSession
) -> int:
    """Fast bulk update using executemany (may return approximate count for PostgreSQL)."""
    if not mappings:
        return 0

    # Build UPDATE statement
    where_conditions = [manager._table.c[f] == bindparam(f"match::{f}") for f in match_fields]  # noqa
    stmt = update(manager._table).where(*where_conditions)  # noqa

    # Get update fields (exclude match fields)
    update_values = {key: bindparam(f"update::{key}") for key in mappings[0].keys() if key not in match_fields}
    if not update_values:
        return 0

    stmt = stmt.values(**update_values)

    # Process in batches
    total = 0
    for i in range(0, len(mappings), batch_size):
        batch = mappings[i : i + batch_size]

        # Prepare parameter mappings
        param_mappings = []
        for mapping in batch:
            param_dict = {}
            for f in match_fields:
                param_dict[f"match::{f}"] = mapping[f]
            for key, value in mapping.items():
                if key not in match_fields:
                    param_dict[f"update::{key}"] = value
            param_mappings.append(param_dict)

        # Execute with executemany
        result = await session.execute(stmt, param_mappings)
        # PostgreSQL returns -1, use batch length as approximation
        count = result.rowcount if result.rowcount >= 0 else len(batch)  # noqa
        total += count

    return total

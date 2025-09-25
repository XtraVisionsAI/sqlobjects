"""SQLObjects Bulk Operations and Transaction Control

This module provides bulk operations functionality and transaction control,
merged from the original bulk_transaction.py module.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

from sqlalchemy import bindparam, delete, insert, select, update

from ..session import AsyncSession, ctx_session


T = TypeVar("T")


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


class DatabaseNativeHandler:
    """Handles database-specific conflict resolution."""

    def __init__(self, dialect_name: str):
        self.dialect_name = dialect_name

    def get_conflict_clause(
        self, conflict_resolution: ConflictResolution, conflict_fields: list[str] | None = None
    ) -> str | None:
        """Get database-specific conflict resolution clause."""
        if self.dialect_name == "postgresql":
            if conflict_resolution == ConflictResolution.IGNORE:
                fields = f"({', '.join(conflict_fields)})" if conflict_fields else ""
                return f"ON CONFLICT {fields} DO NOTHING"
            elif conflict_resolution == ConflictResolution.UPDATE and conflict_fields:
                updates = ", ".join(f"{field} = EXCLUDED.{field}" for field in conflict_fields)
                return f"ON CONFLICT ({', '.join(conflict_fields)}) DO UPDATE SET {updates}"
        elif self.dialect_name == "mysql":
            if conflict_resolution == ConflictResolution.IGNORE:
                return "INSERT IGNORE"
            elif conflict_resolution == ConflictResolution.UPDATE:
                return "INSERT ... ON DUPLICATE KEY UPDATE"
        elif self.dialect_name == "sqlite":
            if conflict_resolution == ConflictResolution.IGNORE:
                return "INSERT OR IGNORE"
            elif conflict_resolution == ConflictResolution.UPDATE:
                return "INSERT OR REPLACE"
        return None

    def modify_statement(self, stmt, conflict_resolution: ConflictResolution, conflict_fields: list[str] | None = None):
        """Modify SQL statement for conflict resolution."""
        if conflict_resolution == ConflictResolution.IGNORE:
            if self.dialect_name == "postgresql" and hasattr(stmt, "on_conflict_do_nothing"):
                if conflict_fields:
                    return stmt.on_conflict_do_nothing(index_elements=conflict_fields)
                return stmt.on_conflict_do_nothing()
            elif self.dialect_name == "sqlite":
                # For SQLite, use INSERT OR IGNORE
                return stmt.prefix_with("OR IGNORE")
            elif self.dialect_name == "mysql":
                # For MySQL, use INSERT IGNORE
                return stmt.prefix_with("IGNORE")
        elif conflict_resolution == ConflictResolution.UPDATE:
            if self.dialect_name == "sqlite":
                # For SQLite, use INSERT OR REPLACE
                return stmt.prefix_with("OR REPLACE")
        return stmt

    @staticmethod
    def get_error_code(exception: Exception) -> str:
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


class BulkOperationHandler:
    """Unified handler for bulk operations with SQLAlchemy native capabilities."""

    def __init__(self, session: AsyncSession, table, model_class, transaction_mode: TransactionMode):
        self.session = session
        self.table = table
        self.model_class = model_class
        self.dialect = session.bind.dialect
        self.native_handler = DatabaseNativeHandler(self.dialect.name)
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
            return [self.table.c[field] for field in return_fields]
        return list(self.table.c)

    def create_objects_from_rows(self, rows, return_fields: list[str] | None = None) -> list:
        """Create model objects or dictionaries from database rows."""
        objects = []
        for row in rows:
            row_dict = dict(row._mapping)  # noqa
            if return_fields:
                # When return_fields is specified, return dict with only requested fields
                filtered_dict = {field: row_dict.get(field) for field in return_fields}
                objects.append(filtered_dict)
            else:
                # When return_fields is None, return full model objects
                obj = self.model_class.from_dict(row_dict, validate=False)
                objects.append(obj)
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
        return [], result.rowcount or 0, False

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

        # Modify statement for conflict resolution
        if conflict_resolution != ConflictResolution.ERROR:
            stmt = self.native_handler.modify_statement(stmt, conflict_resolution, conflict_fields)

        successful_objects = []
        failed_records = []
        success_count = 0

        if error_handling in (ErrorHandling.FAIL_FAST, ErrorHandling.IGNORE):
            # Unified handling for FAIL_FAST and IGNORE modes
            successful_objects, success_count = await self._execute_batch_operation(
                stmt, operation, data_batch, return_columns, exec_session
            )

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
                    failed_records.append(FailedRecord(i, data, e, self.native_handler.get_error_code(e)))

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
        success_count = result.rowcount or 0

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
                    filtered_dict = {field: obj_data.get(field) for field in current_return_fields}
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

    stmt = insert(manager._table)  # noqa
    return_columns = handler.get_return_columns(return_fields) if return_objects else None

    async def operation_func(session_, batch_data):
        # Store return_fields in handler for use in create_objects_from_rows
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
    ) = await handler.execute_bulk_operation(objects, batch_size, operation_func, transaction_mode, on_error)

    return handler.build_result(
        successful_objects,
        total_success_count,
        failed_records,
        len(objects),
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

    # Build base statement with conflict resolution
    where_conditions = [manager._table.c[field] == bindparam(f"match::{field}") for field in match_fields]  # noqa
    stmt = update(manager._table).where(*where_conditions)  # noqa

    # Apply conflict resolution if specified
    if on_conflict != ConflictResolution.ERROR:
        stmt = handler.native_handler.modify_statement(stmt, on_conflict, conflict_fields)

    async def operation_func(session_, batch_data):
        # Add update values
        update_values = {key: bindparam(f"update::{key}") for key in batch_data[0].keys() if key not in match_fields}
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
        # Store return_fields in handler for use in create_objects_from_rows
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
        field_column = manager._table.c[id_field]  # noqa
        in_condition = field_column.in_(batch_ids)

        # Handle FunctionExpression by resolving to SQLAlchemy expression
        if hasattr(in_condition, "resolve"):
            in_condition = in_condition.resolve(manager._table)  # noqa

        stmt = delete(manager._table).where(in_condition)  # noqa
        return_columns = handler.get_return_columns(return_fields) if return_objects else None

        if return_objects and not handler.supports_returning("delete"):
            # Fallback: select before delete
            # Store return_fields in handler for use in create_objects_from_rows
            handler._current_return_fields = return_fields
            objects_batch = await handler.handle_select_fallback(in_condition, return_columns, session_)
            result = await session_.execute(stmt)
            return objects_batch, result.rowcount or 0, []
        else:
            # Store return_fields in handler for use in create_objects_from_rows
            handler._current_return_fields = return_fields
            objects, rowcount, _ = await handler.execute_with_returning(
                stmt, "delete", return_columns, None, session_, return_fields
            )
            return objects, rowcount, []

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

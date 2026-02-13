"""Database dialect handlers for database-specific SQL generation."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa


if TYPE_CHECKING:
    from ..session import AsyncSession


__all__ = ["BaseDialect", "PostgreSQLDialect", "MySQLDialect", "SQLiteDialect", "DialectHandler"]


class BaseDialect(ABC):
    """Base class for database dialect handlers."""

    def __init__(self, dialect_name: str):
        self.name = dialect_name

    @abstractmethod
    def get_upsert_statement(
        self,
        table: sa.Table,
        data: dict[str, Any],
        conflict_fields: list[str],
        update_fields: list[str],
    ) -> sa.sql.Insert:
        """Generate UPSERT statement for the database."""
        pass

    @abstractmethod
    def get_date_trunc_expression(self, field: Any, precision: str) -> Any:
        """Generate date truncation expression."""
        pass

    @abstractmethod
    def get_datetime_trunc_expression(self, field: Any, precision: str) -> Any:
        """Generate datetime truncation expression."""
        pass

    @abstractmethod
    def build_explain_query(self, sql: str, analyze: bool, verbose: bool) -> str:
        """Build EXPLAIN query for the database."""
        pass

    @abstractmethod
    def parse_explain_result(self, rows: list) -> str:
        """Parse EXPLAIN result for the database."""
        pass

    def supports_returning(self) -> bool:
        """Check if database supports RETURNING clause."""
        return False

    def get_batch_size_recommendation(self, operation: str) -> int:
        """Get recommended batch size for bulk operations."""
        return 1000


class PostgreSQLDialect(BaseDialect):
    """PostgreSQL dialect handler."""

    def get_upsert_statement(
        self,
        table: sa.Table,
        data: dict[str, Any],
        conflict_fields: list[str],
        update_fields: list[str],
    ) -> sa.sql.Insert:
        """Generate PostgreSQL UPSERT using ON CONFLICT."""
        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(table).values(data)
        if update_fields:
            # ON CONFLICT DO UPDATE
            update_dict = {field: stmt.excluded[field] for field in update_fields}
            return stmt.on_conflict_do_update(index_elements=conflict_fields, set_=update_dict)
        # ON CONFLICT DO NOTHING
        return stmt.on_conflict_do_nothing(index_elements=conflict_fields if conflict_fields else None)

    def get_date_trunc_expression(self, field: Any, precision: str) -> Any:
        """Generate PostgreSQL date_trunc expression."""
        from sqlalchemy import func

        return func.date_trunc(precision, field)

    def get_datetime_trunc_expression(self, field: Any, precision: str) -> Any:
        """Generate PostgreSQL date_trunc expression for datetime."""
        from sqlalchemy import func

        return func.date_trunc(precision, field)

    def supports_returning(self) -> bool:
        """PostgreSQL supports RETURNING for all operations."""
        return True

    def build_explain_query(self, sql: str, analyze: bool, verbose: bool) -> str:
        """Build PostgreSQL EXPLAIN query."""
        options = []
        if analyze:
            options.append("ANALYZE TRUE")
        if verbose:
            options.append("VERBOSE TRUE")

        if options:
            return f"EXPLAIN ({', '.join(options)}) {sql}"
        return f"EXPLAIN {sql}"

    def parse_explain_result(self, rows: list) -> str:
        """Parse PostgreSQL EXPLAIN result."""
        return "\n".join(str(row[0]) for row in rows)


class MySQLDialect(BaseDialect):
    """MySQL dialect handler."""

    def get_upsert_statement(
        self,
        table: sa.Table,
        data: dict[str, Any],
        conflict_fields: list[str],
        update_fields: list[str],
    ) -> sa.sql.Insert:
        """Generate MySQL UPSERT using INSERT IGNORE or ON DUPLICATE KEY UPDATE."""
        from sqlalchemy.dialects.mysql import insert

        stmt = insert(table).values(data)
        if update_fields:
            # ON DUPLICATE KEY UPDATE
            update_dict = {field: stmt.inserted[field] for field in update_fields}
            return stmt.on_duplicate_key_update(**update_dict)
        # INSERT IGNORE
        return stmt.prefix_with("IGNORE")

    def get_date_trunc_expression(self, field: Any, precision: str) -> Any:
        """Generate MySQL date_format expression."""
        from sqlalchemy import func

        format_map = {"year": "%Y", "month": "%Y-%m", "day": "%Y-%m-%d"}
        return func.date_format(field, format_map.get(precision, "%Y-%m-%d"))

    def get_datetime_trunc_expression(self, field: Any, precision: str) -> Any:
        """Generate MySQL date_format expression for datetime."""
        return self.get_date_trunc_expression(field, precision)

    def build_explain_query(self, sql: str, analyze: bool, verbose: bool) -> str:
        """Build MySQL EXPLAIN query."""
        if analyze:
            return f"EXPLAIN ANALYZE {sql}"
        return f"EXPLAIN {sql}"

    def parse_explain_result(self, rows: list) -> str:
        """Parse MySQL EXPLAIN result."""
        return "\n".join(str(row[0]) for row in rows)


class SQLiteDialect(BaseDialect):
    """SQLite dialect handler."""

    def get_upsert_statement(
        self,
        table: sa.Table,
        data: dict[str, Any],
        conflict_fields: list[str],
        update_fields: list[str],
    ) -> sa.sql.Insert:
        """Generate SQLite UPSERT using INSERT OR IGNORE or ON CONFLICT."""
        from sqlalchemy.dialects.sqlite import insert

        stmt = insert(table).values(data)
        if update_fields and conflict_fields:
            # ON CONFLICT DO UPDATE
            update_dict = {field: stmt.excluded[field] for field in update_fields}
            return stmt.on_conflict_do_update(index_elements=conflict_fields, set_=update_dict)
        # INSERT OR IGNORE
        return stmt.prefix_with("OR IGNORE")

    def get_date_trunc_expression(self, field: Any, precision: str) -> Any:
        """Generate SQLite strftime expression."""
        from sqlalchemy import func

        format_map = {"year": "%Y", "month": "%Y-%m", "day": "%Y-%m-%d"}
        return func.strftime(format_map.get(precision, "%Y-%m-%d"), field)

    def get_datetime_trunc_expression(self, field: Any, precision: str) -> Any:
        """Generate SQLite strftime expression for datetime."""
        return self.get_date_trunc_expression(field, precision)

    def supports_returning(self) -> bool:
        """SQLite 3.35+ supports RETURNING."""
        return True

    def build_explain_query(self, sql: str, analyze: bool, verbose: bool) -> str:
        """Build SQLite EXPLAIN query.

        Note: SQLite doesn't support ANALYZE or VERBOSE in EXPLAIN.
        """
        return f"EXPLAIN QUERY PLAN {sql}"

    def parse_explain_result(self, rows: list) -> str:
        """Parse SQLite EXPLAIN result.

        SQLite EXPLAIN QUERY PLAN returns: (id, parent, notused, detail)
        We want the detail column (last column).
        """
        return "\n".join(str(row[-1]) for row in rows)


class DialectHandler:
    """Factory for creating database dialect handlers."""

    _dialects = {
        "postgresql": PostgreSQLDialect,
        "mysql": MySQLDialect,
        "sqlite": SQLiteDialect,
    }

    @classmethod
    def create(cls, session: "AsyncSession") -> BaseDialect:
        """Create dialect handler from session."""
        dialect_name = session.bind.dialect.name
        return cls.get_dialect(dialect_name)

    @classmethod
    def get_dialect(cls, dialect_name: str) -> BaseDialect:
        """Get dialect handler for the specified database."""
        dialect_class = cls._dialects.get(dialect_name)
        if not dialect_class:
            raise ValueError(f"Unsupported dialect: {dialect_name}")
        return dialect_class(dialect_name)

"""Unified UPSERT and conflict resolution system for all database types."""

from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

from ..queries.dialect import DialectHandler


if TYPE_CHECKING:
    from ..session import AsyncSession


__all__ = ["UpsertHandler", "ConflictResolution"]


class ConflictResolution:
    """Defines conflict resolution strategies for UPSERT operations."""

    IGNORE = "ignore"
    UPDATE = "update"
    REPLACE = "replace"


class UpsertHandler:
    """Handles UPSERT operations with database-specific syntax."""

    def __init__(self, session: "AsyncSession"):
        self.session = session
        self.dialect = DialectHandler.create(session)

    def get_upsert_statement(
        self,
        table: sa.Table,
        values: list[dict[str, Any]],
        conflict_resolution: str = ConflictResolution.IGNORE,
        match_fields: list[str] | None = None,
    ) -> sa.sql.Insert:
        """Generate database-specific UPSERT statement."""
        if not values:
            return sa.insert(table)

        # Determine update fields based on conflict resolution
        if conflict_resolution == ConflictResolution.UPDATE:
            all_fields = list(values[0].keys())
            update_fields = [f for f in all_fields if f not in (match_fields or [])]
        else:
            update_fields = []

        # Use DialectHandler to generate statement
        return self.dialect.get_upsert_statement(
            table=table,
            data=values[0],
            conflict_fields=match_fields or [],
            update_fields=update_fields,
        )

    async def execute_upsert_with_returning(
        self,
        table: sa.Table,
        values: list[dict[str, Any]],
        conflict_resolution: str = ConflictResolution.IGNORE,
        match_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute UPSERT and return affected rows."""
        if not values:
            return []

        stmt = self.get_upsert_statement(table, values, conflict_resolution, match_fields)

        if self.dialect.supports_returning():
            stmt = stmt.returning(*table.columns)  # noqa
            result = await self.session.execute(stmt)
            return [dict(row._mapping) for row in result.fetchall()]  # noqa
        else:
            # For databases without RETURNING support
            result = await self.session.execute(stmt)
            return values[: result.rowcount] if result.rowcount and result.rowcount > 0 else []

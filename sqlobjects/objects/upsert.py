"""Unified UPSERT and conflict resolution system for all database types."""

from typing import TYPE_CHECKING, Any

import sqlalchemy as sa


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
        self.dialect_name = session.bind.dialect.name

    def get_upsert_statement(
        self,
        table: sa.Table,
        values: list[dict[str, Any]],
        conflict_resolution: str = ConflictResolution.IGNORE,
        match_fields: list[str] | None = None,
    ) -> sa.sql.Insert:
        """Generate database-specific UPSERT statement."""
        if self.dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            insert_stmt = pg_insert(table).values(values)
            return self._get_postgresql_upsert(insert_stmt, table, conflict_resolution, match_fields)
        elif self.dialect_name == "mysql":
            insert_stmt = sa.insert(table).values(values)
            return self._get_mysql_upsert(insert_stmt, conflict_resolution)
        elif self.dialect_name == "sqlite":
            return self._get_sqlite_upsert(table, values, conflict_resolution, match_fields)
        else:
            return sa.insert(table).values(values)

    @staticmethod
    def _get_postgresql_upsert(
        insert_stmt: sa.sql.Insert, table: sa.Table, conflict_resolution: str, match_fields: list[str] | None
    ) -> sa.sql.Insert:
        """Generate PostgreSQL ON CONFLICT statement."""
        if conflict_resolution == ConflictResolution.IGNORE:
            if match_fields:
                conflict_columns = [table.c[field] for field in match_fields]
                return insert_stmt.on_conflict_do_nothing(index_elements=conflict_columns)  # type: ignore[reportAttributeAccessIssue]
            return insert_stmt.on_conflict_do_nothing()  # type: ignore[reportAttributeAccessIssue]
        elif conflict_resolution == ConflictResolution.UPDATE:
            if match_fields:
                conflict_columns = [table.c[field] for field in match_fields]
            else:
                conflict_columns = [col for col in table.primary_key.columns]  # noqa

            update_dict = {
                col.name: insert_stmt.excluded[col.name]  # type: ignore[reportAttributeAccessIssue]
                for col in table.columns  # noqa
                if col.name not in [c.name for c in conflict_columns]
            }

            return insert_stmt.on_conflict_do_update(  # type: ignore[reportAttributeAccessIssue]
                index_elements=conflict_columns, set_=update_dict
            )
        return insert_stmt

    @staticmethod
    def _get_mysql_upsert(insert_stmt: sa.sql.Insert, conflict_resolution: str) -> sa.sql.Insert:
        """Generate MySQL ON DUPLICATE KEY statement."""
        if conflict_resolution == ConflictResolution.IGNORE:
            return insert_stmt.prefix_with("IGNORE")
        elif conflict_resolution == ConflictResolution.UPDATE:
            return insert_stmt.on_duplicate_key_update(  # type: ignore[reportAttributeAccessIssue]
                **{col.name: sa.text(f"VALUES({col.name})") for col in insert_stmt.table.columns}  # noqa
            )
        return insert_stmt

    @staticmethod
    def _get_sqlite_upsert(
        table: sa.Table, values: list[dict[str, Any]], conflict_resolution: str, match_fields: list[str] | None
    ) -> sa.sql.Insert:
        """Generate SQLite ON CONFLICT statement."""
        if conflict_resolution == ConflictResolution.IGNORE:
            if match_fields:
                # Use ON CONFLICT with specific columns
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                sqlite_stmt = sqlite_insert(table).values(values)
                conflict_columns = [table.c[field] for field in match_fields]
                return sqlite_stmt.on_conflict_do_nothing(index_elements=conflict_columns)
            else:
                # Use INSERT OR IGNORE for general conflicts
                return sa.insert(table).values(values).prefix_with("OR IGNORE")
        elif conflict_resolution == ConflictResolution.UPDATE:
            if match_fields:
                # Use ON CONFLICT DO UPDATE with specific columns
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                sqlite_stmt = sqlite_insert(table).values(values)
                conflict_columns = [table.c[field] for field in match_fields]

                update_dict = {
                    col.name: sqlite_stmt.excluded[col.name]
                    for col in table.columns
                    if col.name not in match_fields  # noqa
                }

                return sqlite_stmt.on_conflict_do_update(index_elements=conflict_columns, set_=update_dict)
            else:
                # Use INSERT OR REPLACE for general conflicts
                return sa.insert(table).values(values).prefix_with("OR REPLACE")
        return sa.insert(table).values(values)

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

        if self.dialect_name in ("postgresql", "sqlite"):
            stmt = stmt.returning(*table.columns)  # noqa
            result = await self.session.execute(stmt)
            return [dict(row._mapping) for row in result.fetchall()]  # noqa
        else:
            # For MySQL, execute and return the input values with any defaults applied
            result = await self.session.execute(stmt)
            # For MySQL without RETURNING, we can't get the exact inserted data
            # Return the input values as approximation
            return values[: result.rowcount] if result.rowcount else []

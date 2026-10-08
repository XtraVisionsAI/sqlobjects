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
            data=values[0] if len(values) == 1 else values,
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
        match_fields = match_fields or []

        # A matching key lets us restore input order after a multi-row RETURNING.
        can_match = bool(match_fields) and all(
            all(field in value and value[field] is not None for field in match_fields) for value in values
        )
        if (
            self.dialect.supports_returning()
            and can_match
            and len({tuple(v[f] for f in match_fields) for v in values}) == len(values)
        ):
            stmt = self.get_upsert_statement(table, values, conflict_resolution, match_fields)
            stmt = stmt.returning(*table.columns)  # noqa
            result = await self.session.execute(stmt)
            rows = {tuple(row._mapping[f] for f in match_fields): dict(row._mapping) for row in result.fetchall()}
            return [rows[key] for value in values if (key := tuple(value[f] for f in match_fields)) in rows]

        rows = []
        for value in values:
            stmt = self.get_upsert_statement(table, [value], conflict_resolution, match_fields)
            if self.dialect.supports_returning():
                result = await self.session.execute(stmt.returning(*table.columns))
                rows.extend(dict(row._mapping) for row in result.fetchall())
                continue
            result = await self.session.execute(stmt)
            if result.rowcount <= 0:
                continue
            # Fetch actual stored values; affected-row counts are not input offsets.
            keys: dict[str, Any] = {field: value[field] for field in match_fields if field in value}
            if not keys:
                primary_key = result.inserted_primary_key
                if primary_key is not None:
                    keys = dict(zip((col.name for col in table.primary_key), primary_key, strict=True))
            if not keys or any(v is None for v in keys.values()):
                raise ValueError("UPSERT without RETURNING requires conflict fields or a generated primary key")
            stored = await self.session.execute(sa.select(table).where(*(table.c[k] == v for k, v in keys.items())))
            row = stored.one()
            rows.append(dict(row._mapping))
        return rows

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

    async def _match_returned_rows(
        self,
        table: sa.Table,
        values: list[dict[str, Any]],
        match_fields: list[str],
        returned: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Restore input order for multi-row RETURNING without trusting input values.

        The database may normalize conflict-key values (string to integer,
        Decimal scale, timezone, case-insensitive collations, UUID objects), so a
        returned row does not always equal the raw input key. Rows that cannot be
        matched in Python are resolved by asking the database, and only accepted
        when they are among the rows this statement actually returned.
        """
        by_key: dict[tuple, dict[str, Any]] = {}
        for row in returned:
            by_key.setdefault(tuple(row[f] for f in match_fields), row)
        pk_columns = [col.name for col in table.primary_key]

        def identity(row: dict[str, Any]) -> tuple:
            return tuple(row[c] for c in pk_columns) if pk_columns else tuple(sorted(row.items()))

        ordered: list[dict[str, Any] | None] = []
        unmatched: list[int] = []
        for index, value in enumerate(values):
            row = by_key.pop(tuple(value[f] for f in match_fields), None)
            ordered.append(row)
            if row is None:
                unmatched.append(index)

        # Every returned row was matched, or nothing is left to attribute.
        if unmatched and by_key:
            remaining = {identity(row) for row in by_key.values()}
            for index in unmatched:
                if not remaining:
                    break
                value = values[index]
                stored = await self.session.execute(
                    sa.select(table).where(*(table.c[f] == value[f] for f in match_fields))
                )
                row = stored.one_or_none()
                if row is None:
                    continue
                data = dict(row._mapping)
                if identity(data) in remaining:
                    remaining.discard(identity(data))
                    ordered[index] = data
        return [row for row in ordered if row is not None]

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
            return await self._match_returned_rows(table, values, match_fields, [dict(r._mapping) for r in result])

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

"""Internal SQL operations utilities

This module provides low-level SQL execution utilities shared by
Model and Bulk operations. These are internal utilities and should
not be used directly by end users.
"""

from sqlalchemy import delete, select, update


__all__ = ["SQLOperations"]


class SQLOperations:
    """Low-level SQL execution utilities for internal use

    Provides pure SQL operations without ORM overhead, used by both
    Model._internal methods and Bulk operations.
    """

    @staticmethod
    async def execute_delete(session, table, conditions):
        """Execute DELETE statement

        Args:
            session: Database session
            table: SQLAlchemy Table object
            conditions: WHERE condition expression or list of conditions

        Returns:
            Number of deleted rows
        """
        from sqlalchemy import and_

        if isinstance(conditions, list):
            if not conditions:
                raise ValueError("Cannot execute DELETE without conditions")
            condition = and_(*conditions) if len(conditions) > 1 else conditions[0]
        else:
            condition = conditions

        stmt = delete(table).where(condition)
        result = await session.execute(stmt)
        return result.rowcount

    @staticmethod
    async def execute_update(session, table, conditions, values):
        """Execute UPDATE statement

        Args:
            session: Database session
            table: SQLAlchemy Table object
            conditions: WHERE condition expression or list of conditions
            values: Dictionary of field values to update

        Returns:
            Number of updated rows
        """
        from sqlalchemy import and_

        if not values:
            return 0

        if isinstance(conditions, list):
            if not conditions:
                raise ValueError("Cannot execute UPDATE without conditions")
            condition = and_(*conditions) if len(conditions) > 1 else conditions[0]
        else:
            condition = conditions

        stmt = update(table).where(condition).values(**values)
        result = await session.execute(stmt)
        return result.rowcount

    @staticmethod
    async def execute_select(session, table, condition, columns=None):
        """Execute SELECT statement

        Args:
            session: Database session
            table: SQLAlchemy Table object
            condition: WHERE condition expression
            columns: List of columns to select (None = all columns)

        Returns:
            Query result object
        """
        if columns:
            stmt = select(*columns).select_from(table).where(condition)
        else:
            stmt = select(table).where(condition)
        result = await session.execute(stmt)
        return result

    @staticmethod
    def build_in_condition(table, field, values):
        """Build WHERE field IN (values) condition

        Args:
            table: SQLAlchemy Table object
            field: Field name (string)
            values: List of values for IN clause

        Returns:
            SQLAlchemy condition expression
        """
        return table.c[field].in_(values)

    @staticmethod
    def build_eq_condition(table, field, value):
        """Build WHERE field = value condition

        Args:
            table: SQLAlchemy Table object
            field: Field name (string)
            value: Field value

        Returns:
            SQLAlchemy condition expression
        """
        return table.c[field] == value

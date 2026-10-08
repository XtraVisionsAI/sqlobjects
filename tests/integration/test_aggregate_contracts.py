"""Aggregation evaluates the same input rows through every public entry point."""

import pytest
from sqlalchemy import column, event, func, select

from sqlobjects import Q
from sqlobjects.database import close_db, init_db
from sqlobjects.exceptions import QueryError
from sqlobjects.fields import Column, IntegerColumn, StringColumn, foreign_key, identity, relationship
from sqlobjects.metadata import ModelRegistry
from sqlobjects.model import ObjectModel
from sqlobjects.session import ctx_session
from tests.test_config import TestDatabaseConfig


class AggregateBase(ObjectModel):
    __abstract__ = True
    __registry__ = ModelRegistry()


class AggregateParent(AggregateBase):
    id: Column[int] = identity()
    category: Column[str] = StringColumn(length=20)
    amount: Column[int] = IntegerColumn(deferred=True)


class AggregateChild(AggregateBase):
    id: Column[int] = identity()
    parent_id: Column[int] = foreign_key("aggregate_parents.id")
    score: Column[int] = IntegerColumn()
    parent = relationship("AggregateParent", foreign_keys="parent_id")


@pytest.fixture(autouse=True)
def clean_db():
    """This suite owns its registry and database lifecycle."""


@pytest.fixture
async def aggregate_db(db_type, tmp_path):
    config = TestDatabaseConfig.get_config(db_type)
    url = f"sqlite+aiosqlite:///{tmp_path / 'aggregate.db'}" if db_type == "sqlite" else config["url"]
    db = await init_db(url, **config["pool_config"])
    await db.create_tables(AggregateBase)
    try:
        parents = [
            await AggregateParent.objects.create(category=category, amount=amount)
            for category, amount in [("a", 10), ("a", 20), ("b", 40)]
        ]
        await AggregateChild.objects.bulk_create(
            [
                {"parent_id": parents[0].id, "score": 2},
                {"parent_id": parents[0].id, "score": 3},
                {"parent_id": parents[1].id, "score": 5},
            ]
        )
        yield db
    finally:
        await db.drop_tables(AggregateBase)
        await close_db()


async def assert_total(query, expected):
    expression = query.aggregate(total=func.sum(AggregateParent.amount))
    assert await expression == {"total": expected}
    async with ctx_session() as session:
        assert (await session.execute(expression.get_query())).scalar_one() == expected
        assert (await session.execute(select(expression.scalar_subquery()))).scalar_one() == expected
    return expression


@pytest.mark.usefixtures("aggregate_db")
class TestAggregateContracts:
    async def test_filters_and_sql_rendering(self):
        query = AggregateParent.objects.filter(Q(AggregateParent.amount >= 10), category="a").extra(
            where=["amount < :ceiling"], params={"ceiling": 20}
        )
        expression = await assert_total(query, 10)
        sql = expression.get_sql()
        assert "sum(" in sql
        assert "'a'" in sql and "amount < 20" in sql

    @pytest.mark.parametrize("limit,offset,expected", [(1, 1, 20), (0, 0, None), (2, 8, None), (None, 1, 30)])
    async def test_slicing_precedes_aggregation(self, limit, offset, expected):
        query = AggregateParent.objects.order_by("-amount").offset(offset)
        if limit is not None:
            query = query.limit(limit)
        await assert_total(query, expected)
        assert await AggregateParent.objects.count() == 3

    async def test_join_duplicates_and_distinct_rows(self):
        query = AggregateParent.objects.join(AggregateChild, AggregateParent.id == AggregateChild.parent_id)
        await assert_total(query, 40)
        await assert_total(query.distinct(), 30)
        await assert_total(query.distinct().order_by("amount").offset(1), 20)

    async def test_joined_column_and_expression_inputs(self):
        query = (
            AggregateParent.objects.join(AggregateChild, AggregateParent.id == AggregateChild.parent_id)
            .order_by(AggregateChild.score.desc())
            .limit(2)
        )
        assert await query.aggregate(total=func.sum(AggregateChild.score), rows=func.count()) == {"total": 8, "rows": 2}
        assert await query.aggregate(total=func.sum(AggregateParent.amount + AggregateChild.score)) == {"total": 38}
        assert await query.aggregate(total=func.count(AggregateParent.amount.distinct())) == {"total": 2}

    async def test_distinct_rejects_unselected_joined_input(self):
        query = AggregateParent.objects.join(AggregateChild, AggregateParent.id == AggregateChild.parent_id).distinct()
        with pytest.raises(QueryError, match="DISTINCT.*projected"):
            await query.aggregate(total=func.sum(AggregateChild.score))
        projected = query.annotate(child_score=AggregateChild.score)
        assert await projected.aggregate(total=func.sum(column("child_score"))) == {"total": 10}

    @pytest.mark.parametrize("projection", ["only", "defer"])
    async def test_hydration_projection_does_not_hide_aggregate_input(self, projection):
        query = getattr(AggregateParent.objects, projection)("category")
        await assert_total(query, 70)
        await assert_total(query.distinct(), 70)
        await assert_total(query.order_by("-amount").limit(1), 40)

    async def test_annotations_can_be_aggregated_by_alias(self):
        query = AggregateParent.objects.annotate(doubled=AggregateParent.amount * 2).order_by("id").limit(2)
        assert await query.aggregate(total=func.sum(column("doubled"))) == {"total": 60}
        assert await query.aggregate(total=AggregateParent.amount.sum()) == {"total": 30}

    async def test_empty_input_retains_sql_aggregate_defaults(self):
        for query in [AggregateParent.objects.none(), AggregateParent.objects.limit(0)]:
            assert await query.aggregate(rows=func.count(), total=func.sum(AggregateParent.amount)) == {
                "rows": 0,
                "total": None,
            }
        query = AggregateParent.objects.annotate(doubled=AggregateParent.amount * 2).none()
        assert await query.aggregate(total=func.sum(column("doubled"))) == {"total": None}

    async def test_bound_session_and_uncorrelated_comparison(self):
        async with ctx_session() as session:
            expression = (
                AggregateParent.objects.using(session)
                .filter(category="a")
                .aggregate(total=func.sum(AggregateParent.amount))
            )
            assert await expression == {"total": 30}
            result = (
                await AggregateParent.objects.using(session)
                .filter(AggregateParent.amount > expression)
                .values("amount")
            )
            assert result == [{"amount": 40}]

    @pytest.mark.parametrize("sliced", [False, True])
    async def test_correlated_scalar_aggregate(self, sliced):
        query = AggregateChild.objects.filter(AggregateChild.parent_id == AggregateParent.id).order_by("-score")
        if sliced:
            query = query.limit(1)
        total = query.aggregate(total=func.sum(AggregateChild.score)).scalar_subquery()
        result = await AggregateParent.objects.order_by("id").annotate(total=total).values_list("total", flat=True)
        assert result == ([3, 5, None] if sliced else [5, 5, None])

    async def test_scalar_expression_input_keeps_its_local_query_scope(self):
        child_score = (
            select(func.max(AggregateChild.score))
            .where(AggregateChild.parent_id == AggregateParent.id)
            .correlate(AggregateParent.__table__)
            .scalar_subquery()
        )
        assert await AggregateParent.objects.order_by("id").limit(2).aggregate(total=func.sum(child_score)) == {
            "total": 8
        }

    async def test_select_related_left_join_and_cte(self):
        child_query = AggregateChild.objects.select_related("parent").order_by("score").limit(2)
        assert await child_query.aggregate(total=func.sum(AggregateChild.score)) == {"total": 5}
        left_join = AggregateParent.objects.join(
            AggregateChild, AggregateParent.id == AggregateChild.parent_id, join_type="left"
        )
        assert await left_join.aggregate(rows=func.count(), children=func.count(AggregateChild.id)) == {
            "rows": 4,
            "children": 3,
        }
        adults = AggregateParent.objects.filter(category="a").cte("selected_parents")
        expression = await assert_total(AggregateParent.objects.with_cte(adults).filter(category="b"), 40)
        assert "WITH selected_parents" in expression.get_sql()

    async def test_explain_uses_the_actual_aggregate_statement(self, aggregate_db):
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(aggregate_db.engine.sync_engine, "before_cursor_execute", record)
        try:
            expression = (
                AggregateParent.objects.order_by("id").limit(2).aggregate(total=func.sum(AggregateParent.amount))
            )
            assert await expression.explain()
            assert any("EXPLAIN" in sql and "sum(" in sql and "LIMIT" in sql for sql in statements)
        finally:
            event.remove(aggregate_db.engine.sync_engine, "before_cursor_execute", record)

    @pytest.mark.parametrize("operation", ["select_for_update", "select_for_share", "having"])
    async def test_unsupported_shapes_fail_before_execution(self, operation):
        query = AggregateParent.objects.filter()
        query = query.having(func.count() > 0) if operation == "having" else getattr(query, operation)()
        with pytest.raises(QueryError, match="aggregate"):
            query.aggregate(total=func.sum(AggregateParent.amount))

    async def test_invalid_aggregate_shapes(self):
        with pytest.raises(ValueError, match="at least one"):
            AggregateParent.objects.aggregate()
        expression = AggregateParent.objects.aggregate(rows=func.count(), total=func.sum(AggregateParent.amount))
        with pytest.raises(ValueError, match="multi-field"):
            expression.scalar_subquery()

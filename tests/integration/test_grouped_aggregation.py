"""A terminal aggregate summarizes the rows produced by grouping and HAVING."""

import pytest
from sqlalchemy import column, event, func, literal, select

from sqlobjects import Q
from sqlobjects.exceptions import QueryError
from sqlobjects.session import ctx_session
from tests.integration.test_aggregate_contracts import AggregateChild, AggregateParent
from tests.integration.test_aggregate_contracts import aggregate_db as _aggregate_db
from tests.integration.test_aggregate_contracts import clean_db as _clean_db


aggregate_db = _aggregate_db
clean_db = _clean_db


def category_totals():
    return AggregateParent.objects.annotate(subtotal=func.sum(AggregateParent.amount)).group_by("category")


@pytest.mark.usefixtures("aggregate_db")
class TestGroupedAggregation:
    async def test_count_groups_without_annotations(self):
        expression = AggregateParent.objects.group_by("category").aggregate(groups=func.count())
        assert await expression == {"groups": 2}
        sql = expression.get_sql()
        assert "GROUP BY aggregate_parents.category" in sql
        assert "aggregate_parents.id" not in sql

    async def test_aggregate_over_annotation_aliases(self):
        original = category_totals()
        assert await original.aggregate(
            total=func.sum(column("subtotal")), groups=func.count(), mean=func.avg(column("subtotal"))
        ) == {"total": 70, "groups": 2, "mean": 35}
        assert await original.order_by("category").values("category", "subtotal") == [
            {"category": "a", "subtotal": 30},
            {"category": "b", "subtotal": 40},
        ]

    async def test_having_and_filters_run_before_outer_aggregate(self):
        query = (
            category_totals()
            .filter(Q(AggregateParent.amount >= 10))
            .extra(where=["amount < :ceiling"], params={"ceiling": 50})
            .having(func.sum(AggregateParent.amount) > 30)
        )
        expression = query.aggregate(total=func.sum(column("subtotal")))
        assert await expression == {"total": 40}
        async with ctx_session() as session:
            assert (await session.execute(expression.get_query())).scalar_one() == 40
            assert (await session.execute(select(expression.scalar_subquery()))).scalar_one() == 40
        sql = expression.get_sql()
        assert "HAVING" in sql and "amount < 50" in sql

    @pytest.mark.parametrize("offset, expected", [(0, 40), (1, 30), (2, None)])
    async def test_annotation_ordering_and_slicing_select_groups(self, offset, expected):
        query = category_totals().order_by("-subtotal").offset(offset).limit(1)
        assert await query.aggregate(total=func.sum(column("subtotal"))) == {"total": expected}

    @pytest.mark.parametrize("empty", ["none", "limit", "having"])
    async def test_empty_group_inputs(self, empty):
        query = category_totals()
        if empty == "none":
            query = query.none()
        elif empty == "limit":
            query = query.limit(0)
        else:
            query = query.having(func.sum(AggregateParent.amount) > 100)
        assert await query.aggregate(groups=func.count(), total=func.sum(column("subtotal"))) == {
            "groups": 0,
            "total": None,
        }

    async def test_group_keys_and_hydration_hints(self):
        query = AggregateParent.objects.only("id").defer("amount").group_by("amount")
        assert await query.aggregate(total=func.sum(AggregateParent.amount)) == {"total": 70}
        assert await category_totals().only("id").defer("category").aggregate(groups=func.count()) == {"groups": 2}

    @pytest.mark.parametrize("kind", ["expression", "alias"])
    async def test_computed_grouping_keys(self, kind):
        grouped_key = func.length(AggregateParent.category)
        query = AggregateParent.objects.annotate(subtotal=func.sum(AggregateParent.amount))
        if kind == "alias":
            query = query.annotate(category_length=grouped_key).group_by("category_length")
            outer_key = column("category_length")
        else:
            query = query.group_by(grouped_key)
            # A separately constructed equivalent expression should resolve too.
            outer_key = func.length(AggregateParent.category)
        assert await query.aggregate(key_total=func.sum(outer_key), total=func.sum(column("subtotal"))) == {
            "key_total": 1,
            "total": 70,
        }

    async def test_joined_groups(self):
        query = (
            AggregateChild.objects.join(AggregateParent, AggregateChild.parent_id == AggregateParent.id)
            .group_by(AggregateParent.category)
            .annotate(subtotal=func.sum(AggregateChild.score))
        )
        assert await query.aggregate(total=func.sum(column("subtotal")), groups=func.count()) == {
            "total": 10,
            "groups": 1,
        }

    async def test_correlated_grouped_scalar_subquery(self):
        query = (
            AggregateChild.objects.filter(AggregateChild.parent_id == AggregateParent.id)
            .group_by("score")
            .annotate(score_count=func.count())
        )
        total = query.aggregate(total=func.sum(column("score_count"))).scalar_subquery()
        assert await AggregateParent.objects.order_by("id").annotate(total=total).values_list("total", flat=True) == [
            2,
            1,
            None,
        ]

    async def test_distinct_and_bound_session(self):
        async with ctx_session() as session:
            expression = category_totals().distinct().using(session).aggregate(total=func.sum(column("subtotal")))
            assert await expression == {"total": 70}

    async def test_explain_describes_the_outer_aggregate(self, aggregate_db):
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(aggregate_db.engine.sync_engine, "before_cursor_execute", record)
        try:
            expression = category_totals().having(func.count() > 1).aggregate(total=func.sum(column("subtotal")))
            assert await expression.explain()
            assert any(
                "EXPLAIN" in sql and "GROUP BY" in sql and "HAVING" in sql and sql.lower().count("sum(") >= 2
                for sql in statements
            )
        finally:
            event.remove(aggregate_db.engine.sync_engine, "before_cursor_execute", record)

    async def test_ungrouped_column_is_rejected_before_sql(self, aggregate_db):
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(aggregate_db.engine.sync_engine, "before_cursor_execute", record)
        try:
            with pytest.raises(QueryError, match="grouping key|annotation"):
                await category_totals().aggregate(total=func.sum(AggregateParent.amount))
            assert statements == []
        finally:
            event.remove(aggregate_db.engine.sync_engine, "before_cursor_execute", record)

    async def test_unknown_grouping_alias_is_rejected(self):
        with pytest.raises(QueryError, match="Unknown.*group"):
            await category_totals().group_by("missing").aggregate(groups=func.count())

    async def test_wrapped_expression_groups_and_reversed_annotation_order(self):
        query = AggregateParent.objects.annotate(subtotal=AggregateParent.amount.sum()).group_by(
            AggregateParent.amount % 20
        )
        assert await query.order_by("-subtotal").reverse().limit(1).aggregate(total=func.sum(column("subtotal"))) == {
            "total": 10
        }

    async def test_multiple_keys_and_duplicate_group_entries(self):
        query = AggregateParent.objects.group_by("category", AggregateParent.amount, "category")
        assert await query.aggregate(groups=func.count(), total=func.sum(AggregateParent.amount)) == {
            "groups": 3,
            "total": 70,
        }

    async def test_annotation_alias_must_not_shadow_a_model_column(self):
        with pytest.raises(QueryError, match="aliases shadow model columns"):
            await (
                AggregateParent.objects.annotate(id=func.count())
                .group_by("category")
                .aggregate(total=func.sum(column("id")))
            )

    async def test_user_annotation_does_not_collide_with_internal_group_labels(self):
        query = AggregateParent.objects.annotate(_sqlobjects_group_0=func.sum(AggregateParent.amount)).group_by(
            "category"
        )
        assert await query.aggregate(total=func.sum(column("_sqlobjects_group_0"))) == {"total": 70}

    async def test_distinct_on_grouped_input_retains_backend_validation(self, aggregate_db):
        query = category_totals().order_by("category").distinct("category")
        expression = query.aggregate(total=func.sum(column("subtotal")))
        if aggregate_db.engine.dialect.name == "postgresql":
            assert await expression == {"total": 70}
        else:
            with pytest.raises(QueryError, match="PostgreSQL"):
                await expression

    async def test_grouped_cte_dependency_is_retained(self):
        records = AggregateParent.objects.filter(category="a").cte("filtered_parents")
        expression = category_totals().with_cte(records).aggregate(total=func.sum(column("subtotal")))
        assert await expression == {"total": 70}
        assert "WITH filtered_parents" in expression.get_sql()

    async def test_native_expression_grouping_also_works_in_values_queries(self):
        query = AggregateParent.objects.annotate(
            category_length=func.length(AggregateParent.category), subtotal=func.sum(AggregateParent.amount)
        ).group_by(func.length(AggregateParent.category))
        assert await query.values("category_length", "subtotal") == [{"category_length": 1, "subtotal": 70}]

    async def test_constant_grouping_does_not_rebind_outer_default_values(self):
        query = AggregateParent.objects.annotate(subtotal=func.sum(AggregateParent.amount)).group_by(literal(1))
        assert await query.aggregate(total=func.coalesce(func.sum(column("subtotal")), 1)) == {"total": 70}
        assert await query.none().aggregate(total=func.coalesce(func.sum(column("subtotal")), 1)) == {"total": 1}

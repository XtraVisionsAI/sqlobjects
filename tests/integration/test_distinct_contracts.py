"""DISTINCT must survive cloning, projection, counting and dialect validation."""

import pytest
from sqlalchemy import event, func, select

from sqlobjects.exceptions import QueryError
from sqlobjects.session import ctx_session
from tests.integration.test_orm_contracts import ContractChild, ContractParent, ContractRecord, seed
from tests.integration.test_orm_contracts import clean_db as _clean_db
from tests.integration.test_orm_contracts import contract_db as _contract_db


clean_db = _clean_db
contract_db = _contract_db


@pytest.mark.usefixtures("contract_db")
class TestDistinctContracts:
    async def test_plain_distinct_projects_unique_values_and_preserves_original(self):
        await seed(4)
        original = ContractRecord.objects.order_by("value")
        distinct = original.distinct().filter(ContractRecord.value >= 0)
        assert await distinct.values_list("value", flat=True) == [0, 1]
        assert await distinct.values("value") == [{"value": 0}, {"value": 1}]
        assert await original.values_list("value", flat=True) == [0, 0, 1, 1]
        assert await original.distinct("value").distinct().values_list("value", flat=True) == [0, 1]

    async def test_join_deduplication_matches_count_stream_and_slices(self):
        parent = await ContractParent.objects.create(code="parent")
        await ContractChild.objects.bulk_create([{"author_code": "parent", "reviewer_code": "parent"}] * 3)
        query = ContractParent.objects.join(
            ContractChild.__table__, ContractParent.code == ContractChild.author_code
        ).order_by("id")
        assert await query.count() == 3
        unique = query.distinct()
        assert [obj.id for obj in await unique.all()] == [parent.id]
        assert await unique.count() == 1
        assert [obj.id async for obj in unique.iterator(chunk_size=1)] == [parent.id]
        assert await unique.offset(1).count() == 0
        async with ctx_session() as session:
            result = await session.execute(select(unique.count().scalar_subquery()))
            assert result.scalar_one() == 1

    @pytest.mark.parametrize("operation", ["update", "delete"])
    async def test_plain_distinct_write_is_rejected(self, operation):
        await seed(2)
        query = ContractRecord.objects.distinct()
        with pytest.raises(QueryError, match="distinct"):
            if operation == "update":
                await query.update(value=9)
            else:
                await query.delete(cascade="none")
        assert await ContractRecord.objects.count() == 2
        assert await ContractRecord.objects.filter(value=9).count() == 0

    @pytest.mark.parametrize("fields", [("missing",), ("value", "missing")])
    async def test_unknown_distinct_fields_are_rejected(self, fields):
        with pytest.raises(QueryError, match="missing"):
            await ContractRecord.objects.distinct(*fields).all()

    async def test_aggregate_preserves_distinct_rows(self):
        await seed(4)
        assert await ContractRecord.objects.distinct().aggregate(total=func.sum(ContractRecord.value)) == {"total": 2}

    @pytest.mark.parametrize(
        "evaluation",
        [
            "all",
            "count",
            "exists",
            "iterator",
            "subquery",
            "cte",
            "explain",
            "aggregate",
            "aggregate_scalar",
            "aggregate_explain",
        ],
    )
    async def test_distinct_on_is_postgresql_only_in_nested_queries(self, evaluation, contract_db):
        await seed(4)
        query = ContractRecord.objects.order_by("value", "id").distinct("value")
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        async def evaluate():
            if evaluation.startswith("aggregate"):
                expression = query.aggregate(total=func.sum(ContractRecord.value))
                if evaluation == "aggregate_scalar":
                    async with ctx_session() as session:
                        return (await session.execute(select(expression.scalar_subquery()))).scalar_one()
                if evaluation == "aggregate_explain":
                    return await expression.explain()
                return await expression
            if evaluation == "explain":
                return await query.all().explain()
            if evaluation == "iterator":
                return [obj async for obj in query.iterator()]
            if evaluation in {"subquery", "cte"}:
                statement = query._builder.build(ContractRecord.__table__)
                nested = statement.cte() if evaluation == "cte" else statement.subquery()
                async with ctx_session() as session:
                    return (await session.execute(select(nested))).all()
            return await getattr(query, evaluation)()

        event.listen(contract_db.engine.sync_engine, "before_cursor_execute", record)
        try:
            if contract_db.engine.dialect.name == "postgresql":
                result = await evaluate()
                if evaluation == "aggregate":
                    assert result == {"total": 1}
                elif evaluation == "aggregate_scalar":
                    assert result == 1
                elif evaluation == "count":
                    assert result == 2
                elif evaluation == "exists":
                    assert result is True
                elif evaluation in {"explain", "aggregate_explain"}:
                    assert "Unique" in result
                else:
                    assert isinstance(result, list)
                    assert [row.name for row in result] == ["r0", "r1"]
            else:
                with pytest.raises(QueryError, match="PostgreSQL"):
                    await evaluate()
                assert statements == []
        finally:
            event.remove(contract_db.engine.sync_engine, "before_cursor_execute", record)

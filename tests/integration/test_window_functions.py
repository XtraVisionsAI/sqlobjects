"""Integration tests for window functions."""

import pytest

from sqlobjects.expressions import func
from sqlobjects.fields import Column, IntegerColumn, StringColumn
from sqlobjects.model import ObjectModel


class Employee(ObjectModel):
    id: Column[int] = IntegerColumn(primary_key=True)
    name: Column[str] = StringColumn(length=50)
    department: Column[str] = StringColumn(length=50)
    salary: Column[int] = IntegerColumn()

    class Config:
        table_name = "employees"


@pytest.fixture
async def sample_employees(session):
    """Create sample employee data."""
    employees = [
        {"name": "Alice", "department": "Engineering", "salary": 100000},
        {"name": "Bob", "department": "Engineering", "salary": 90000},
        {"name": "Charlie", "department": "Engineering", "salary": 95000},
        {"name": "David", "department": "Sales", "salary": 80000},
        {"name": "Eve", "department": "Sales", "salary": 85000},
        {"name": "Frank", "department": "Sales", "salary": 75000},
    ]
    await Employee.objects.using(session).bulk_create(employees)


@pytest.mark.asyncio
class TestWindowFunctions:
    """Test window function implementations."""

    @pytest.mark.usefixtures("sample_employees")
    async def test_row_number_basic(self, session):
        """Test ROW_NUMBER() with ORDER BY."""
        employees = await (
            Employee.objects.using(session)
            .annotate(row_num=func.row_number().over(order_by=[Employee.salary]))
            .order_by("salary")
            .all()
        )

        assert len(employees) == 6
        # Check row numbers are sequential
        for i, emp in enumerate(employees, 1):
            assert emp.row_num == i

    @pytest.mark.usefixtures("sample_employees")
    async def test_rank_with_partition(self, session):
        """Test RANK() with PARTITION BY."""
        employees = await (
            Employee.objects.using(session)
            .annotate(dept_rank=func.rank().over(partition_by=[Employee.department], order_by=[Employee.salary.desc()]))
            .order_by("department", "-salary")
            .all()
        )

        # Engineering department (sorted by salary DESC)
        eng_employees = [e for e in employees if e.department == "Engineering"]
        assert eng_employees[0].name == "Alice"
        assert eng_employees[0].dept_rank == 1
        assert eng_employees[1].name == "Charlie"
        assert eng_employees[1].dept_rank == 2
        assert eng_employees[2].name == "Bob"
        assert eng_employees[2].dept_rank == 3

        # Sales department (sorted by salary DESC)
        sales_employees = [e for e in employees if e.department == "Sales"]
        assert sales_employees[0].name == "Eve"
        assert sales_employees[0].dept_rank == 1

    @pytest.mark.usefixtures("sample_employees")
    async def test_dense_rank(self, session):
        """Test DENSE_RANK() function."""
        employees = await (
            Employee.objects.using(session)
            .annotate(dense_rank=func.dense_rank().over(order_by=[Employee.salary.desc()]))
            .order_by("-salary")
            .all()
        )

        assert len(employees) == 6
        # Dense rank should have no gaps
        assert employees[0].dense_rank == 1
        assert employees[1].dense_rank == 2

    @pytest.mark.usefixtures("sample_employees")
    async def test_lag_function(self, session):
        """Test LAG() offset function."""
        employees = await (
            Employee.objects.using(session)
            .annotate(
                prev_salary=func.lag(Employee.salary, 1).over(
                    partition_by=[Employee.department], order_by=[Employee.salary]
                )
            )
            .order_by("department", "salary")
            .all()
        )

        # First employee in each department should have NULL prev_salary
        eng_first = [e for e in employees if e.department == "Engineering"][0]
        assert eng_first.prev_salary is None

        # Second employee should have first employee's salary
        eng_second = [e for e in employees if e.department == "Engineering"][1]
        assert eng_second.prev_salary == eng_first.salary

    @pytest.mark.usefixtures("sample_employees")
    async def test_lead_function(self, session):
        """Test LEAD() offset function."""
        employees = await (
            Employee.objects.using(session)
            .annotate(
                next_salary=func.lead(Employee.salary, 1).over(
                    partition_by=[Employee.department], order_by=[Employee.salary]
                )
            )
            .order_by("department", "salary")
            .all()
        )

        # Last employee in each department should have NULL next_salary
        eng_employees = [e for e in employees if e.department == "Engineering"]
        assert eng_employees[-1].next_salary is None

        # First employee should have second employee's salary
        assert eng_employees[0].next_salary == eng_employees[1].salary

    @pytest.mark.usefixtures("sample_employees")
    async def test_multiple_window_functions(self, session):
        """Test multiple window functions in single query."""
        employees = await (
            Employee.objects.using(session)
            .annotate(
                row_num=func.row_number().over(order_by=[Employee.salary]),
                dept_rank=func.rank().over(partition_by=[Employee.department], order_by=[Employee.salary.desc()]),
                prev_salary=func.lag(Employee.salary, 1, 0).over(order_by=[Employee.salary]),
            )
            .order_by("salary")
            .all()
        )

        assert len(employees) == 6
        # Verify all window functions computed
        for emp in employees:
            assert hasattr(emp, "row_num")
            assert hasattr(emp, "dept_rank")
            assert hasattr(emp, "prev_salary")

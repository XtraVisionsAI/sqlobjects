"""Unit tests for dialect EXPLAIN functionality."""

from sqlobjects.queries.dialect import MySQLDialect, PostgreSQLDialect, SQLiteDialect


class TestDialectExplain:
    """Test EXPLAIN query building and result parsing for different dialects."""

    def test_postgresql_explain_basic(self):
        """Test PostgreSQL basic EXPLAIN query."""
        dialect = PostgreSQLDialect("postgresql")
        sql = "SELECT * FROM users"

        result = dialect.build_explain_query(sql, analyze=False, verbose=False)

        assert result == "EXPLAIN SELECT * FROM users"

    def test_postgresql_explain_with_analyze(self):
        """Test PostgreSQL EXPLAIN with ANALYZE."""
        dialect = PostgreSQLDialect("postgresql")
        sql = "SELECT * FROM users WHERE age > 25"

        result = dialect.build_explain_query(sql, analyze=True, verbose=False)

        assert result == "EXPLAIN (ANALYZE TRUE) SELECT * FROM users WHERE age > 25"

    def test_postgresql_explain_with_verbose(self):
        """Test PostgreSQL EXPLAIN with VERBOSE."""
        dialect = PostgreSQLDialect("postgresql")
        sql = "SELECT * FROM users"

        result = dialect.build_explain_query(sql, analyze=False, verbose=True)

        assert result == "EXPLAIN (VERBOSE TRUE) SELECT * FROM users"

    def test_postgresql_explain_with_both(self):
        """Test PostgreSQL EXPLAIN with ANALYZE and VERBOSE."""
        dialect = PostgreSQLDialect("postgresql")
        sql = "SELECT * FROM users"

        result = dialect.build_explain_query(sql, analyze=True, verbose=True)

        assert result == "EXPLAIN (ANALYZE TRUE, VERBOSE TRUE) SELECT * FROM users"

    def test_postgresql_parse_result(self):
        """Test PostgreSQL EXPLAIN result parsing."""
        dialect = PostgreSQLDialect("postgresql")
        rows = [
            ("Seq Scan on users",),
            ("  Filter: (age > 25)",),
        ]

        result = dialect.parse_explain_result(rows)

        assert result == "Seq Scan on users\n  Filter: (age > 25)"

    def test_mysql_explain_basic(self):
        """Test MySQL basic EXPLAIN query."""
        dialect = MySQLDialect("mysql")
        sql = "SELECT * FROM users"

        result = dialect.build_explain_query(sql, analyze=False, verbose=False)

        assert result == "EXPLAIN SELECT * FROM users"

    def test_mysql_explain_with_analyze(self):
        """Test MySQL EXPLAIN with ANALYZE."""
        dialect = MySQLDialect("mysql")
        sql = "SELECT * FROM users WHERE age > 25"

        result = dialect.build_explain_query(sql, analyze=True, verbose=False)

        assert result == "EXPLAIN ANALYZE SELECT * FROM users WHERE age > 25"

    def test_mysql_parse_result(self):
        """Test MySQL EXPLAIN result parsing."""
        dialect = MySQLDialect("mysql")
        rows = [
            ("1, SIMPLE, users, NULL, ALL, NULL, NULL, NULL, NULL, 100, 33.33, Using where",),
        ]

        result = dialect.parse_explain_result(rows)

        assert "1, SIMPLE, users" in result

    def test_sqlite_explain_basic(self):
        """Test SQLite EXPLAIN query."""
        dialect = SQLiteDialect("sqlite")
        sql = "SELECT * FROM users"

        result = dialect.build_explain_query(sql, analyze=False, verbose=False)

        assert result == "EXPLAIN QUERY PLAN SELECT * FROM users"

    def test_sqlite_explain_ignores_analyze(self):
        """Test SQLite EXPLAIN ignores ANALYZE parameter."""
        dialect = SQLiteDialect("sqlite")
        sql = "SELECT * FROM users"

        # SQLite doesn't support ANALYZE in EXPLAIN
        result = dialect.build_explain_query(sql, analyze=True, verbose=True)

        assert result == "EXPLAIN QUERY PLAN SELECT * FROM users"

    def test_sqlite_parse_result(self):
        """Test SQLite EXPLAIN result parsing."""
        dialect = SQLiteDialect("sqlite")
        # SQLite returns: (id, parent, notused, detail)
        rows = [
            (2, 0, 0, "SCAN users"),
            (3, 2, 0, "USE TEMP B-TREE FOR ORDER BY"),
        ]

        result = dialect.parse_explain_result(rows)

        # Should extract last column (detail)
        assert result == "SCAN users\nUSE TEMP B-TREE FOR ORDER BY"

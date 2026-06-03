"""Tests for `data_eval.scorers.sql` — dialect-correct, identifier-safe check SQL."""

import pytest

from data_eval.scorers import sql
from data_eval.types import Sql

_MODEL = Sql("SELECT email FROM users")


@pytest.mark.unit
class TestWrapModel:
    def test_duckdb_aliases_derived_table(self) -> None:
        assert sql.wrap_model(_MODEL, "count(*)", "duckdb") == "SELECT COUNT(*) FROM (SELECT email FROM users) AS t"

    def test_postgres_aliases_derived_table(self) -> None:
        assert sql.wrap_model(_MODEL, "count(*)", "postgres") == "SELECT COUNT(*) FROM (SELECT email FROM users) AS t"

    def test_quotes_reserved_column_name(self) -> None:
        # A column named after a keyword must be quoted, not emitted bare.
        out = sql.wrap_model(Sql('SELECT "order" FROM t'), '"order"', "postgres")
        assert '"order"' in out


@pytest.mark.unit
class TestCheckBuilders:
    def test_row_count(self) -> None:
        assert sql.row_count(_MODEL, "duckdb") == "SELECT COUNT(*) FROM (SELECT email FROM users) AS t"

    def test_not_null_count(self) -> None:
        out = sql.not_null_count(_MODEL, "email", "postgres")
        assert out == 'SELECT COUNT(*) FROM (SELECT email FROM users) AS t WHERE "email" IS NULL'

    def test_not_null_sample_is_limited(self) -> None:
        out = sql.not_null_sample(_MODEL, "email", "duckdb")
        assert out == 'SELECT * FROM (SELECT email FROM users) AS t WHERE "email" IS NULL LIMIT 20'

    def test_unique_count_excludes_nulls(self) -> None:
        out = sql.unique_count(_MODEL, "email", "duckdb")
        assert 'WHERE NOT "email" IS NULL' in out
        assert "GROUP BY" in out
        assert "HAVING COUNT(*) > 1" in out

    def test_unique_sample_carries_counts_and_limit(self) -> None:
        out = sql.unique_sample(_MODEL, "email", "postgres")
        assert "COUNT(*) AS n" in out
        assert "LIMIT 20" in out

    def test_quoted_identifier_column(self) -> None:
        # A column named `order` is quoted in every clause it appears in.
        out = sql.unique_count(Sql('SELECT "order" FROM t'), "order", "duckdb")
        assert '"order"' in out
        assert " order " not in out

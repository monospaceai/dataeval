"""End-to-end slice test: EvalCase -> CallableSolver -> DuckDB -> ResultSetEquivalence -> assert_eval.

Hermetic and CI-runnable: an in-memory DuckDB seeded with a tiny table, a deterministic
no-LLM solver, and the real scorer. Proves the full chain and the failure-message content.
"""

from collections.abc import Iterator

import pytest

from data_eval import CallableSolver, EvalCase, PlatformRef, ResultSetEquivalence, assert_eval
from data_eval.platforms import DuckDBAdapter
from data_eval.types import ExpectedResultSet

_ROCK_SQL = "SELECT count(*) AS count FROM tracks WHERE genre = 'Rock'"


@pytest.fixture
def duck() -> Iterator[DuckDBAdapter]:
    with DuckDBAdapter() as adapter:
        adapter.execute("CREATE TABLE tracks (id INTEGER, genre VARCHAR)")
        adapter.execute("INSERT INTO tracks VALUES (1, 'Rock'), (2, 'Rock'), (3, 'Jazz')")
        yield adapter


def _case(expected_rows: list[dict[str, object]]) -> EvalCase:
    return EvalCase(
        id="rock-count",
        input="How many tracks are in the 'Rock' genre?",
        expected=ExpectedResultSet(rows=expected_rows),
        platform=PlatformRef(name="local", kind="duckdb"),
    )


@pytest.mark.unit
class TestAssertEvalEndToEnd:
    def test_passes_when_sql_is_correct(self, duck: DuckDBAdapter) -> None:
        case = _case([{"count": 2}])
        solver = CallableSolver(lambda c: _ROCK_SQL)
        assert_eval(case, solver, adapter=duck, scorers=[ResultSetEquivalence()])  # no raise == pass

    def test_fails_with_diff_and_sql_on_wrong_value(self, duck: DuckDBAdapter) -> None:
        case = _case([{"count": 99}])
        solver = CallableSolver(lambda c: _ROCK_SQL)
        with pytest.raises(AssertionError) as exc:
            assert_eval(case, solver, adapter=duck, scorers=[ResultSetEquivalence()])
        msg = str(exc.value)
        assert "rock-count" in msg
        assert _ROCK_SQL in msg  # the generated SQL is surfaced for debugging
        assert "99" in msg  # expected-row sample
        assert "{'count': 2}" in msg  # actual-row sample

    def test_fails_with_execution_error_on_bad_sql(self, duck: DuckDBAdapter) -> None:
        case = _case([{"count": 2}])
        solver = CallableSolver(lambda c: "SELECT * FROM does_not_exist_xyz")
        with pytest.raises(AssertionError) as exc:
            assert_eval(case, solver, adapter=duck, scorers=[ResultSetEquivalence()])
        assert "execution error" in str(exc.value)

    def test_column_alias_mismatch_surfaces_in_diff(self, duck: DuckDBAdapter) -> None:
        # AI aliases the column 'n' but the case expects 'count' -> missing/extra columns
        case = _case([{"count": 2}])
        solver = CallableSolver(lambda c: "SELECT count(*) AS n FROM tracks WHERE genre = 'Rock'")
        with pytest.raises(AssertionError) as exc:
            assert_eval(case, solver, adapter=duck, scorers=[ResultSetEquivalence()])
        msg = str(exc.value)
        assert "missing columns" in msg
        assert "extra columns" in msg

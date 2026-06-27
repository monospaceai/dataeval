"""Tests for `run_benchmark` — the non-raising aggregate over a set of cases."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from evaldata import CallableSolver, EvalCase, ExecutionAccuracy, run_benchmark
from evaldata.platforms import sqlite_platform
from evaldata.platforms.registry import close_all
from evaldata.types import GoldQuery


@pytest.fixture
def db(tmp_path: Path) -> Iterator[str]:
    path = tmp_path / "bench.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE items (id INTEGER)")
    con.executemany("INSERT INTO items VALUES (?)", [(1,), (2,), (3,)])
    con.commit()
    con.close()
    yield str(path)
    close_all()  # drop the per-name adapters this test resolved so names are free again


def _case(case_id: str, db: str) -> EvalCase:
    return EvalCase(
        id=case_id,
        input="q",
        expected=GoldQuery(sql="SELECT id FROM items"),
        platform=sqlite_platform(name=f"bench-{case_id}", path=db),
    )


@pytest.mark.unit
class TestRunBenchmark:
    def test_reports_accuracy(self, db: str) -> None:
        # The "good" case returns all rows; the "bad" case returns a subset and fails.
        solver = CallableSolver(
            lambda c: "SELECT id FROM items" if c.id == "good" else "SELECT id FROM items WHERE id < 2"
        )
        summary = run_benchmark([_case("good", db), _case("bad", db)], solver, scorers=[ExecutionAccuracy()])

        assert summary.total == 2
        assert summary.passed == 1
        assert summary.accuracy == 0.5
        assert [c.id for c in summary.cases] == ["good", "bad"]

    def test_limit_caps_cases_run(self, db: str) -> None:
        solver = CallableSolver(lambda c: "SELECT id FROM items")
        cases = [_case("a", db), _case("b", db), _case("c", db)]
        summary = run_benchmark(cases, solver, scorers=[ExecutionAccuracy()], limit=1)

        assert summary.total == 1
        assert summary.passed == 1

    def test_empty_cases_yield_zero_accuracy(self) -> None:
        solver = CallableSolver(lambda c: "SELECT 1")
        summary = run_benchmark([], solver, scorers=[ExecutionAccuracy()])

        assert summary.total == 0
        assert summary.passed == 0
        assert summary.accuracy == 0.0

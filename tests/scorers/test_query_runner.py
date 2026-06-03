"""Tests for `QueryRunner` — budget-aware derived-query execution."""

import pytest

from data_eval.scorers import QueryRunner
from data_eval.types import ExecutionResult, Sql


class _RecordingAdapter:
    def __init__(self, results: list[ExecutionResult]) -> None:
        self.executed: list[str] = []
        self._results = list(results)

    def execute(self, sql: str) -> ExecutionResult:
        self.executed.append(sql)
        return self._results.pop(0)

    def cancel(self) -> None: ...

    def close(self) -> None: ...


@pytest.mark.unit
class TestQueryRunner:
    def test_success_passes_result_through(self) -> None:
        result = ExecutionResult(rows=[{"n": 1}], latency_seconds=0.5)
        adapter = _RecordingAdapter([result])
        runner = QueryRunner(adapter, Sql("SELECT 1"), None)
        out = runner.run(Sql("SELECT 1"))
        assert out is result
        assert adapter.executed == ["SELECT 1"]

    def test_underlying_error_returned_after_executing(self) -> None:
        result = ExecutionResult(rows=[], latency_seconds=0.0, error="boom")
        adapter = _RecordingAdapter([result])
        runner = QueryRunner(adapter, Sql("SELECT 1"), None)
        out = runner.run(Sql("SELECT bad"))
        assert out.error == "boom"
        assert adapter.executed == ["SELECT bad"]

    def test_pool_decrements_across_calls(self) -> None:
        results = [
            ExecutionResult(rows=[], latency_seconds=2.0),
            ExecutionResult(rows=[], latency_seconds=2.0),
        ]
        adapter = _RecordingAdapter(results)
        runner = QueryRunner(adapter, Sql("SELECT 1"), 5.0)
        runner.run(Sql("SELECT 1"))
        runner.run(Sql("SELECT 2"))
        assert len(adapter.executed) == 2

    def test_exhausted_pool_fails_fast(self) -> None:
        results = [
            ExecutionResult(rows=[], latency_seconds=1.0),
            ExecutionResult(rows=[], latency_seconds=1.0),
        ]
        adapter = _RecordingAdapter(results)
        runner = QueryRunner(adapter, Sql("SELECT 1"), 1.0)
        runner.run(Sql("SELECT 1"))
        out = runner.run(Sql("SELECT 2"))
        assert out.error is not None
        assert "budget" in out.error
        assert len(adapter.executed) == 1

    def test_unbounded_pool_never_short_circuits(self) -> None:
        results = [
            ExecutionResult(rows=[], latency_seconds=10.0),
            ExecutionResult(rows=[], latency_seconds=10.0),
        ]
        adapter = _RecordingAdapter(results)
        runner = QueryRunner(adapter, Sql("SELECT 1"), None)
        runner.run(Sql("SELECT 1"))
        runner.run(Sql("SELECT 2"))
        assert len(adapter.executed) == 2

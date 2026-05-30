"""Tests for ``ResultSetEquivalence`` — the engine-backed v1 scorer."""

import pytest

from data_eval.scorers import ResultSetEquivalence, Scorer
from data_eval.scorers.result_set_equivalence import SCORER_NAME, _dialect_for
from data_eval.types import (
    Column,
    EvalCase,
    ExecutionResult,
    Expected,
    ExpectedResultSet,
    ExpectedSQL,
    PlatformRef,
    SolverOutput,
)

_OUTPUT = SolverOutput(output="SELECT ...")


def _case(expected: Expected) -> EvalCase:
    return EvalCase(
        id="c",
        input="q",
        expected=expected,
        platform=PlatformRef(name="x", kind="duckdb"),
    )


@pytest.mark.unit
class TestResultSetEquivalence:
    def test_passes_on_match_untyped(self) -> None:
        case = _case(ExpectedResultSet(rows=[{"count": 1297}]))
        result = ExecutionResult(
            rows=[{"count": 1297}],
            schema=[Column(name="count", type="BIGINT")],
            latency_seconds=0.0,
        )
        score = ResultSetEquivalence().score(case, _OUTPUT, result)
        assert score.scorer == SCORER_NAME
        assert score.passed is True
        assert score.diff is None

    def test_fails_on_value_mismatch_and_carries_samples(self) -> None:
        case = _case(ExpectedResultSet(rows=[{"count": 1297}]))
        result = ExecutionResult(rows=[{"count": 1298}], latency_seconds=0.0)
        score = ResultSetEquivalence().score(case, _OUTPUT, result)
        assert score.passed is False
        assert score.diff is not None
        assert score.diff.sample_missing_rows == [{"count": 1297}]
        assert score.diff.sample_extra_rows == [{"count": 1298}]

    def test_execution_error_fails_with_explanation(self) -> None:
        case = _case(ExpectedResultSet(rows=[{"count": 1297}]))
        result = ExecutionResult(rows=[], latency_seconds=0.0, error="relation does not exist")
        score = ResultSetEquivalence().score(case, _OUTPUT, result)
        assert score.passed is False
        assert score.diff is None
        assert score.explanation is not None
        assert "relation does not exist" in score.explanation

    def test_typed_path_detects_type_mismatch(self) -> None:
        # expected carries a schema -> typed path -> semantic type comparison via dialect
        case = _case(ExpectedResultSet(rows=[{"n": 1}], schema=[Column(name="n", type="INTEGER")]))
        result = ExecutionResult(rows=[{"n": 1}], schema=[Column(name="n", type="BIGINT")], latency_seconds=0.0)
        score = ResultSetEquivalence().score(case, _OUTPUT, result)
        assert score.passed is False
        assert score.diff is not None
        assert len(score.diff.type_mismatches) == 1
        assert score.diff.type_mismatches[0].column == "n"

    def test_typed_path_treats_aliased_types_as_equal(self) -> None:
        # INT8 and BIGINT are the same duckdb type -> equivalent on the typed path
        case = _case(ExpectedResultSet(rows=[{"n": 1}], schema=[Column(name="n", type="INT8")]))
        result = ExecutionResult(rows=[{"n": 1}], schema=[Column(name="n", type="BIGINT")], latency_seconds=0.0)
        score = ResultSetEquivalence().score(case, _OUTPUT, result)
        assert score.passed is True

    def test_raises_on_non_result_set_expected(self) -> None:
        case = _case(ExpectedSQL(sql="SELECT 1"))
        result = ExecutionResult(rows=[{"n": 1}], latency_seconds=0.0)
        with pytest.raises(TypeError, match="ExpectedResultSet"):
            ResultSetEquivalence().score(case, _OUTPUT, result)

    def test_satisfies_scorer_protocol(self) -> None:
        assert isinstance(ResultSetEquivalence(), Scorer)


@pytest.mark.unit
class TestDialectResolution:
    def test_infers_dialect_from_kind(self) -> None:
        assert _dialect_for(PlatformRef(name="x", kind="postgres")) == "postgres"

    def test_explicit_dialect_overrides_kind(self) -> None:
        assert _dialect_for(PlatformRef(name="x", kind="duckdb", dialect="databricks")) == "databricks"

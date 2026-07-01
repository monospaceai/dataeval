"""Tests for MetricFlow canonicalisation and the `MetricSpecEquivalence` scorer.

Canonicalisation resolves a metric query against the committed semantic manifest; it needs the
`dbt-metricflow` toolchain (installed via the `dbt-sl` extra) but touches no warehouse.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaldata.dbt import DbtError, MetricSpecEquivalence, canonicalize
from evaldata.dbt.metric_spec_equivalence import TARGET_DIR_KEY
from evaldata.dbt.metricflow import CanonicalMetricQuery, _spec_key
from evaldata.scorers import QueryRunner, ScoreContext
from evaldata.types import (
    EvalCase,
    ExecutionResult,
    GoldMetricQuery,
    GoldQuery,
    MetricQuery,
    PlatformRef,
    ScoreResult,
    SolverOutput,
    Sql,
)

pytestmark = pytest.mark.unit

TARGET = Path(__file__).parent / "fixtures" / "jaffle_duckdb" / "artifacts"
PLATFORM = PlatformRef(name="duck", kind="duckdb")
_RESULT = ExecutionResult(rows=[], latency_seconds=0.0)


class _NullAdapter:
    """An adapter that is never executed — spec equivalence touches no warehouse."""

    def execute(self, sql: str) -> ExecutionResult:  # pragma: no cover - never called
        msg = "MetricSpecEquivalence must not execute SQL"
        raise AssertionError(msg)

    def cancel(self) -> None: ...

    def close(self) -> None: ...


def _context() -> ScoreContext:
    return ScoreContext(queries=QueryRunner(_NullAdapter(), Sql("select 1"), "duckdb", None))


def _case(gold: MetricQuery, *, target: Path | None = TARGET) -> EvalCase:
    metadata = {} if target is None else {TARGET_DIR_KEY: str(target)}
    return EvalCase(id="c", input="q", expected=GoldMetricQuery(query=gold), platform=PLATFORM, metadata=metadata)


def _score(case: EvalCase, output: SolverOutput) -> ScoreResult:
    return MetricSpecEquivalence().score(case, output, _RESULT, context=_context())


def test_canonicalize_resolves_default_grain() -> None:
    # `metric_time` resolves to the metric's default grain (day), so these are the same query.
    a = canonicalize(MetricQuery(metrics=["revenue"], group_by=["metric_time"]), TARGET)
    b = canonicalize(MetricQuery(metrics=["revenue"], group_by=["metric_time__day"]), TARGET)
    assert isinstance(a, CanonicalMetricQuery)
    assert a == b


def test_canonicalize_captures_where_order_and_limit() -> None:
    where = "{{ Dimension('order_id__is_large_order') }} = true"
    resolved = canonicalize(
        MetricQuery(
            metrics=["revenue"],
            group_by=["metric_time__month"],
            where=[where],
            order_by=["-metric_time__month"],
            limit=5,
        ),
        TARGET,
    )
    assert isinstance(resolved, CanonicalMetricQuery)
    assert resolved.metrics == frozenset({"revenue"})
    assert resolved.limit == 5
    assert resolved.where == frozenset({where})
    assert len(resolved.order_by) == 1
    assert resolved.order_by[0][1] is True  # descending


def test_canonicalize_missing_manifest(tmp_path: Path) -> None:
    result = canonicalize(MetricQuery(metrics=["revenue"]), tmp_path)
    assert isinstance(result, DbtError)
    assert result.kind == "target_not_found"


def test_canonicalize_invalid_query() -> None:
    result = canonicalize(MetricQuery(metrics=["does_not_exist"]), TARGET)
    assert isinstance(result, DbtError)
    assert result.kind == "metric_query_invalid"


def test_canonicalize_without_metricflow(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (
        "metricflow_semantics.model.dbt_manifest_parser",
        "metricflow_semantics.model.semantic_manifest_lookup",
        "metricflow_semantics.query.query_parser",
    ):
        monkeypatch.setitem(sys.modules, module, None)
    result = canonicalize(MetricQuery(metrics=["revenue"]), TARGET)
    assert isinstance(result, DbtError)
    assert result.kind == "metricflow_unavailable"


def test_spec_key_includes_grain_and_date_part() -> None:
    spec = SimpleNamespace(
        element_name="ds",
        entity_links=(SimpleNamespace(element_name="order_id"),),
        time_granularity=SimpleNamespace(name="month"),
        date_part=SimpleNamespace(value="year"),
    )
    assert _spec_key(spec) == ("SimpleNamespace", "ds", ("order_id",), "month", "year")


def test_scorer_confirms_equivalent_queries() -> None:
    case = _case(MetricQuery(metrics=["revenue"], group_by=["metric_time"]))
    output = SolverOutput(query=MetricQuery(metrics=["revenue"], group_by=["metric_time__day"]))
    score = _score(case, output)
    assert score.verdict == "pass"
    assert score.basis == "proven"


def test_scorer_is_inconclusive_for_different_queries() -> None:
    case = _case(MetricQuery(metrics=["revenue"], group_by=["metric_time"]))
    output = SolverOutput(query=MetricQuery(metrics=["order_count"], group_by=["metric_time"]))
    score = _score(case, output)
    assert score.verdict == "inconclusive"


def test_scorer_is_inconclusive_when_model_query_is_invalid() -> None:
    case = _case(MetricQuery(metrics=["revenue"]))
    output = SolverOutput(query=MetricQuery(metrics=["does_not_exist"]))
    score = _score(case, output)
    assert score.verdict == "inconclusive"
    assert score.explanation is not None
    assert score.explanation.startswith("model query:")


def test_scorer_is_inconclusive_when_gold_query_is_invalid() -> None:
    case = _case(MetricQuery(metrics=["does_not_exist"]))
    output = SolverOutput(query=MetricQuery(metrics=["revenue"]))
    score = _score(case, output)
    assert score.verdict == "inconclusive"
    assert score.explanation is not None
    assert score.explanation.startswith("gold query:")


def test_scorer_is_inconclusive_without_target_dir() -> None:
    case = _case(MetricQuery(metrics=["revenue"]), target=None)
    output = SolverOutput(query=MetricQuery(metrics=["revenue"]))
    score = _score(case, output)
    assert score.verdict == "inconclusive"


def test_scorer_rejects_non_metric_gold() -> None:
    case = EvalCase(id="c", input="q", expected=GoldQuery(sql="select 1"), platform=PLATFORM)
    output = SolverOutput(query=MetricQuery(metrics=["revenue"]))
    with pytest.raises(TypeError):
        _score(case, output)


def test_scorer_rejects_output_without_metric_query() -> None:
    case = _case(MetricQuery(metrics=["revenue"]))
    output = SolverOutput(output="select 1")
    with pytest.raises(TypeError):
        _score(case, output)

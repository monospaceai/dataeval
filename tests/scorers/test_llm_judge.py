"""Tests for `LlmJudge` — the LLM-as-judge scorer, driven through a `StubLlm`.

The judge talks only to the `Llm` seam, so its unit tests inject a `StubLlm` (no litellm, no
network). The litellm backend itself is covered in `tests/llm/test_lite.py`.
"""

import os

import pytest

from evaldata.llm import StubLlm
from evaldata.scorers import QueryRunner, ScoreContext, Scorer
from evaldata.scorers.llm_judge import SCORER_NAME, JudgeReply, LlmJudge
from evaldata.scorers.sql import Dialect
from evaldata.types import (
    EvalCase,
    ExecutionResult,
    Expected,
    GoldQuery,
    LlmError,
    PlatformRef,
    SolverOutput,
    Sql,
    UntypedResultSet,
)

_OUTPUT = SolverOutput(output="SELECT 1")
_RESULT = ExecutionResult(rows=[], latency_seconds=0.0)


class _NullAdapter:
    """An adapter that is never executed — the judge compares text, touching no warehouse."""

    def execute(self, sql: str) -> ExecutionResult:  # pragma: no cover - never called
        msg = "LlmJudge must not execute SQL"
        raise AssertionError(msg)

    def cancel(self) -> None: ...

    def close(self) -> None: ...


def _context(model: str = "SELECT 1 AS n", dialect: Dialect = "duckdb") -> ScoreContext:
    return ScoreContext(queries=QueryRunner(_NullAdapter(), Sql(model), dialect, None))


def _case(expected: Expected | None = None) -> EvalCase:
    return EvalCase(
        id="c",
        input="How many tracks?",
        expected=expected if expected is not None else UntypedResultSet(rows=[]),
        platform=PlatformRef(name="x", kind="duckdb"),
    )


@pytest.mark.unit
class TestLlmJudge:
    def test_score_at_or_above_threshold_passes(self) -> None:
        stub = StubLlm(JudgeReply(score=0.9, reason="great"))
        result = LlmJudge(model=stub, criteria="is it correct?").score(_case(), _OUTPUT, _RESULT, context=_context())
        assert result.verdict == "pass"
        assert result.score == pytest.approx(0.9)
        assert result.explanation == "great"

    def test_score_below_threshold_fails(self) -> None:
        stub = StubLlm(JudgeReply(score=0.2, reason="off"))
        result = LlmJudge(model=stub, criteria="c").score(_case(), _OUTPUT, _RESULT, context=_context())
        assert result.verdict == "fail"
        assert result.score == pytest.approx(0.2)

    def test_malformed_output_is_inconclusive(self) -> None:
        err = LlmError(kind="malformed_output", message="grader returned malformed output")
        result = LlmJudge(model=StubLlm(err), criteria="c").score(_case(), _OUTPUT, _RESULT, context=_context())
        assert result.verdict == "inconclusive"
        assert result.score is None
        assert "grader call failed" in (result.explanation or "")
        assert result.metadata["error"]["kind"] == "malformed_output"

    def test_provider_error_is_inconclusive_with_metadata(self) -> None:
        err = LlmError(kind="api_error", message="boom", provider="openai")
        result = LlmJudge(model=StubLlm(err), criteria="c").score(_case(), _OUTPUT, _RESULT, context=_context())
        assert result.verdict == "inconclusive"
        assert result.score is None
        assert "grader call failed" in (result.explanation or "")
        assert result.metadata["error"]["kind"] == "api_error"
        assert "boom" in result.metadata["error"]["message"]

    def test_score_above_one_clamped(self) -> None:
        stub = StubLlm(JudgeReply(score=1.7, reason="r"))
        result = LlmJudge(model=stub, criteria="c").score(_case(), _OUTPUT, _RESULT, context=_context())
        assert result.verdict == "pass"
        assert result.score == pytest.approx(1.0)

    def test_score_below_zero_clamped(self) -> None:
        stub = StubLlm(JudgeReply(score=-0.2, reason="r"))
        result = LlmJudge(model=stub, criteria="c").score(_case(), _OUTPUT, _RESULT, context=_context())
        assert result.verdict == "fail"
        assert result.score == pytest.approx(0.0)

    def test_empty_reason_is_no_explanation(self) -> None:
        stub = StubLlm(JudgeReply(score=0.9, reason=""))
        result = LlmJudge(model=stub, criteria="c").score(_case(), _OUTPUT, _RESULT, context=_context())
        assert result.verdict == "pass"
        assert result.explanation is None

    def test_metadata_carries_source_and_grader_model(self) -> None:
        stub = StubLlm(JudgeReply(score=0.9, reason="r"))
        result = LlmJudge(model=stub, criteria="c").score(_case(), _OUTPUT, _RESULT, context=_context())
        assert result.metadata["source"] == "llm_judge"
        assert result.metadata["grader_model"] == "StubLlm"

    def test_grader_model_string_recorded(self) -> None:
        result = LlmJudge(model="my-grader", criteria="c")
        assert result._model == "my-grader"

    def test_threshold_boundary_passes(self) -> None:
        stub = StubLlm(JudgeReply(score=0.5, reason="r"))
        result = LlmJudge(model=stub, criteria="c", threshold=0.5).score(_case(), _OUTPUT, _RESULT, context=_context())
        assert result.verdict == "pass"

    def test_prompt_carries_criteria_question_and_model_sql(self) -> None:
        stub = StubLlm(JudgeReply(score=0.9, reason="r"))
        LlmJudge(model=stub, criteria="the answer must be exact").score(
            _case(), _OUTPUT, _RESULT, context=_context(model="SELECT count(*) FROM tracks")
        )
        prompt = stub.prompts[-1]
        assert "the answer must be exact" in prompt
        assert "How many tracks?" in prompt
        assert "SELECT count(*) FROM tracks" in prompt

    def test_gold_query_included_only_for_gold_query_expected(self) -> None:
        stub = StubLlm(JudgeReply(score=0.9, reason="r"))
        LlmJudge(model=stub, criteria="c").score(
            _case(GoldQuery(sql="SELECT 42 AS gold")), _OUTPUT, _RESULT, context=_context()
        )
        assert "SELECT 42 AS gold" in stub.prompts[-1]

    def test_gold_query_absent_for_non_gold_expected(self) -> None:
        stub = StubLlm(JudgeReply(score=0.9, reason="r"))
        LlmJudge(model=stub, criteria="c").score(
            _case(UntypedResultSet(rows=[{"n": 1}])), _OUTPUT, _RESULT, context=_context()
        )
        assert "Reference SQL" not in stub.prompts[-1]

    def test_show_limits_fields(self) -> None:
        stub = StubLlm(JudgeReply(score=0.9, reason="r"))
        LlmJudge(model=stub, criteria="c", show=["question"]).score(
            _case(), _OUTPUT, _RESULT, context=_context(model="SELECT secret")
        )
        prompt = stub.prompts[-1]
        assert "How many tracks?" in prompt
        assert "SELECT secret" not in prompt

    def test_scorer_name(self) -> None:
        stub = StubLlm(JudgeReply(score=0.9, reason="r"))
        result = LlmJudge(model=stub, criteria="c").score(_case(), _OUTPUT, _RESULT, context=_context())
        assert result.scorer == SCORER_NAME

    def test_satisfies_scorer_protocol(self) -> None:
        assert isinstance(LlmJudge(model=StubLlm(JudgeReply(score=0.9, reason="r")), criteria="c"), Scorer)


@pytest.mark.e2e
@pytest.mark.skipif(
    os.environ.get("OPENAI_API_KEY") is None,
    reason="set OPENAI_API_KEY to run live grader e2e",
)
def test_live_llm_judge_smoke() -> None:
    judge = LlmJudge(
        model="openai/gpt-4o-mini",
        criteria="The query must return a single integer column named n equal to 1.",
    )
    context = ScoreContext(queries=QueryRunner(_NullAdapter(), Sql("SELECT 1 AS n"), "duckdb", None))
    result = judge.score(_case(), _OUTPUT, _RESULT, context=context)
    assert result.verdict in {"pass", "fail"}
    assert result.score is not None

"""The data-free equivalence composition: `FirstDecisive([SemanticEquivalence(), LlmJudge(...)])`.

AST confirms equivalence without running a query; when it cannot, the judge decides. The
composition executes no SQL, so the adapter must never be called.
"""

import pytest

from evaldata.llm import StubLlm
from evaldata.scorers import FirstDecisive, QueryRunner, ScoreContext
from evaldata.scorers.llm_judge import JudgeReply, LlmJudge
from evaldata.scorers.semantic_equivalence import SemanticEquivalence
from evaldata.scorers.sql import Dialect
from evaldata.types import (
    EvalCase,
    ExecutionResult,
    GoldQuery,
    PlatformRef,
    SolverOutput,
    Sql,
)

_OUTPUT = SolverOutput(output="SELECT 1")
_RESULT = ExecutionResult(rows=[], latency_seconds=0.0)


class _NullAdapter:
    """An adapter that is never executed — the data-free composition touches no warehouse."""

    def execute(self, sql: str) -> ExecutionResult:  # pragma: no cover - never called
        msg = "must not execute SQL"
        raise AssertionError(msg)

    def cancel(self) -> None: ...

    def close(self) -> None: ...


def _context(model: str, dialect: Dialect = "duckdb") -> ScoreContext:
    return ScoreContext(queries=QueryRunner(_NullAdapter(), Sql(model), dialect, None))


def _gold_case(gold_sql: str) -> EvalCase:
    return EvalCase(id="c", input="q", expected=GoldQuery(sql=gold_sql), platform=PlatformRef(name="x", kind="duckdb"))


def _trail(score) -> list[str]:
    return [entry["scorer"] for entry in score.metadata["first_decisive"]]


@pytest.mark.unit
class TestJudgeEquivalence:
    def test_ast_confirms_and_judge_not_consulted(self) -> None:
        judge = LlmJudge(model=StubLlm(JudgeReply(score=0.0, reason="never asked")), criteria="c")
        composition = FirstDecisive([SemanticEquivalence(), judge])
        case = _gold_case("SELECT name FROM t WHERE country = 'US' AND id > 1")
        model = "select NAME from t where id > 1 and country = 'US'"
        score = composition.score(case, _OUTPUT, _RESULT, context=_context(model))
        assert score.passed is True
        assert score.basis == "proven"
        assert _trail(score) == ["semantic_equivalence"]
        assert judge._llm.prompts == []

    def test_ast_inconclusive_then_judge_passes(self) -> None:
        judge = LlmJudge(model=StubLlm(JudgeReply(score=0.9, reason="equivalent enough")), criteria="c")
        composition = FirstDecisive([SemanticEquivalence(), judge])
        case = _gold_case("SELECT 2 AS n")
        score = composition.score(case, _OUTPUT, _RESULT, context=_context("SELECT 1 AS n"))
        assert score.verdict == "pass"
        assert score.basis == "judged"
        assert _trail(score) == ["semantic_equivalence", "llm_judge"]

    def test_ast_inconclusive_then_judge_fails(self) -> None:
        judge = LlmJudge(model=StubLlm(JudgeReply(score=0.1, reason="different")), criteria="c")
        composition = FirstDecisive([SemanticEquivalence(), judge])
        case = _gold_case("SELECT 2 AS n")
        score = composition.score(case, _OUTPUT, _RESULT, context=_context("SELECT 1 AS n"))
        assert score.verdict == "fail"
        assert _trail(score) == ["semantic_equivalence", "llm_judge"]

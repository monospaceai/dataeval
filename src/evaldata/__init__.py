"""evaldata — AI evals framework for data and analytics engineering teams."""

from typing import TYPE_CHECKING, Any

from evaldata.core import BenchmarkSummary, assert_eval, run_benchmark
from evaldata.llm import Llm
from evaldata.loaders import eval_case, load_bird, load_spider
from evaldata.scorers import (
    JUDGE_INSTRUCTION,
    ExecutionAccuracy,
    ExpectationSuiteScorer,
    FirstDecisive,
    JudgeExample,
    LlmJudge,
    ResultSetEquivalence,
    RubricBand,
    SemanticEquivalence,
    judged_equivalence,
    observed_equivalence,
    sql_equivalence_judge,
)
from evaldata.solvers import SCHEMA_PROMPT_TEMPLATE, CallableSolver, MetricLayerSolver, PromptSolver
from evaldata.types import EvalCase, PlatformRef

if TYPE_CHECKING:
    from evaldata.llm import LiteLlm

__all__ = [
    "JUDGE_INSTRUCTION",
    "SCHEMA_PROMPT_TEMPLATE",
    "BenchmarkSummary",
    "CallableSolver",
    "EvalCase",
    "ExecutionAccuracy",
    "ExpectationSuiteScorer",
    "FirstDecisive",
    "JudgeExample",
    "LiteLlm",
    "Llm",
    "LlmJudge",
    "MetricLayerSolver",
    "PlatformRef",
    "PromptSolver",
    "ResultSetEquivalence",
    "RubricBand",
    "SemanticEquivalence",
    "assert_eval",
    "eval_case",
    "judged_equivalence",
    "load_bird",
    "load_spider",
    "observed_equivalence",
    "run_benchmark",
    "sql_equivalence_judge",
]


def __getattr__(name: str) -> Any:
    if name == "LiteLlm":
        from evaldata.llm import LiteLlm

        return LiteLlm
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    return sorted([*globals(), "LiteLlm"])

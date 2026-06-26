"""`LlmJudge`: a probabilistic LLM-as-judge `Scorer` over the `Llm` seam.

A grader model scores the case against authored criteria; its 0-1 score maps to a pass/fail
verdict, or an inconclusive result when no verdict can be reached.
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from evaldata.llm import Llm, resolve_llm
from evaldata.scorers.context import ScoreContext
from evaldata.types import EvalCase, ExecutionResult, GoldQuery, LlmError, ScoreResult, SolverOutput

SCORER_NAME = "llm_judge"

# A case field shown to the grader: the question, the candidate SQL, or the gold query.
JudgeField = Literal["question", "model_sql", "gold_query"]

_ALL_FIELDS: tuple[JudgeField, ...] = ("question", "model_sql", "gold_query")

_INSTRUCTION = (
    "You are grading a candidate SQL query against the criteria below. Judge how well it meets "
    "them and return JSON with a `score` between 0.0 (fails the criteria) and 1.0 (fully meets "
    "them) and a short `reason` explaining the score."
)


class JudgeReply(BaseModel):
    """Structured grader reply: a 0-1 correctness score and its rationale."""

    score: float
    reason: str


class LlmJudge:
    """LLM-as-judge `Scorer`: a grader model scores the case against authored criteria.

    The grader's 0-1 score is compared to a threshold for the pass/fail verdict; the score and
    rationale are recorded. A provider failure or a malformed reply yields an inconclusive
    result.
    """

    def __init__(
        self,
        *,
        model: str | Llm,
        criteria: str,
        threshold: float = 0.5,
        temperature: float | None = 0.0,
        timeout: float | None = None,
        show: Sequence[JudgeField] | None = None,
    ) -> None:
        """Configure the judge.

        Args:
            model: A litellm grader-model identifier (separate from any solver model), or an
                `Llm` to use directly. `temperature` and `timeout` apply only to the
                model-string path.
            criteria: The natural-language standard the grader scores the case against.
            threshold: The minimum score (inclusive) for a passing verdict. Defaults to `0.5`.
            temperature: Sampling temperature; `None` leaves the provider default. Defaults to
                `0.0` for deterministic grading.
            timeout: Per-request timeout in seconds.
            show: The case fields to offer the grader, each included only when available.
                Defaults to all of `question`, `model_sql`, and `gold_query`.
        """
        self._llm = resolve_llm(model, temperature=temperature, timeout=timeout)
        self._model = model if isinstance(model, str) else type(model).__name__
        self._criteria = criteria
        self._threshold = threshold
        self._show = tuple(show) if show is not None else _ALL_FIELDS

    def score(
        self, case: EvalCase, output: SolverOutput, result: ExecutionResult, *, context: ScoreContext
    ) -> ScoreResult:
        """Grade `case` with the grader model and return a graded `ScoreResult`.

        Builds a prompt from the criteria and the selected available fields, calls the grader,
        and maps its score to a verdict against the threshold.

        Args:
            case: The eval case, supplying the question and (optionally) the gold query.
            output: The solver output (part of the `Scorer` protocol; unused here).
            result: The executed model result (part of the `Scorer` protocol; unused here).
            context: The score context, supplying the model's SQL.

        Returns:
            A `ScoreResult` whose verdict is pass or fail with the graded score and rationale,
            or inconclusive when no verdict could be reached.
        """
        prompt = self._build_prompt(case, context)
        metadata: dict = {"source": "llm_judge", "grader_model": self._model}

        completion = self._llm.complete(prompt, response_format=JudgeReply)
        if isinstance(completion, LlmError):
            return ScoreResult(
                scorer=SCORER_NAME,
                verdict="inconclusive",
                explanation=f"grader call failed: {completion.message}",
                metadata={**metadata, "error": {"kind": completion.kind, "message": completion.message}},
            )

        clamped = min(1.0, max(0.0, completion.parsed.score))
        verdict = "pass" if clamped >= self._threshold else "fail"
        return ScoreResult(
            scorer=SCORER_NAME,
            verdict=verdict,
            score=clamped,
            basis="judged",
            explanation=completion.parsed.reason or None,
            metadata=metadata,
        )

    def _build_prompt(self, case: EvalCase, context: ScoreContext) -> str:
        """Render the grader prompt from the criteria and the selected available fields.

        Args:
            case: The eval case, supplying the question and (optionally) the gold query.
            context: The score context, supplying the model's SQL.

        Returns:
            The grader prompt: the instruction, the criteria, each available selected field,
            and the JSON-output request.
        """
        parts = [_INSTRUCTION, f"Criteria:\n{self._criteria}"]
        if "question" in self._show:
            parts.append(f"Question:\n{case.input}")
        if "model_sql" in self._show:
            parts.append(f"Candidate SQL:\n{context.queries.model_sql}")
        if "gold_query" in self._show and isinstance(case.expected, GoldQuery):
            parts.append(f"Reference SQL:\n{case.expected.sql}")
        parts.append("Return JSON with a `score` between 0.0 and 1.0 and a `reason`.")
        return "\n\n".join(parts)

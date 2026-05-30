"""Eval orchestration and the pytest-facing assertion.

``assert_eval`` chains the slice end-to-end: the Solver produces SQL, the platform
adapter executes it, each Scorer compares the result, and any failure is raised as an
``AssertionError`` carrying a readable diagnostic. The library stays errors-as-values
throughout (``ExecutionResult.error``, ``ScoreResult.passed``); only this thin wrapper
raises, because raising *is* pytest's failure protocol.

Adapter resolution (slice one): the live ``PlatformAdapter`` is passed in explicitly —
typically from a pytest fixture that owns its connection lifecycle. The case's
``PlatformRef`` stays declarative metadata. The upgrade path (when a loader lands) is
GE-style: add ``resolve(PlatformRef) -> PlatformAdapter`` as a fallback and make
``adapter`` optional, with an explicitly passed adapter always winning.

Message composition follows prevailing practice (GE/DeepEval/Inspect): the originating
input/SQL is *not* stored on ``ScoreResult`` — it is composed here from the case, the
solver output, and the execution result, alongside the structured diff.
"""

from collections.abc import Sequence

from data_eval.platforms.base import PlatformAdapter
from data_eval.scorers.base import Scorer
from data_eval.solvers.base import Solver
from data_eval.types import EvalCase, ExecutionResult, ResultSetDiff, ScoreResult, SolverOutput


def assert_eval(
    case: EvalCase,
    solver: Solver,
    *,
    adapter: PlatformAdapter,
    scorers: Sequence[Scorer],
) -> None:
    """Run ``case`` through ``solver`` + ``adapter`` + ``scorers``; raise on any failure.

    Solves the case, executes the produced SQL against ``adapter``, scores the result
    with each scorer, and raises ``AssertionError`` with a composed diagnostic if any
    scorer fails. Returns ``None`` on success (pytest-friendly).
    """
    output = solver.solve(case)
    result = adapter.execute(output.output)
    scores = [scorer.score(case, output, result) for scorer in scorers]
    failures = [s for s in scores if not s.passed]
    if failures:
        raise AssertionError(_format_failure(case, output, result, failures))


def _format_failure(
    case: EvalCase,
    output: SolverOutput,
    result: ExecutionResult,
    failures: Sequence[ScoreResult],
) -> str:
    """Compose a readable failure message from the case, the SQL, and the failing scores."""
    lines = [
        f"data-eval case {case.id!r} failed",
        f"  input: {case.input}",
        f"  sql:   {output.output}",
    ]
    if result.error is not None:
        lines.append(f"  execution error: {result.error}")
    for score in failures:
        lines.append(f"  scorer {score.scorer!r}: FAIL")
        if score.explanation:
            lines.append(f"    {score.explanation}")
        if score.diff is not None:
            lines.extend(_format_diff(score.diff))
    return "\n".join(lines)


def _format_diff(diff: ResultSetDiff) -> list[str]:
    """Render a ``ResultSetDiff`` as indented diagnostic lines (counts + concrete samples)."""
    lines = [f"    rows: expected {diff.expected_row_count}, got {diff.actual_row_count}"]
    if diff.missing_columns:
        lines.append(f"    missing columns: {diff.missing_columns}")
    if diff.extra_columns:
        lines.append(f"    extra columns: {diff.extra_columns}")
    if diff.column_order_mismatch:
        lines.append("    column order differs")
    for tm in diff.type_mismatches:
        lines.append(f"    type mismatch on {tm.column!r}: expected {tm.expected}, got {tm.actual}")
    if diff.missing_row_count:
        lines.append(f"    missing rows ({diff.missing_row_count}); sample: {diff.sample_missing_rows}")
    if diff.extra_row_count:
        lines.append(f"    extra rows ({diff.extra_row_count}); sample: {diff.sample_extra_rows}")
    return lines

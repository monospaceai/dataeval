"""Eval orchestration and the pytest-facing assertion.

``assert_eval`` chains the slice end-to-end: the Solver produces SQL, the platform
adapter executes it, each Scorer compares the result, and any failure is raised as an
``AssertionError`` carrying a readable diagnostic. The library stays errors-as-values
throughout (``ExecutionResult.error``, ``ScoreResult.passed``); only this thin wrapper
raises, because raising *is* pytest's failure protocol.

Adapter resolution (GE-style dual rule): an explicitly passed ``adapter`` always wins —
typically a pytest fixture that owns its own connection lifecycle. When ``adapter`` is
omitted, the live adapter is resolved from the case's ``PlatformRef`` via
``platforms.registry.resolve``, which caches it session-globally and closes it at session
end (the pytest plugin's ``pytest_sessionfinish`` hook). So ``assert_eval`` never closes a
resolved adapter mid-run — reuse across cases is the point — and never closes a
caller-supplied one (the caller owns it).

Message composition follows prevailing practice (GE/DeepEval/Inspect): the originating
input/SQL is *not* stored on ``ScoreResult`` — it is composed here from the case, the
solver output, and the execution result, alongside the structured diff.
"""

from collections.abc import Sequence

from data_eval.platforms.base import PlatformAdapter
from data_eval.platforms.registry import resolve
from data_eval.scorers.base import Scorer
from data_eval.solvers.base import Solver
from data_eval.types import EvalCase, ExecutionResult, ResultSetDiff, ScoreResult, SolverError, SolverOutput


def assert_eval(
    case: EvalCase,
    solver: Solver,
    *,
    scorers: Sequence[Scorer],
    adapter: PlatformAdapter | None = None,
) -> None:
    """Run ``case`` through ``solver`` + a platform adapter + ``scorers``; raise on any failure.

    Solves the case, executes the produced SQL, scores the result with each scorer, and
    raises ``AssertionError`` with a composed diagnostic if any scorer fails. The adapter is
    the explicitly passed ``adapter`` if given, otherwise resolved (and session-cached) from
    ``case.platform``. Returns ``None`` on success (pytest-friendly).
    """
    output = solver.solve(case)
    if output.error is not None:
        raise AssertionError(_format_solver_error(case, output.error))
    sql = output.output
    if sql is None:  # invariant: error is None implies output is set (SolverOutput validator)
        raise AssertionError(f"data-eval case {case.id!r}: solver returned neither output nor error")
    live = adapter if adapter is not None else resolve(case.platform)
    result = live.execute(sql)
    scores = [scorer.score(case, output, result) for scorer in scorers]
    failures = [s for s in scores if not s.passed]
    if failures:
        raise AssertionError(_format_failure(case, output, result, failures))


def _format_solver_error(case: EvalCase, error: SolverError) -> str:
    """Compose a readable message for a solver failure (no SQL was executed)."""
    return "\n".join(
        [
            f"data-eval case {case.id!r} failed: solver error",
            f"  input: {case.input}",
            f"  solver error [{error.kind}]: {error.message}",
        ]
    )


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

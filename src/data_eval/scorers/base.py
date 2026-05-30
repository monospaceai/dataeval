"""``Scorer`` Protocol: pluggable pass/fail check over an executed result.

A Scorer turns ``(EvalCase, SolverOutput, ExecutionResult)`` into a ``ScoreResult``.
It runs *after* the platform has executed the solver's SQL, so it does no I/O and
sees only the already-fetched ``ExecutionResult`` — keeping scoring pure, local
(PII-safe), and unit-testable. v1 ships one: ``ResultSetEquivalence``.

A Protocol (not an ABC), matching ``PlatformAdapter`` / ``Solver``.
"""

from typing import Protocol, runtime_checkable

from data_eval.types import EvalCase, ExecutionResult, ScoreResult, SolverOutput


@runtime_checkable
class Scorer(Protocol):
    """Produces a ``ScoreResult`` from a case, its solver output, and the execution result."""

    def score(self, case: EvalCase, output: SolverOutput, result: ExecutionResult) -> ScoreResult:
        """Decide pass/fail with diagnostics for ``case`` given ``output`` and ``result``."""
        ...

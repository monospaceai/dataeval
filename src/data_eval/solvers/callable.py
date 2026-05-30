"""``CallableSolver``: adapt a plain function into a ``Solver``.

The hermetic, no-LLM entry point: wrap any ``Callable[[EvalCase], str]`` that returns
the SQL to execute. Keeps the first end-to-end loop deterministic and CI-runnable (no
API key). Solvers that need to report tokens/cost/latency, or that emit richer output,
implement the ``Solver`` Protocol directly rather than going through this wrapper.
"""

from collections.abc import Callable

from data_eval.types import EvalCase, SolverOutput


class CallableSolver:
    """Wraps a function ``(EvalCase) -> sql`` as a ``Solver``."""

    def __init__(self, fn: Callable[[EvalCase], str]) -> None:
        """Store the SQL-producing function ``fn``."""
        self._fn = fn

    def solve(self, case: EvalCase) -> SolverOutput:
        """Call the wrapped function and return its SQL as ``SolverOutput.output``."""
        return SolverOutput(output=self._fn(case))

"""``Solver`` Protocol: the contract for the AI system under test.

A Solver turns an ``EvalCase`` into a ``SolverOutput`` — "given a question, produce
SQL." It may be a single prompt, a RAG pipeline, or a multi-agent system. The full
``EvalCase`` (not just ``input``) is passed so the solver can tailor SQL to the
case's platform/dialect. The Solver owns any extraction of the executable artifact
from raw model text (see ``SolverOutput``): ``output`` is the SQL the runner executes
verbatim.

A Protocol (not an ABC), matching ``PlatformAdapter``: arbitrary callables and
lightweight wrappers satisfy it structurally without inheritance.
"""

from typing import Protocol, runtime_checkable

from data_eval.types import EvalCase, SolverOutput


@runtime_checkable
class Solver(Protocol):
    """Produces a ``SolverOutput`` for an ``EvalCase``."""

    def solve(self, case: EvalCase) -> SolverOutput:
        """Produce output (for SQL solvers, the executable SQL) for ``case``."""
        ...

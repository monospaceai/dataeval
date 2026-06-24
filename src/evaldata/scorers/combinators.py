"""`FirstDecisive`: a generic scorer combinator running members until one passes."""

from collections.abc import Sequence

from evaldata.scorers.base import Scorer
from evaldata.scorers.context import ScoreContext
from evaldata.types import EvalCase, ExecutionResult, ScoreResult, SolverOutput


class FirstDecisive:
    """Runs member scorers in order; the first that passes wins, else the last decides.

    The first member whose `ScoreResult.passed` is true is returned immediately; if none pass,
    the last member's result is returned, so its diagnostics (e.g. a diff) surface. Order
    members so an earlier one's failure means "couldn't decide", not "refuted".
    """

    def __init__(self, scorers: Sequence[Scorer]) -> None:
        """Bind the combinator to an ordered list of member scorers.

        Args:
            scorers: The member scorers, in priority order.

        Raises:
            ValueError: If `scorers` is empty.
        """
        self._scorers = list(scorers)
        if not self._scorers:
            msg = "FirstDecisive requires at least one scorer"
            raise ValueError(msg)

    def score(
        self, case: EvalCase, output: SolverOutput, result: ExecutionResult, *, context: ScoreContext
    ) -> ScoreResult:
        """Run members in order, returning the first that passes (later members not consulted), else the last.

        The returned result carries a `metadata["first_decisive"]` trail of
        `{"scorer", "passed"}` for each member that actually ran.

        Args:
            case: The eval case, forwarded to each member.
            output: The solver output, forwarded to each member.
            result: The executed model result, forwarded to each member.
            context: The score context, forwarded to each member.

        Returns:
            The first passing member's `ScoreResult`, or the last member's result when none
            pass, with the `"first_decisive"` trail merged into its metadata.
        """
        trail: list[dict[str, object]] = []
        decided: ScoreResult | None = None
        for scorer in self._scorers:
            decided = scorer.score(case, output, result, context=context)
            trail.append({"scorer": decided.scorer, "passed": decided.passed})
            if decided.passed:
                break
        assert decided is not None
        return decided.model_copy(update={"metadata": {**decided.metadata, "first_decisive": trail}})

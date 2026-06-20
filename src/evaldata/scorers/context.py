"""`ScoreContext`: per-case capabilities injected into `Scorer.score`."""

from dataclasses import dataclass

from evaldata.scorers.query import QueryRunner


@dataclass(frozen=True)
class ScoreContext:
    """Per-case capabilities injected into `Scorer.score`.

    Attributes:
        queries: The budget-aware runner for derived SQL against the case's platform.
    """

    queries: QueryRunner

"""`MetricSpecEquivalence`: confirm two metric queries match by resolving both through MetricFlow."""

from evaldata.dbt.errors import DbtError
from evaldata.dbt.metricflow import canonicalize
from evaldata.dbt.semantic_layer import MetricCase, MetricQuery
from evaldata.types import ScoreResult

SCORER_NAME = "metric_spec_equivalence"


class MetricSpecEquivalence:
    """Confirms a metric query matches the gold query by comparing their MetricFlow-resolved forms.

    Both queries are resolved through MetricFlow against the project's semantic manifest; equal
    resolved forms confirm equivalence (a passing, proven result). Anything else — the forms
    differ, MetricFlow is unavailable, or a query does not resolve — is inconclusive, never a
    refutation.
    """

    def score(self, case: MetricCase, query: MetricQuery) -> ScoreResult:
        """Resolve the candidate and gold queries and confirm equivalence when they match.

        Args:
            case: The eval case, supplying the gold query and the target directory.
            query: The candidate metric query.

        Returns:
            A passing, proven `ScoreResult` when both queries resolve to the same MetricFlow query,
            else an inconclusive result.
        """
        candidate = canonicalize(query, case.target_dir)
        if isinstance(candidate, DbtError):
            return _inconclusive(f"model query: {candidate.message}")
        gold = canonicalize(case.gold, case.target_dir)
        if isinstance(gold, DbtError):
            return _inconclusive(f"gold query: {gold.message}")

        if candidate == gold:
            return ScoreResult(
                scorer=SCORER_NAME,
                verdict="pass",
                basis="proven",
                explanation="metric queries resolve to the same MetricFlow query",
            )
        return _inconclusive("metric queries resolve to different MetricFlow queries")


def _inconclusive(detail: str) -> ScoreResult:
    """Return an inconclusive `ScoreResult` carrying `detail`."""
    return ScoreResult(scorer=SCORER_NAME, verdict="inconclusive", explanation=detail)

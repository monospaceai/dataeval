"""`MetricSpecEquivalence`: confirm two metric queries match by resolving both through MetricFlow."""

from evaldata.dbt.errors import DbtError
from evaldata.dbt.metricflow import canonicalize
from evaldata.scorers.context import ScoreContext
from evaldata.types import EvalCase, ExecutionResult, GoldMetricQuery, ScoreResult, SolverOutput

SCORER_NAME = "metric_spec_equivalence"

# The case-metadata key holding the dbt `target/` directory whose semantic manifest resolves queries.
TARGET_DIR_KEY = "dbt_target_dir"


class MetricSpecEquivalence:
    """Confirms a metric query matches the gold query by comparing their MetricFlow-resolved forms.

    Both queries are resolved through MetricFlow against the project's semantic manifest; equal
    resolved forms confirm equivalence (a passing, proven result). Anything else — the forms
    differ, the target directory is absent, MetricFlow is unavailable, or a query does not
    resolve — is inconclusive, never a refutation.
    """

    def score(
        self, case: EvalCase, output: SolverOutput, result: ExecutionResult, *, context: ScoreContext
    ) -> ScoreResult:
        """Resolve the model and gold metric queries and confirm equivalence when they match.

        Args:
            case: The eval case; `expected` must be a `GoldMetricQuery`, and `metadata` must carry
                the dbt target directory under `dbt_target_dir`.
            output: The solver output; `query` must be set.
            result: Unused; this scorer reads the semantic manifest, not the result set.
            context: Unused; resolution reads the manifest, not the warehouse.

        Returns:
            A passing, proven `ScoreResult` when both queries resolve to the same MetricFlow query,
            else an inconclusive result.

        Raises:
            TypeError: If `case.expected` is not a `GoldMetricQuery`, or `output` carries no query.
        """
        if not isinstance(case.expected, GoldMetricQuery):
            msg = f"MetricSpecEquivalence requires a GoldMetricQuery; got {type(case.expected).__name__}"
            raise TypeError(msg)
        if output.query is None:
            msg = "MetricSpecEquivalence requires a metric query in the solver output"
            raise TypeError(msg)

        target_dir = case.metadata.get(TARGET_DIR_KEY)
        if target_dir is None:
            return _inconclusive(f"no dbt target directory in case metadata under {TARGET_DIR_KEY!r}")

        candidate = canonicalize(output.query, target_dir)
        if isinstance(candidate, DbtError):
            return _inconclusive(f"model query: {candidate.message}")
        gold = canonicalize(case.expected.query, target_dir)
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
    return ScoreResult(scorer=SCORER_NAME, verdict="inconclusive", explanation=detail)

"""``ResultSetEquivalence``: the v1 scorer — wraps the equivalence engine.

Bridges the executed ``ExecutionResult`` and the case's ``ExpectedResultSet`` into the
engine's ``TypedResultSet`` / ``UntypedResultSet`` inputs and delegates to ``compare()``.

Type-comparison gating (matches pandas ``check_dtype`` / GE practice — never automatic
unless both sides carry types): the **typed** path runs only when the expected outcome
*and* the execution result both carry a schema; otherwise the **untyped** values-only
path runs. The typed path needs a single SQLGlot dialect, taken from the case's
``PlatformRef`` (explicit ``dialect`` override, else inferred from ``kind``).

Errors-as-values: a failed query (``ExecutionResult.error``) becomes a failing
``ScoreResult`` with an explanation, not a raised exception. Only a genuine
misconfiguration — pairing this scorer with a non-``ExpectedResultSet`` expectation —
raises, since that is programmer error.
"""

from data_eval.equivalence import TypedResultSet, UntypedResultSet, compare
from data_eval.types import (
    EvalCase,
    ExecutionResult,
    ExpectedResultSet,
    PlatformKind,
    PlatformRef,
    ScoreResult,
    SolverOutput,
    SQLDialect,
)

SCORER_NAME = "result_set_equivalence"

# Every PlatformKind is also a valid SQLGlot dialect string, but they are distinct
# Literal types — this explicit map is the type-safe bridge (and documents the relation).
_KIND_TO_DIALECT: dict[PlatformKind, SQLDialect] = {
    "duckdb": "duckdb",
    "postgres": "postgres",
    "snowflake": "snowflake",
    "bigquery": "bigquery",
    "databricks": "databricks",
}


def _dialect_for(platform: PlatformRef) -> SQLDialect:
    """Resolve the SQLGlot dialect for a platform: explicit override, else inferred from kind."""
    return platform.dialect or _KIND_TO_DIALECT[platform.kind]


class ResultSetEquivalence:
    """Scores a case by comparing its executed result set against its ``ExpectedResultSet``."""

    def score(self, case: EvalCase, output: SolverOutput, result: ExecutionResult) -> ScoreResult:
        """Compare ``result`` against ``case.expected``; pass iff the engine finds them equivalent."""
        expected = case.expected
        if not isinstance(expected, ExpectedResultSet):
            msg = f"ResultSetEquivalence requires an ExpectedResultSet; got {type(expected).__name__}"
            raise TypeError(msg)

        if result.error is not None:
            return ScoreResult(
                scorer=SCORER_NAME,
                passed=False,
                explanation=f"query execution failed: {result.error}",
            )

        if expected.schema_ is not None and result.schema_ is not None:
            diff = compare(
                TypedResultSet(rows=result.rows, schema=result.schema_),
                TypedResultSet(rows=expected.rows, schema=expected.schema_),
                case.comparison,
                dialect=_dialect_for(case.platform),
            )
        else:
            diff = compare(
                UntypedResultSet(rows=result.rows),
                UntypedResultSet(rows=expected.rows),
                case.comparison,
            )

        return ScoreResult(scorer=SCORER_NAME, passed=diff is None, diff=diff)

"""`ResultSetEquivalence`: result-set scorer that diffs in-warehouse via `EXCEPT ALL`."""

from typing import Any

from data_eval.equivalence import build_result_set_diff, reconcile_columns
from data_eval.scorers import sql
from data_eval.scorers.context import ScoreContext
from data_eval.scorers.query import QueryRunner
from data_eval.types import (
    EvalCase,
    ExecutionResult,
    ExpectedResultSet,
    Schema,
    ScoreResult,
    SolverOutput,
    TypeMismatch,
)

SCORER_NAME = "result_set_equivalence"


class ResultSetEquivalence:
    """Scores a case by diffing its executed result set against its `ExpectedResultSet` in SQL."""

    def score(
        self, case: EvalCase, output: SolverOutput, result: ExecutionResult, *, context: ScoreContext
    ) -> ScoreResult:
        """Compare `result` against `case.expected`; pass iff the engine finds them equivalent.

        Column reconciliation and type comparison run in Python; row equivalence is pushed
        into the platform as two `EXCEPT ALL` diffs (bag semantics) over the shared columns,
        with authored expected rows materialised as typed literals so the engine defines
        equality. Only mismatch counts and bounded samples are read back. `null_equality`
        `"distinct"` is unsupported by this path and rejected with a failing result.

        Args:
            case: The eval case, carrying the expected result set, comparison config, and platform.
            output: The solver output (part of the `Scorer` protocol; unused here).
            result: The executed result to compare against the expectation.
            context: The score context, carrying the budget-aware `QueryRunner`.

        Returns:
            A `ScoreResult` that passes when the result set matches the expectation. A failed
            model query, a failed derived query, or `null_equality="distinct"` each yield a
            failing result with an explanation.

        Raises:
            TypeError: If `case.expected` is not an `ExpectedResultSet`.
        """
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

        config = case.comparison
        if config.null_equality == "distinct":
            return ScoreResult(
                scorer=SCORER_NAME,
                passed=False,
                explanation="null_equality='distinct' is not supported by the SQL equivalence path",
            )

        actual_names = _column_names(result.schema_, result.rows)
        expected_names = _column_names(expected.schema_, expected.rows)
        columns = reconcile_columns(actual_names, expected_names, config.column_order)
        type_mismatches = _type_mismatches(result.schema_, expected.schema_, columns.in_both)

        diff_or_error = _diff_rows(expected, columns.in_both, config.float_tolerance, context.queries)
        if isinstance(diff_or_error, str):
            return ScoreResult(scorer=SCORER_NAME, passed=False, explanation=f"query execution failed: {diff_or_error}")
        missing_count, extra_count, sample_missing, sample_extra = diff_or_error

        diff = build_result_set_diff(
            expected_row_count=len(expected.rows),
            actual_row_count=len(result.rows),
            missing_row_count=missing_count,
            extra_row_count=extra_count,
            sample_missing_rows=sample_missing,
            sample_extra_rows=sample_extra,
            columns=columns,
            type_mismatches=type_mismatches,
        )
        return ScoreResult(scorer=SCORER_NAME, passed=diff is None, diff=diff)


_RowDiff = tuple[int, int, list[dict[str, Any]], list[dict[str, Any]]]


def _diff_rows(
    expected: ExpectedResultSet,
    in_both: list[str],
    float_tolerance: float,
    queries: QueryRunner,
) -> _RowDiff | str:
    """Compute the bag diff over `in_both` via two `EXCEPT ALL` runs, or return an error string.

    Args:
        expected: The expected result set (rows + optional schema).
        in_both: The shared columns to diff on, in expected order.
        float_tolerance: The absolute tolerance; `> 0` rounds numeric columns before diffing.
        queries: The budget-aware runner used to execute the derived diff queries.

    Returns:
        `(missing_count, extra_count, sample_missing, sample_extra)` on success, where
        `missing` are expected rows absent from actual and `extra` are actual rows absent
        from expected; or an error message string when a derived query fails. With no shared
        columns the diff is empty `(0, 0, [], [])` and no query runs.
    """
    if not in_both:
        return (0, 0, [], [])

    round_scale = sql._round_scale(float_tolerance) if float_tolerance > 0 else None
    numeric = _numeric_columns(expected.schema_, in_both, queries.dialect)
    expected_rel = sql.expected_relation(expected.rows, expected.schema_, in_both, queries.dialect, round_scale)
    actual_rel = sql.aligned_actual(queries.model_sql, in_both, numeric, queries.dialect, round_scale)

    missing = queries.scalar(sql.except_all_count(expected_rel, actual_rel, queries.dialect))
    if missing.error is not None:
        return missing.error
    extra = queries.scalar(sql.except_all_count(actual_rel, expected_rel, queries.dialect))
    if extra.error is not None:
        return extra.error

    missing_count = int(missing.value or 0)
    extra_count = int(extra.value or 0)
    sample_missing: list[dict[str, Any]] = []
    if missing_count:
        run = queries.run(sql.except_all_sample(expected_rel, actual_rel, queries.dialect))
        if run.error is not None:
            return run.error
        sample_missing = run.rows
    sample_extra: list[dict[str, Any]] = []
    if extra_count:
        run = queries.run(sql.except_all_sample(actual_rel, expected_rel, queries.dialect))
        if run.error is not None:
            return run.error
        sample_extra = run.rows
    return (missing_count, extra_count, sample_missing, sample_extra)


def _column_names(schema: Schema | None, rows: list[dict[str, Any]]) -> list[str]:
    """Resolve column names from a schema if present, else the first row's keys.

    Args:
        schema: The result/expected schema, or `None`.
        rows: The rows, used as a fallback for names.

    Returns:
        The column names in order, or `[]` when neither a schema nor any rows are present.
    """
    if schema is not None:
        return schema.names
    if rows:
        return list(rows[0].keys())
    return []


def _type_mismatches(actual: Schema | None, expected: Schema | None, in_both: list[str]) -> list[TypeMismatch]:
    """Compare shared-column types when both schemas are present.

    Args:
        actual: The actual schema, or `None`.
        expected: The expected schema, or `None`.
        in_both: The shared columns to compare, in expected order.

    Returns:
        A `TypeMismatch` per shared column whose actual type differs from the expected type;
        empty when either schema is absent.
    """
    if actual is None or expected is None:
        return []
    actual_types = dict(zip(actual.names, actual.types, strict=True))
    expected_types = dict(zip(expected.names, expected.types, strict=True))
    return [
        TypeMismatch(column=col, expected=expected_types[col].raw, actual=actual_types[col].raw)
        for col in in_both
        if actual_types[col] != expected_types[col]
    ]


def _numeric_columns(schema: Schema | None, in_both: list[str], dialect: sql.Dialect) -> set[str]:
    """Resolve which shared columns are numeric, from the expected schema's types.

    Args:
        schema: The expected schema, or `None` (then no column is treated as numeric).
        in_both: The shared columns to classify.
        dialect: The dialect to parse the column types in.

    Returns:
        The subset of `in_both` whose expected type is numeric.
    """
    if schema is None:
        return set()
    types = dict(zip(schema.names, schema.types, strict=True))
    return {col for col in in_both if col in types and sql._is_numeric_type(types[col].raw, dialect)}

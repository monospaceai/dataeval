"""Public ``compare()`` entry: dispatches on typed-vs-untyped result sets (Design A).

Errors-as-values: equivalence failure is a returned ``ResultSetDiff``, not an exception.
``None`` means equivalent. The typed overload enables semantic type comparison via
SQLGlot; the untyped overload doesn't. Row comparison is always multiset (unordered) —
ordered comparison and key-aligned matching are deferred increments, so
``column_mismatches`` stays empty for now.
"""

from typing import overload

from data_eval.equivalence.columns import reconcile_columns
from data_eval.equivalence.resultset import TypedResultSet, UntypedResultSet
from data_eval.equivalence.rows import match_multiset
from data_eval.equivalence.types import types_match
from data_eval.types import ComparisonConfig, ResultSetDiff, SQLDialect, TypeMismatch

#: Max differing rows carried in each ``ResultSetDiff`` sample. Counts stay exact; only
#: the inline examples are capped so a large mismatch doesn't flood the failure message.
#: Datacompy/GE use 10/20 here; made configurable when the comparison surface grows.
SAMPLE_LIMIT = 10


@overload
def compare(
    actual: TypedResultSet,
    expected: TypedResultSet,
    config: ComparisonConfig | None = ...,
    *,
    compare_types: bool = ...,
    dialect: SQLDialect | None = ...,
) -> ResultSetDiff | None: ...


@overload
def compare(
    actual: UntypedResultSet,
    expected: UntypedResultSet,
    config: ComparisonConfig | None = ...,
) -> ResultSetDiff | None: ...


def compare(
    actual: TypedResultSet | UntypedResultSet,
    expected: TypedResultSet | UntypedResultSet,
    config: ComparisonConfig | None = None,
    *,
    compare_types: bool = True,
    dialect: SQLDialect | None = None,
) -> ResultSetDiff | None:
    """Compare actual vs expected result sets; ``None`` if equivalent, else a ``ResultSetDiff``."""
    cfg = config or ComparisonConfig()

    if isinstance(actual, TypedResultSet) and isinstance(expected, TypedResultSet):
        actual_cols = [c.name for c in actual.schema_]
        expected_cols = [c.name for c in expected.schema_]
        actual_types_map = {c.name: c.type for c in actual.schema_}
        expected_types_map = {c.name: c.type for c in expected.schema_}
        do_types = compare_types
    elif isinstance(actual, UntypedResultSet) and isinstance(expected, UntypedResultSet):
        actual_cols = list(actual.rows[0].keys()) if actual.rows else []
        expected_cols = list(expected.rows[0].keys()) if expected.rows else []
        actual_types_map = {}
        expected_types_map = {}
        do_types = False
    else:
        msg = "actual and expected must both be Typed or both Untyped result sets"
        raise TypeError(msg)

    common, missing_cols, extra_cols, order_mismatch = reconcile_columns(
        actual_cols,
        expected_cols,
        cfg.column_order,
    )

    type_mismatches: list[TypeMismatch] = []
    if do_types:
        if dialect is None:
            msg = "dialect= is required when compare_types=True on typed result sets"
            raise ValueError(msg)
        for col in common:
            if not types_match(actual_types_map[col], expected_types_map[col], dialect):
                type_mismatches.append(
                    TypeMismatch(
                        column=col,
                        expected=expected_types_map[col],
                        actual=actual_types_map[col],
                    ),
                )

    missing_rows, extra_rows = match_multiset(
        actual.rows,
        expected.rows,
        common,
        cfg.null_equality,
        cfg.float_tolerance,
    )

    diff = ResultSetDiff(
        expected_row_count=len(expected.rows),
        actual_row_count=len(actual.rows),
        missing_row_count=len(missing_rows),
        extra_row_count=len(extra_rows),
        sample_missing_rows=missing_rows[:SAMPLE_LIMIT],
        sample_extra_rows=extra_rows[:SAMPLE_LIMIT],
        missing_columns=missing_cols,
        extra_columns=extra_cols,
        type_mismatches=type_mismatches,
        column_order_mismatch=order_mismatch,
    )

    if _is_empty(diff):
        return None
    return diff


def _is_empty(d: ResultSetDiff) -> bool:
    """True iff a ``ResultSetDiff`` carries no signals of difference."""
    return (
        d.missing_row_count == 0
        and d.extra_row_count == 0
        and not d.missing_columns
        and not d.extra_columns
        and not d.type_mismatches
        and not d.column_mismatches
        and not d.column_order_mismatch
    )

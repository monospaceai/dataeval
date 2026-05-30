"""Row matching: multiset/bag comparison via greedy O(n*m) matching."""

from typing import Any, Literal

from data_eval.equivalence.values import cells_equal


def rows_equal(
    a: dict[str, Any],
    b: dict[str, Any],
    columns: list[str],
    null_equality: Literal["equal", "distinct"],
    float_tolerance: float,
) -> bool:
    """True iff two rows have equal values across the given columns."""
    return all(cells_equal(a.get(c), b.get(c), null_equality, float_tolerance) for c in columns)


def match_multiset(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    columns: list[str],
    null_equality: Literal["equal", "distinct"],
    float_tolerance: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Greedy multiset match; returns ``(missing_rows, extra_rows)``.

    ``missing_rows`` are expected rows with no actual match; ``extra_rows`` are the
    actual rows left over. Counts are ``len(...)`` of each; the rows themselves let
    callers surface a sample in diagnostics (GE ``partial_unexpected_list`` / datacompy
    ``sample_mismatch`` convention). Each expected row consumes the first unmatched
    actual row that equals it. O(n*m) worst case — acceptable for eval-sized result
    sets (answers, not full tables). Best-effort under ambiguous tolerance matching;
    the principled successor is key-aligned comparison (datacompy-style), planned
    alongside the match-key increment.
    """
    remaining = list(range(len(actual)))
    missing_rows: list[dict[str, Any]] = []
    for exp_row in expected:
        match_i = None
        for i, idx in enumerate(remaining):
            if rows_equal(actual[idx], exp_row, columns, null_equality, float_tolerance):
                match_i = i
                break
        if match_i is None:
            missing_rows.append(exp_row)
        else:
            del remaining[match_i]
    extra_rows = [actual[idx] for idx in remaining]
    return missing_rows, extra_rows

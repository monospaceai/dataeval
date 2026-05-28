"""Column reconciliation between actual and expected schemas."""

from typing import Literal


def reconcile_columns(
    actual: list[str],
    expected: list[str],
    column_order: Literal["ignore", "strict"],
) -> tuple[list[str], list[str], list[str], bool]:
    """Reconcile actual against expected column-name sequences.

    Returns ``(common, missing, extra, order_mismatch)``. ``common`` preserves expected
    order. ``order_mismatch`` is True iff ``column_order == "strict"`` and the actual
    sequence differs positionally from expected; under ``"ignore"`` it is always False.
    Row comparison is always keyed by name (rows are dicts), so the order signal is a
    separate assertion rather than a constraint on row matching.
    """
    actual_set = set(actual)
    expected_set = set(expected)
    common = [c for c in expected if c in actual_set]
    missing = [c for c in expected if c not in actual_set]
    extra = [c for c in actual if c not in expected_set]
    order_mismatch = column_order == "strict" and actual != expected
    return common, missing, extra, order_mismatch

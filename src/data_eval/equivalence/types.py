"""Semantic SQL-type comparison via SQLGlot.

Two type strings are compared by parsing both with SQLGlot in the given dialect and using
``DataType.is_type`` — base-type comparison for scalars and structural comparison for
parameterized types. Aliases like ``BIGINT``/``INT8`` (DuckDB) or ``BIGINT``/``LONG``
(Spark/Databricks) match; genuinely different types — different width, precision, or
nested inner-types — do not.

**Single-dialect only.** Cross-dialect type equality is a deliberate non-goal: the same
SQL type name can mean different things across platforms.
"""

from sqlglot import exp

from data_eval.types import SQLDialect


def types_match(actual: str, expected: str, dialect: SQLDialect) -> bool:
    """True iff two SQL type strings are semantically equivalent in the given dialect.

    Falls back to literal string equality if either string fails to parse — graceful
    handling of exotic native types SQLGlot doesn't recognise, rather than crashing.
    """
    try:
        actual_dt = exp.DataType.build(actual, dialect=dialect)
        expected_dt = exp.DataType.build(expected, dialect=dialect)
    except Exception:
        return actual == expected
    return actual_dt.is_type(expected_dt)

"""SQL builders for expectation pushdown: wrap the model's query and emit check SQL.

Every builder renders dialect-correct SQL via SQLGlot, quoting user column names so a
column named `select` or `order` is safe, and aliasing the derived table as `t`.
"""

import math
from decimal import Decimal
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from data_eval.types import PlatformKind, Schema, Sql, SQLDialect

Dialect = SQLDialect | PlatformKind

SAMPLE_LIMIT = 20


def _subquery(model_sql: Sql, dialect: Dialect) -> exp.Subquery:
    """Parse `model_sql` and wrap it as a subquery aliased `t`.

    Args:
        model_sql: The model's SQL.
        dialect: The SQLGlot dialect to parse and render in.

    Returns:
        A `Subquery` expression `(<model_sql>) AS t`.
    """
    parsed = sqlglot.parse_one(model_sql, dialect=dialect)
    return exp.Subquery(this=parsed, alias=exp.TableAlias(this=exp.to_identifier("t")))


def wrap_model(model_sql: Sql, select: str, dialect: Dialect) -> Sql:
    """Build `SELECT <select> FROM (<model_sql>) AS t`, rendered for `dialect`.

    Args:
        model_sql: The model's SQL.
        select: The projection clause (e.g. `count(*)`).
        dialect: The SQLGlot dialect to parse and render in.

    Returns:
        The wrapped SQL string.
    """
    query = exp.select(select).from_(_subquery(model_sql, dialect))
    return Sql(query.sql(dialect=dialect))


def row_count(model_sql: Sql, dialect: Dialect) -> Sql:
    """Build `SELECT count(*) FROM (<model_sql>) AS t`.

    Args:
        model_sql: The model's SQL.
        dialect: The SQLGlot dialect to parse and render in.

    Returns:
        The row-count SQL string.
    """
    return wrap_model(model_sql, "count(*)", dialect)


def not_null_count(model_sql: Sql, column: str, dialect: Dialect) -> Sql:
    """Build `SELECT count(*) FROM (<model_sql>) AS t WHERE <column> IS NULL`.

    Args:
        model_sql: The model's SQL.
        column: The column checked for NULLs.
        dialect: The SQLGlot dialect to parse and render in.

    Returns:
        The not-null count SQL string.
    """
    query = (
        exp.select("count(*)")
        .from_(_subquery(model_sql, dialect))
        .where(exp.column(column, quoted=True).is_(exp.null()))
    )
    return Sql(query.sql(dialect=dialect))


def not_null_sample(model_sql: Sql, column: str, dialect: Dialect) -> Sql:
    """Build `SELECT * FROM (<model_sql>) AS t WHERE <column> IS NULL LIMIT 20`.

    Args:
        model_sql: The model's SQL.
        column: The column checked for NULLs.
        dialect: The SQLGlot dialect to parse and render in.

    Returns:
        The not-null sample SQL string (up to 20 offending rows).
    """
    query = (
        exp.select("*")
        .from_(_subquery(model_sql, dialect))
        .where(exp.column(column, quoted=True).is_(exp.null()))
        .limit(SAMPLE_LIMIT)
    )
    return Sql(query.sql(dialect=dialect))


def _duplicates_query(model_sql: Sql, column: str, projection: list[str], dialect: Dialect) -> exp.Select:
    """Build the duplicated-values query: non-NULL values grouped, `HAVING count(*) > 1`.

    Args:
        model_sql: The model's SQL.
        column: The column checked for uniqueness.
        projection: The select clauses over the grouped rows.
        dialect: The SQLGlot dialect to parse and render in.

    Returns:
        A `Select` expression over the duplicated keys.
    """
    col = exp.column(column, quoted=True)
    return (
        exp.select(*projection)
        .from_(_subquery(model_sql, dialect))
        .where(exp.Not(this=col.is_(exp.null())))
        .group_by(col)
        .having(exp.Count(this=exp.Star()) > 1)
    )


def unique_count(model_sql: Sql, column: str, dialect: Dialect) -> Sql:
    """Build a count of duplicated (non-NULL) values: distinct keys appearing more than once.

    Args:
        model_sql: The model's SQL.
        column: The column checked for uniqueness.
        dialect: The SQLGlot dialect to parse and render in.

    Returns:
        The unique-violation count SQL string.
    """
    inner = _duplicates_query(model_sql, column, [exp.column(column, quoted=True).sql(dialect=dialect)], dialect)
    outer = exp.select("count(*)").from_(exp.Subquery(this=inner, alias=exp.TableAlias(this=exp.to_identifier("d"))))
    return Sql(outer.sql(dialect=dialect))


def unique_sample(model_sql: Sql, column: str, dialect: Dialect) -> Sql:
    """Build a sample of up to 20 duplicated values with their counts (column `n`).

    Args:
        model_sql: The model's SQL.
        column: The column checked for uniqueness.
        dialect: The SQLGlot dialect to parse and render in.

    Returns:
        The unique-violation sample SQL string.
    """
    col = exp.column(column, quoted=True).sql(dialect=dialect)
    query = _duplicates_query(model_sql, column, [col, "count(*) AS n"], dialect).limit(SAMPLE_LIMIT)
    return Sql(query.sql(dialect=dialect))


def _round_scale(tol: float) -> int:
    """Derive a decimal scale from an absolute float tolerance for `ROUND` matching.

    Args:
        tol: The absolute float tolerance; must be positive.

    Returns:
        `max(0, round(-log10(tol)))`, the number of fractional digits to round to.
    """
    return max(0, round(-math.log10(tol)))


def _literal(value: Any) -> exp.Expression:
    """Render a Python cell value as a SQLGlot literal expression (`NULL` for `None`).

    Args:
        value: The cell value (`None`, `bool`, `int`/`float`/`Decimal`, `str`, …).

    Returns:
        A SQLGlot expression for the literal.
    """
    if value is None:
        return exp.null()
    if isinstance(value, bool):
        return exp.convert(value)
    if isinstance(value, (int, float, Decimal)):
        return exp.Literal.number(str(value))
    if isinstance(value, str):
        return exp.Literal.string(value)
    return exp.convert(value)


def _is_numeric_type(raw: str, dialect: Dialect) -> bool:
    """Whether a SQL type string names a numeric type in `dialect`.

    Args:
        raw: The native SQL type string.
        dialect: The SQLGlot dialect to parse `raw` in.

    Returns:
        `True` if `raw` parses to a numeric type, `False` otherwise (including unparseable).
    """
    try:
        return exp.DataType.build(raw, dialect=dialect).this in exp.DataType.NUMERIC_TYPES
    except SqlglotError:
        return False


# A wide fixed-point cast applied before `ROUND` so the tolerance scale is not truncated.
_ROUND_CAST = "DECIMAL(38, 18)"


def _maybe_round(value: exp.Expression, round_it: bool, scale: int) -> exp.Expression:
    """Wrap `value` in `ROUND(CAST(value AS DECIMAL(38, 18)), scale)` when `round_it`.

    Args:
        value: The expression to wrap.
        round_it: Whether to apply rounding.
        scale: The decimal scale passed to `ROUND`.

    Returns:
        The wrapped expression, or `value` unchanged when `round_it` is false.
    """
    if not round_it:
        return value
    fixed = exp.Cast(this=value, to=exp.DataType.build(_ROUND_CAST))
    return exp.func("ROUND", fixed, exp.Literal.number(scale))


def expected_relation(
    rows: list[dict[str, Any]],
    schema: Schema | None,
    in_both: list[str],
    dialect: Dialect,
    round_scale: int | None,
) -> exp.Query:
    """Materialise authored expected rows as a typed inline relation over `in_both`.

    Each row becomes `SELECT CAST(<lit> AS <type>) AS <col>, …`, `UNION ALL`-joined. Types
    come from `schema` (matched by name, in `in_both` order); a `None` cell is
    `CAST(NULL AS <type>)`. When `round_scale` is not `None`, numeric columns are wrapped in
    `ROUND(…, round_scale)`. When `schema` is `None`, literals are emitted untyped
    (best-effort) and no rounding is applied — string-vs-number distinctions are then left to
    the engine's literal types.

    Args:
        rows: The authored expected rows, keyed by column name.
        schema: The expected schema supplying per-column types, or `None` for untyped.
        in_both: The columns to project, in expected order.
        dialect: The SGLGlot dialect to render in.
        round_scale: The `ROUND` scale for numeric columns, or `None` for no rounding.

    Returns:
        A SQLGlot query (`SELECT …` or a `UNION ALL` chain) yielding the expected relation.
        An empty `rows` yields a `SELECT … WHERE 1 = 0` typed empty relation.
    """
    types = dict(zip(schema.names, schema.types, strict=True)) if schema is not None else {}

    def project(row: dict[str, Any]) -> exp.Select:
        selections: list[exp.Expression] = []
        for col in in_both:
            lit = _literal(row.get(col))
            if col in types:
                raw = types[col].raw
                try:
                    cell: exp.Expression = exp.Cast(this=lit, to=exp.DataType.build(raw, dialect=dialect))
                except SqlglotError:
                    cell = lit
                numeric = _is_numeric_type(raw, dialect)
            else:
                cell = lit
                numeric = False
            cell = _maybe_round(cell, round_scale is not None and numeric, round_scale or 0)
            selections.append(cell.as_(exp.to_identifier(col, quoted=True)))
        return exp.Select(expressions=selections)

    if not rows:
        empty = project({}).where(exp.condition("1 = 0"))
        return empty

    relation: exp.Query = project(rows[0])
    for row in rows[1:]:
        relation = exp.union(relation, project(row), distinct=False)
    return relation


def aligned_actual(
    model_sql: Sql,
    in_both: list[str],
    numeric_columns: set[str],
    dialect: Dialect,
    round_scale: int | None,
) -> exp.Select:
    """Project the model's result onto `in_both` (in order), optionally rounding numerics.

    Builds `SELECT <cols> FROM (<model_sql>) AS t`, where each column in `numeric_columns`
    is wrapped in `ROUND(<col>, round_scale)` when `round_scale` is not `None`.

    Args:
        model_sql: The model's SQL.
        in_both: The columns to project, in expected order.
        numeric_columns: The subset of `in_both` to round when `round_scale` is set.
        dialect: The SQLGlot dialect to parse and render in.
        round_scale: The `ROUND` scale for numeric columns, or `None` for no rounding.

    Returns:
        A `Select` projecting the aligned actual relation.
    """
    selections: list[exp.Expression] = []
    for col in in_both:
        column = exp.column(col, quoted=True)
        cell = _maybe_round(column, round_scale is not None and col in numeric_columns, round_scale or 0)
        selections.append(cell.as_(exp.to_identifier(col, quoted=True)))
    return exp.Select(expressions=selections).from_(_subquery(model_sql, dialect))


def _operand(relation: exp.Query, alias: str) -> exp.Select:
    """Wrap `relation` as `SELECT * FROM (<relation>) AS <alias>` to pin `EXCEPT ALL` precedence.

    Args:
        relation: The relation to wrap (a `SELECT` or a `UNION ALL` chain).
        alias: The subquery alias.

    Returns:
        A `Select` over the aliased subquery.
    """
    sub = exp.Subquery(this=relation.copy(), alias=exp.TableAlias(this=exp.to_identifier(alias)))
    return exp.select("*").from_(sub)


def _except_all(left: exp.Query, right: exp.Query) -> exp.Subquery:
    """Build the subquery `((left) EXCEPT ALL (right)) AS d`.

    Args:
        left: The left relation.
        right: The right relation.

    Returns:
        A `Subquery` over the bag difference, aliased `d`. Each operand is wrapped as a
        subquery so a `UNION ALL` operand associates correctly under `EXCEPT ALL`.
    """
    diff = exp.except_(_operand(left, "l"), _operand(right, "r"), distinct=False)
    return exp.Subquery(this=diff, alias=exp.TableAlias(this=exp.to_identifier("d")))


def except_all_count(left: exp.Query, right: exp.Query, dialect: Dialect) -> Sql:
    """Build `SELECT count(*) FROM ((left) EXCEPT ALL (right)) AS d`.

    Args:
        left: The left relation.
        right: The right relation.
        dialect: The SQLGlot dialect to render in.

    Returns:
        The bag-difference count SQL string.
    """
    query = exp.select("count(*)").from_(_except_all(left, right))
    return Sql(query.sql(dialect=dialect))


def except_all_sample(left: exp.Query, right: exp.Query, dialect: Dialect) -> Sql:
    """Build `SELECT * FROM ((left) EXCEPT ALL (right)) AS d LIMIT 20`.

    Args:
        left: The left relation.
        right: The right relation.
        dialect: The SQLGlot dialect to render in.

    Returns:
        The bag-difference sample SQL string (up to 20 rows).
    """
    query = exp.select("*").from_(_except_all(left, right)).limit(SAMPLE_LIMIT)
    return Sql(query.sql(dialect=dialect))

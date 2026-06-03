"""SQL builders for expectation pushdown: wrap the model's query and emit check SQL.

Every builder renders dialect-correct SQL via SQLGlot, quoting user column names so a
column named `select` or `order` is safe, and aliasing the derived table as `t`.
"""

import sqlglot
from sqlglot import exp

from data_eval.types import PlatformKind, Sql, SQLDialect

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

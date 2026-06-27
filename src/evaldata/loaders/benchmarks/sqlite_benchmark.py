"""Shared core for SQLite-backed benchmark loaders (Spider, BIRD)."""

import sqlite3
from functools import cache
from pathlib import Path
from typing import Any

from evaldata.platforms.registry import sqlite_platform
from evaldata.types import EvalCase, GoldQuery


@cache
def schema_ddl(db_path: str) -> str:
    """Return the `CREATE TABLE` statements for every table in the SQLite database at `db_path`.

    Read from `sqlite_master` — the same engine that later executes the queries — so the schema
    a model sees matches the database it runs against. Results are cached per path.

    Args:
        db_path: Filesystem path to the SQLite database.

    Returns:
        The table definitions in `sqlite_master` order, each separated by a semicolon and a
        newline. Empty when the database declares no tables.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL ORDER BY rowid"
        ).fetchall()
    finally:
        conn.close()
    return ";\n".join(sql for (sql,) in rows)


def build_case(
    *,
    source: str,
    case_id: str,
    question: str,
    gold_sql: str,
    db_id: str,
    db_path: Path,
    extra_metadata: dict[str, Any],
) -> EvalCase:
    """Assemble one benchmark `EvalCase` against its `db_id`'s SQLite database.

    Args:
        source: The benchmark name (e.g. `"spider"`, `"bird"`), recorded in metadata.
        case_id: The case identifier.
        question: The natural-language question (the solver input).
        gold_sql: The benchmark's gold SQL, used as the `GoldQuery` expected answer.
        db_id: The benchmark database identifier.
        db_path: Filesystem path to the `db_id`'s SQLite database.
        extra_metadata: Benchmark-specific metadata to merge (e.g. evidence, difficulty).

    Returns:
        An `EvalCase` whose platform is the `db_id`'s SQLite database (named `f"{source}:{db_id}"`
        so one adapter is cached per database) and whose `metadata` carries the source, `db_id`,
        and extracted `schema_ddl`.
    """
    metadata: dict[str, Any] = {
        "source": source,
        "db_id": db_id,
        "schema_ddl": schema_ddl(str(db_path)),
        **extra_metadata,
    }
    return EvalCase(
        id=case_id,
        input=question,
        expected=GoldQuery(sql=gold_sql),
        platform=sqlite_platform(name=f"{source}:{db_id}", path=str(db_path)),
        metadata=metadata,
    )

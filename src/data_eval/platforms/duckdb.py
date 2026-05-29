"""``DuckDBAdapter``: in-process DuckDB execution backend.

Conforms to ``PlatformAdapter``. Uses ``duckdb`` directly (no SQLAlchemy) and
reports native DuckDB type strings via the cursor's ``description``: each
``description[i][1]`` is a ``DuckDBPyType`` whose ``str()`` yields the type
SQLGlot's ``duckdb`` dialect parses (``INTEGER``, ``STRUCT(a INTEGER, b VARCHAR)``,
``INTEGER[]``, ...). All query failures surface as ``duckdb.Error`` and are
returned via ``ExecutionResult.error`` rather than raised.
"""

import time

import duckdb

from data_eval.types import Column, ExecutionResult


class DuckDBAdapter:
    """Executes SQL against an in-process DuckDB database."""

    def __init__(self, database: str = ":memory:") -> None:
        """Open a DuckDB connection to ``database`` (default ``:memory:``)."""
        self._conn = duckdb.connect(database)

    def execute(self, sql: str) -> ExecutionResult:
        """Execute one SQL statement; return rows + schema + latency, or error-as-value."""
        start = time.perf_counter()
        try:
            cursor = self._conn.execute(sql)
            description = cursor.description or []
            rows_raw = cursor.fetchall()
        except duckdb.Error as e:
            elapsed = time.perf_counter() - start
            return ExecutionResult(
                rows=[],
                schema=None,
                latency_seconds=elapsed,
                error=str(e),
            )
        elapsed = time.perf_counter() - start
        column_names = [d[0] for d in description]
        schema = [Column(name=d[0], type=str(d[1])) for d in description]
        rows = [dict(zip(column_names, row, strict=True)) for row in rows_raw]
        return ExecutionResult(rows=rows, schema=schema, latency_seconds=elapsed)

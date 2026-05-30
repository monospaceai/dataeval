"""``PostgresAdapter``: PostgreSQL execution backend over ``psycopg`` (v3).

Conforms to ``PlatformAdapter``. Uses ``psycopg`` directly (no SQLAlchemy) and
reports native PostgreSQL type strings via ``cursor.description``: each entry is a
``psycopg.Column`` whose ``.type_display`` yields psycopg's own type rendering
(``int8``, ``varchar(10)``, ``numeric(10,2)``, ``text[]``) — the strings SQLGlot's
``postgres`` dialect parses. Unknown/custom OIDs degrade to ``str(oid)`` rather than
raising, so ``execute`` never crashes on an exotic type. All query failures surface
as ``psycopg.Error`` and are returned via ``ExecutionResult.error`` rather than raised.

The connection runs with ``autocommit=True``: each ``execute`` is its own
transaction, so a failed statement (returned as ``error``) never leaves the
connection in an aborted-transaction state that would poison later calls. This is
why we do NOT use psycopg's connection context manager, whose commit-on-exit /
rollback-on-exception semantics are wrong for our independent per-statement surface.

Connection lifecycle is owned by the adapter: ``close()`` and the context-manager
protocol release the underlying connection. These are NOT on the ``PlatformAdapter``
Protocol — adapters may offer them as a convention (the ``DuckDBAdapter`` precedent).
"""

import time
from types import TracebackType
from typing import Self

import psycopg

from data_eval.types import Column, ExecutionResult


class PostgresAdapter:
    """Executes SQL against a PostgreSQL database via psycopg (v3)."""

    def __init__(self, conninfo: str = "") -> None:
        """Open a psycopg connection.

        ``conninfo`` is a libpq connection string — keyword/value
        (``"host=... port=... user=... password=... dbname=..."``) or a
        ``postgresql://`` URI. Empty uses libpq defaults / ``PG*`` env vars.
        """
        self._conn = psycopg.connect(conninfo, autocommit=True)

    def close(self) -> None:
        """Release the underlying psycopg connection."""
        self._conn.close()

    def __enter__(self) -> Self:
        """Return self; the connection is already open from ``__init__``."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the underlying connection on context-manager exit."""
        self.close()

    def execute(self, sql: str) -> ExecutionResult:
        """Execute one SQL statement; return rows + schema + latency, or error-as-value."""
        start = time.perf_counter()
        try:
            with self._conn.cursor() as cursor:
                # psycopg types `execute` to accept only LiteralString, to steer callers
                # toward parameterized queries. Executing arbitrary caller-provided SQL is
                # this adapter's entire purpose, so that guard is deliberately bypassed.
                cursor.execute(sql)  # ty: ignore[no-matching-overload]
                description = cursor.description
                rows_raw = cursor.fetchall() if description is not None else []
        except psycopg.Error as e:
            elapsed = time.perf_counter() - start
            return ExecutionResult(rows=[], schema=None, latency_seconds=elapsed, error=str(e))
        elapsed = time.perf_counter() - start
        if description is None:
            # Non-row-returning statement (DDL/DML): success, no schema.
            return ExecutionResult(rows=[], schema=None, latency_seconds=elapsed)
        schema: list[Column] = []
        names: list[str] = []
        for col in description:
            schema.append(Column(name=col.name, type=col.type_display))
            names.append(col.name)
        rows = [dict(zip(names, row, strict=True)) for row in rows_raw]
        return ExecutionResult(rows=rows, schema=schema, latency_seconds=elapsed)

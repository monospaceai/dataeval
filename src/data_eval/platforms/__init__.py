"""Platform adapters: per-platform integrations that execute SQL against a data platform.

``DuckDBAdapter`` is exported here because ``duckdb`` is a core dependency. Optional-extra
adapters (e.g. ``PostgresAdapter``) are imported from their own module on demand so the
package imports cleanly without their drivers installed.
"""

from data_eval.platforms.base import PlatformAdapter
from data_eval.platforms.duckdb import DuckDBAdapter
from data_eval.platforms.registry import duckdb_platform, postgres_platform, resolve

__all__ = ["DuckDBAdapter", "PlatformAdapter", "duckdb_platform", "postgres_platform", "resolve"]

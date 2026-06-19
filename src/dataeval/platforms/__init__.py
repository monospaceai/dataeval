"""Platform adapters: per-platform integrations that execute SQL against a data platform."""

import importlib
from typing import TYPE_CHECKING, Any

from dataeval.platforms.base import PlatformAdapter
from dataeval.platforms.duckdb import DuckDBAdapter
from dataeval.platforms.registry import databricks_platform, duckdb_platform, postgres_platform, resolve

if TYPE_CHECKING:
    from dataeval.platforms.databricks import DatabricksAdapter
    from dataeval.platforms.postgres import PostgresAdapter

__all__ = [
    "DatabricksAdapter",
    "DuckDBAdapter",
    "PlatformAdapter",
    "PostgresAdapter",
    "databricks_platform",
    "duckdb_platform",
    "postgres_platform",
    "resolve",
]

_LAZY_ADAPTERS = {
    "PostgresAdapter": ("dataeval.platforms.postgres", "postgres"),
    "DatabricksAdapter": ("dataeval.platforms.databricks", "databricks"),
}


def __getattr__(name: str) -> Any:
    lazy = _LAZY_ADAPTERS.get(name)
    if lazy is not None:
        module_path, extra = lazy
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            msg = f"{name} requires the {extra!r} extra: install dataeval[{extra}]"
            raise ImportError(msg) from e
        return getattr(module, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    return sorted([*globals(), *_LAZY_ADAPTERS])

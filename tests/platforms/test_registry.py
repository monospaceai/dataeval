"""Unit tests for platform-ref builders and ``PlatformRef`` -> adapter resolution."""

from pathlib import Path

import pytest

from data_eval.platforms import duckdb_platform, postgres_platform, resolve
from data_eval.platforms.registry import close_all
from data_eval.types import PlatformRef


@pytest.mark.unit
class TestRefBuilders:
    def test_duckdb_platform_builds_ref(self) -> None:
        ref = duckdb_platform(name="local", path="/tmp/x.duckdb")
        assert ref == PlatformRef(name="local", kind="duckdb", config={"path": "/tmp/x.duckdb"})

    def test_duckdb_platform_defaults_to_in_memory(self) -> None:
        assert duckdb_platform(name="local").config == {"path": ":memory:"}

    def test_postgres_platform_builds_ref(self) -> None:
        ref = postgres_platform(name="warehouse", conninfo="host=db")
        assert ref == PlatformRef(name="warehouse", kind="postgres", config={"conninfo": "host=db"})


@pytest.mark.unit
class TestResolve:
    def test_resolves_and_executes_duckdb(self, tmp_path: Path) -> None:
        db = tmp_path / "t.duckdb"
        adapter = resolve(duckdb_platform(name="local", path=str(db)))
        adapter.execute("CREATE TABLE t (n INTEGER)")
        adapter.execute("INSERT INTO t VALUES (1), (2)")
        result = adapter.execute("SELECT count(*) AS c FROM t")
        assert result.error is None
        assert result.rows == [{"c": 2}]

    def test_same_name_returns_cached_adapter(self) -> None:
        ref = duckdb_platform(name="local")
        assert resolve(ref) is resolve(ref)

    def test_same_name_different_config_raises(self) -> None:
        resolve(duckdb_platform(name="local", path=":memory:"))
        with pytest.raises(ValueError, match="already bound to a different configuration"):
            resolve(duckdb_platform(name="local", path="/tmp/other.duckdb"))

    def test_unsupported_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="no adapter is registered"):
            resolve(PlatformRef(name="wh", kind="snowflake"))

    def test_close_all_is_idempotent_when_empty(self) -> None:
        close_all()
        close_all()  # no raise

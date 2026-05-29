"""Shared conformance battery: every ``PlatformAdapter`` must pass these tests identically.

Each adapter has its own test module under ``tests/platforms/`` that subclasses
``PlatformAdapterConformance`` and provides an ``adapter`` fixture. The base class
is intentionally NOT prefixed ``Test`` so pytest does not collect it standalone —
only subclasses execute, inheriting every ``test_*`` method.

The battery proves the §8 "Independently-tested units" claim: an adapter is "done"
when it passes this — no bespoke per-adapter test design.
"""

import pytest

from data_eval.platforms.base import PlatformAdapter


class PlatformAdapterConformance:
    """Contract tests every ``PlatformAdapter`` must satisfy."""

    @pytest.fixture
    def adapter(self) -> PlatformAdapter:
        """Return a fresh ``PlatformAdapter`` instance. Subclasses must override."""
        raise NotImplementedError

    def test_execute_returns_rows_and_schema(self, adapter: PlatformAdapter) -> None:
        result = adapter.execute("SELECT 1 AS n")
        assert result.error is None
        assert result.rows == [{"n": 1}]
        assert result.schema_ is not None
        assert len(result.schema_) == 1
        assert result.schema_[0].name == "n"
        assert result.schema_[0].type  # non-empty native type string

    def test_schema_reports_native_type_string(self, adapter: PlatformAdapter) -> None:
        # Adapter-agnostic: every adapter must report SOME non-empty type string
        # for a cast-to-BIGINT column. Per-adapter exact-string assertions live in
        # the adapter's own test module.
        result = adapter.execute("SELECT CAST(1 AS BIGINT) AS x")
        assert result.error is None
        assert result.schema_ is not None
        assert result.schema_[0].name == "x"
        assert result.schema_[0].type

    def test_empty_result_set_keeps_schema(self, adapter: PlatformAdapter) -> None:
        result = adapter.execute("SELECT 1 AS n WHERE 1=0")
        assert result.error is None
        assert result.rows == []
        assert result.schema_ is not None
        assert len(result.schema_) == 1
        assert result.schema_[0].name == "n"

    def test_multiple_rows_returned(self, adapter: PlatformAdapter) -> None:
        result = adapter.execute("SELECT * FROM (VALUES (1), (2), (3)) AS t(n)")
        assert result.error is None
        assert len(result.rows) == 3
        assert sorted(r["n"] for r in result.rows) == [1, 2, 3]

    def test_null_values_round_trip(self, adapter: PlatformAdapter) -> None:
        result = adapter.execute("SELECT NULL AS x")
        assert result.error is None
        assert result.rows == [{"x": None}]

    def test_failed_query_returns_error_not_exception(self, adapter: PlatformAdapter) -> None:
        result = adapter.execute("SELECT * FROM does_not_exist_xyz")
        assert result.error is not None
        assert result.error  # non-empty
        assert result.rows == []
        assert result.schema_ is None

    def test_latency_is_measured_on_success(self, adapter: PlatformAdapter) -> None:
        result = adapter.execute("SELECT 1 AS n")
        assert result.error is None
        assert result.latency_seconds >= 0

    def test_latency_is_measured_on_failure(self, adapter: PlatformAdapter) -> None:
        result = adapter.execute("SELECT FROM nope")
        assert result.error is not None
        assert result.latency_seconds >= 0

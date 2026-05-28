"""Tests for the result-set equivalence engine."""

import pytest
from pydantic import ValidationError

from data_eval.equivalence import TypedResultSet, UntypedResultSet
from data_eval.types import Column


@pytest.mark.unit
class TestUntypedResultSet:
    def test_empty_construction(self) -> None:
        rs = UntypedResultSet(rows=[])
        assert rs.rows == []

    def test_with_rows(self) -> None:
        rs = UntypedResultSet(rows=[{"x": 1}, {"x": 2}])
        assert len(rs.rows) == 2

    def test_json_round_trip(self) -> None:
        rs = UntypedResultSet(rows=[{"x": 1}])
        restored = UntypedResultSet.model_validate_json(rs.model_dump_json())
        assert restored == rs

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            UntypedResultSet.model_validate({"rows": [], "schema": []})


@pytest.mark.unit
class TestTypedResultSet:
    def test_minimal_construction(self) -> None:
        rs = TypedResultSet(rows=[], schema=[Column(name="id", type="INTEGER")])
        assert rs.rows == []
        assert rs.schema_ == [Column(name="id", type="INTEGER")]

    def test_with_rows_and_schema(self) -> None:
        rs = TypedResultSet(
            rows=[{"id": 1, "name": "rock"}],
            schema=[Column(name="id", type="BIGINT"), Column(name="name", type="VARCHAR")],
        )
        assert len(rs.schema_) == 2

    def test_nested_type_in_schema(self) -> None:
        rs = TypedResultSet(
            rows=[{"payload": [{"a": 1}]}],
            schema=[Column(name="payload", type="ARRAY<STRUCT<a: INT>>")],
        )
        assert rs.schema_[0].type == "ARRAY<STRUCT<a: INT>>"

    def test_json_round_trip_uses_external_alias(self) -> None:
        rs = TypedResultSet(rows=[{"id": 1}], schema=[Column(name="id", type="INTEGER")])
        dumped = rs.model_dump_json()
        assert '"schema"' in dumped
        assert '"schema_"' not in dumped
        restored = TypedResultSet.model_validate_json(dumped)
        assert restored == rs

    def test_schema_required(self) -> None:
        with pytest.raises(ValidationError):
            TypedResultSet.model_validate({"rows": []})

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            TypedResultSet.model_validate(
                {"rows": [], "schema": [{"name": "x", "type": "INT"}], "dialect": "duckdb"},
            )

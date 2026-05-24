"""Tests for the core public Pydantic types."""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from data_eval.types import (
    ColumnPresenceExpectation,
    ColumnTypeExpectation,
    ComparisonConfig,
    CostBudget,
    EvalCase,
    Expectation,
    ExpectationSuite,
    Expected,
    ExpectedResultSet,
    ExpectedSQL,
    NonNullExpectation,
    PlatformRef,
    RowCountExpectation,
    SnapshotRef,
    UniqueExpectation,
)

ExpectedAdapter: TypeAdapter[Expected] = TypeAdapter(Expected)
ExpectationAdapter: TypeAdapter[Expectation] = TypeAdapter(Expectation)


@pytest.mark.unit
class TestPlatformRef:
    def test_minimal_construction(self) -> None:
        ref = PlatformRef(name="local", kind="duckdb")
        assert ref.name == "local"
        assert ref.kind == "duckdb"
        assert ref.dialect is None
        assert ref.config == {}

    def test_full_construction(self) -> None:
        ref = PlatformRef(
            name="prod-snow",
            kind="snowflake",
            dialect="snowflake",
            config={"account": "abc123", "warehouse": "EVAL_WH"},
        )
        assert ref.config["account"] == "abc123"

    def test_json_schema_round_trip(self) -> None:
        ref = PlatformRef(name="local", kind="duckdb", config={"path": ":memory:"})
        restored = PlatformRef.model_validate_json(ref.model_dump_json())
        assert restored == ref

    def test_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            PlatformRef.model_validate({"name": "x", "kind": "oracle"})

    def test_rejects_unknown_dialect(self) -> None:
        with pytest.raises(ValidationError):
            PlatformRef.model_validate({"name": "x", "kind": "duckdb", "dialect": "mysql"})

    def test_accepts_cross_platform_dialect_override(self) -> None:
        ref = PlatformRef(name="local", kind="duckdb", dialect="snowflake")
        assert ref.dialect == "snowflake"

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValidationError):
            PlatformRef(name="", kind="duckdb")

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            PlatformRef.model_validate({"name": "x", "kind": "duckdb", "nmae": "typo"})


@pytest.mark.unit
class TestSnapshotRef:
    def test_timestamp_construction(self) -> None:
        snap = SnapshotRef(kind="timestamp", value="2026-05-23T14:30:00Z")
        assert snap.kind == "timestamp"
        assert snap.value == "2026-05-23T14:30:00Z"

    def test_version_construction(self) -> None:
        snap = SnapshotRef(kind="version", value="42")
        assert snap.kind == "version"

    def test_snapshot_id_construction(self) -> None:
        snap = SnapshotRef(kind="snapshot_id", value="3051729675574597004")
        assert snap.kind == "snapshot_id"

    def test_json_schema_round_trip(self) -> None:
        snap = SnapshotRef(kind="version", value="42")
        restored = SnapshotRef.model_validate_json(snap.model_dump_json())
        assert restored == snap

    def test_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotRef.model_validate({"kind": "clone", "value": "snap_table"})

    def test_rejects_empty_value(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotRef.model_validate({"kind": "timestamp", "value": ""})

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotRef.model_validate({"kind": "version", "value": "42", "extra": "x"})


@pytest.mark.unit
class TestExpectedResultSet:
    def test_minimal_construction(self) -> None:
        exp = ExpectedResultSet(rows=[{"count": 1297}])
        assert exp.kind == "result_set"
        assert exp.rows == [{"count": 1297}]
        assert exp.schema_ is None

    def test_with_schema(self) -> None:
        exp = ExpectedResultSet(rows=[{"id": 1}], schema={"id": "INTEGER"})
        assert exp.schema_ == {"id": "INTEGER"}

    def test_empty_rows_allowed(self) -> None:
        exp = ExpectedResultSet(rows=[])
        assert exp.rows == []

    def test_json_round_trip(self) -> None:
        exp = ExpectedResultSet(rows=[{"x": 1}], schema={"x": "INTEGER"})
        dumped = exp.model_dump_json()
        assert '"schema"' in dumped
        assert '"schema_"' not in dumped
        restored = ExpectedResultSet.model_validate_json(dumped)
        assert restored == exp

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            ExpectedResultSet.model_validate({"kind": "result_set", "rows": [], "extra": 1})


@pytest.mark.unit
class TestExpectedSQL:
    def test_construction(self) -> None:
        exp = ExpectedSQL(sql="SELECT COUNT(*) FROM tracks WHERE genre = 'Rock'")
        assert exp.kind == "sql"

    def test_json_round_trip(self) -> None:
        exp = ExpectedSQL(sql="SELECT 1")
        restored = ExpectedSQL.model_validate_json(exp.model_dump_json())
        assert restored == exp

    def test_rejects_empty_sql(self) -> None:
        with pytest.raises(ValidationError):
            ExpectedSQL(sql="")


@pytest.mark.unit
class TestExpectations:
    def test_row_count_construction(self) -> None:
        e = RowCountExpectation(exact=42)
        assert e.kind == "row_count"
        assert e.exact == 42

    def test_row_count_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            RowCountExpectation(exact=-1)

    def test_column_presence_construction(self) -> None:
        e = ColumnPresenceExpectation(columns=["id", "revenue"])
        assert e.columns == ["id", "revenue"]

    def test_column_presence_rejects_empty_list(self) -> None:
        with pytest.raises(ValidationError):
            ColumnPresenceExpectation(columns=[])

    def test_column_type_construction(self) -> None:
        e = ColumnTypeExpectation(column="id", expected_type="INTEGER")
        assert e.column == "id"
        assert e.expected_type == "INTEGER"

    def test_non_null_construction(self) -> None:
        e = NonNullExpectation(column="email")
        assert e.column == "email"

    def test_unique_construction(self) -> None:
        e = UniqueExpectation(column="user_id")
        assert e.column == "user_id"

    def test_expectation_discriminator_dispatches(self) -> None:
        data = {"kind": "row_count", "exact": 7}
        e = ExpectationAdapter.validate_python(data)
        assert isinstance(e, RowCountExpectation)

    def test_expectation_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            ExpectationAdapter.validate_python({"kind": "fictional", "x": 1})


@pytest.mark.unit
class TestExpectationSuite:
    def test_construction(self) -> None:
        suite = ExpectationSuite(
            expectations=[
                RowCountExpectation(exact=10),
                UniqueExpectation(column="id"),
            ]
        )
        assert suite.kind == "expectation_suite"
        assert len(suite.expectations) == 2

    def test_rejects_empty_expectations(self) -> None:
        with pytest.raises(ValidationError):
            ExpectationSuite(expectations=[])

    def test_json_round_trip(self) -> None:
        suite = ExpectationSuite(
            expectations=[
                RowCountExpectation(exact=10),
                ColumnPresenceExpectation(columns=["id"]),
            ]
        )
        restored = ExpectationSuite.model_validate_json(suite.model_dump_json())
        assert restored == suite


@pytest.mark.unit
class TestExpected:
    def test_dispatches_to_result_set(self) -> None:
        e = ExpectedAdapter.validate_python({"kind": "result_set", "rows": [{"count": 1}]})
        assert isinstance(e, ExpectedResultSet)

    def test_dispatches_to_sql(self) -> None:
        e = ExpectedAdapter.validate_python({"kind": "sql", "sql": "SELECT 1"})
        assert isinstance(e, ExpectedSQL)

    def test_dispatches_to_expectation_suite(self) -> None:
        e = ExpectedAdapter.validate_python(
            {
                "kind": "expectation_suite",
                "expectations": [{"kind": "row_count", "exact": 5}],
            }
        )
        assert isinstance(e, ExpectationSuite)

    def test_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            ExpectedAdapter.validate_python({"kind": "something_else", "rows": []})

    def test_json_round_trip_through_adapter(self) -> None:
        original = ExpectationSuite(expectations=[RowCountExpectation(exact=3)])
        restored = ExpectedAdapter.validate_json(ExpectedAdapter.dump_json(original))
        assert restored == original


@pytest.mark.unit
class TestComparisonConfig:
    def test_defaults(self) -> None:
        cfg = ComparisonConfig()
        assert cfg.row_order == "ignore"
        assert cfg.column_order == "ignore"
        assert cfg.type_equality == "ignore"
        assert cfg.null_equality == "equal"
        assert cfg.float_tolerance == 1e-9

    def test_strict_construction(self) -> None:
        cfg = ComparisonConfig(
            row_order="strict",
            column_order="strict",
            type_equality="strict",
            null_equality="distinct",
            float_tolerance=0.0,
        )
        assert cfg.row_order == "strict"
        assert cfg.null_equality == "distinct"

    def test_json_round_trip(self) -> None:
        cfg = ComparisonConfig(row_order="strict", float_tolerance=1e-6)
        restored = ComparisonConfig.model_validate_json(cfg.model_dump_json())
        assert restored == cfg

    def test_rejects_unknown_row_order(self) -> None:
        with pytest.raises(ValidationError):
            ComparisonConfig.model_validate({"row_order": "maybe"})

    def test_rejects_unknown_null_equality(self) -> None:
        with pytest.raises(ValidationError):
            ComparisonConfig.model_validate({"null_equality": "python"})

    def test_rejects_negative_float_tolerance(self) -> None:
        with pytest.raises(ValidationError):
            ComparisonConfig(float_tolerance=-1e-9)

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            ComparisonConfig.model_validate({"duplicates": "multiset"})


@pytest.mark.unit
class TestCostBudget:
    def test_default_no_limit(self) -> None:
        budget = CostBudget()
        assert budget.max_seconds is None

    def test_with_seconds(self) -> None:
        budget = CostBudget(max_seconds=30.0)
        assert budget.max_seconds == 30.0

    def test_subsecond_budget(self) -> None:
        budget = CostBudget(max_seconds=0.5)
        assert budget.max_seconds == 0.5

    def test_json_round_trip(self) -> None:
        budget = CostBudget(max_seconds=12.5)
        restored = CostBudget.model_validate_json(budget.model_dump_json())
        assert restored == budget

    def test_rejects_zero_seconds(self) -> None:
        with pytest.raises(ValidationError):
            CostBudget(max_seconds=0)

    def test_rejects_negative_seconds(self) -> None:
        with pytest.raises(ValidationError):
            CostBudget(max_seconds=-1.0)

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            CostBudget.model_validate({"max_seconds": 30.0, "max_usd": 50.0})


def _make_case(**overrides: Any) -> EvalCase:
    defaults: dict[str, Any] = {
        "id": "rock_track_count",
        "input": "How many tracks are in the 'Rock' genre?",
        "expected": ExpectedResultSet(rows=[{"count": 1297}]),
        "platform": PlatformRef(name="local", kind="duckdb"),
    }
    return EvalCase(**(defaults | overrides))


@pytest.mark.unit
class TestEvalCase:
    def test_minimal_construction(self) -> None:
        case = _make_case()
        assert case.id == "rock_track_count"
        assert case.snapshot is None
        assert case.comparison == ComparisonConfig()
        assert case.allow_data_egress is False
        assert case.cost_budget is None
        assert case.metadata == {}

    def test_full_construction(self) -> None:
        case = EvalCase(
            id="case-1",
            input="List active users",
            expected=ExpectedSQL(sql="SELECT * FROM users WHERE active"),
            platform=PlatformRef(name="warehouse", kind="snowflake"),
            snapshot=SnapshotRef(kind="timestamp", value="2026-05-23T00:00:00Z"),
            comparison=ComparisonConfig(row_order="strict"),
            allow_data_egress=True,
            cost_budget=CostBudget(max_seconds=30.0),
            metadata={"owner": "analytics", "ticket": "ANL-42"},
        )
        assert case.snapshot is not None
        assert case.comparison.row_order == "strict"
        assert case.allow_data_egress is True
        assert case.metadata["owner"] == "analytics"

    def test_accepts_expectation_suite(self) -> None:
        case = _make_case(expected=ExpectationSuite(expectations=[RowCountExpectation(exact=10)]))
        assert isinstance(case.expected, ExpectationSuite)

    def test_json_round_trip(self) -> None:
        case = _make_case()
        restored = EvalCase.model_validate_json(case.model_dump_json())
        assert restored == case

    def test_rejects_empty_id(self) -> None:
        with pytest.raises(ValidationError):
            _make_case(id="")

    def test_rejects_empty_input(self) -> None:
        with pytest.raises(ValidationError):
            _make_case(input="")

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            _make_case(typo_field="anything")

    def test_default_metadata_not_shared(self) -> None:
        case_a = _make_case()
        case_b = _make_case(id="another")
        case_a.metadata["touched"] = True
        assert case_b.metadata == {}

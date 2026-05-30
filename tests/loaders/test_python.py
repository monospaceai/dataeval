"""Unit tests for the ``@eval_case`` decorator and its dict->Expected coercion."""

import pytest
from pydantic import ValidationError

from data_eval.loaders.python import eval_case, read_eval_case
from data_eval.platforms import duckdb_platform
from data_eval.types import ComparisonConfig, ExpectedResultSet

_PLATFORM = duckdb_platform(name="local")


@pytest.mark.unit
class TestEvalCaseDecorator:
    def test_id_defaults_to_function_name(self) -> None:
        @eval_case(input="q", expected={"kind": "result_set", "rows": [{"n": 1}]}, platform=_PLATFORM)
        def test_thing(case: object) -> None: ...

        recorded = read_eval_case(test_thing)
        assert recorded is not None
        assert recorded.id == "test_thing"

    def test_explicit_id_overrides_function_name(self) -> None:
        @eval_case(input="q", expected={"kind": "result_set", "rows": [{"n": 1}]}, platform=_PLATFORM, id="custom")
        def test_thing(case: object) -> None: ...

        recorded = read_eval_case(test_thing)
        assert recorded is not None
        assert recorded.id == "custom"

    def test_dict_expected_is_coerced_to_typed_model(self) -> None:
        @eval_case(input="q", expected={"kind": "result_set", "rows": [{"n": 1}]}, platform=_PLATFORM)
        def test_thing(case: object) -> None: ...

        recorded = read_eval_case(test_thing)
        assert recorded is not None
        assert isinstance(recorded.expected, ExpectedResultSet)
        assert recorded.expected.rows == [{"n": 1}]

    def test_typed_expected_passes_through(self) -> None:
        expected = ExpectedResultSet(rows=[{"n": 1}])

        @eval_case(input="q", expected=expected, platform=_PLATFORM)
        def test_thing(case: object) -> None: ...

        recorded = read_eval_case(test_thing)
        assert recorded is not None
        assert recorded.expected == expected

    def test_metadata_and_comparison_are_forwarded(self) -> None:
        comparison = ComparisonConfig(float_tolerance=0.5)

        @eval_case(
            input="q",
            expected={"kind": "result_set", "rows": [{"n": 1}]},
            platform=_PLATFORM,
            metadata={"owner": "alex"},
            comparison=comparison,
        )
        def test_thing(case: object) -> None: ...

        recorded = read_eval_case(test_thing)
        assert recorded is not None
        assert recorded.metadata == {"owner": "alex"}
        assert recorded.comparison.float_tolerance == 0.5

    def test_malformed_dict_raises_at_decoration_time(self) -> None:
        # An unknown discriminator value fails loudly when the module is imported/collected,
        # not lazily at test-run time.
        with pytest.raises(ValidationError):
            eval_case(input="q", expected={"kind": "not_a_real_kind"}, platform=_PLATFORM)

    def test_decorator_returns_the_function_unchanged(self) -> None:
        def original(case: object) -> None: ...

        decorated = eval_case(input="q", expected={"kind": "result_set", "rows": [{"n": 1}]}, platform=_PLATFORM)(
            original
        )
        assert decorated is original

    def test_read_eval_case_returns_none_for_undecorated_function(self) -> None:
        def plain(case: object) -> None: ...

        assert read_eval_case(plain) is None

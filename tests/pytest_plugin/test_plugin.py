"""Tests for the data-eval pytest plugin's ``case`` fixture, exercised via ``pytester``.

These run an inline pytest session (in-process, so the entry-point-registered plugin is
active) to prove the fixture is available with zero conftest setup and that requesting
``case`` without ``@eval_case`` fails with a clear message.
"""

import pytest

pytest_plugins = ["pytester"]


@pytest.mark.unit
def test_case_fixture_injects_the_decorated_case(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        from data_eval import eval_case
        from data_eval.platforms import duckdb_platform

        @eval_case(
            input="q",
            expected={"kind": "result_set", "rows": [{"n": 1}]},
            platform=duckdb_platform(name="p"),
        )
        def test_injected(case):
            assert case.id == "test_injected"
            assert case.input == "q"
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)


@pytest.mark.unit
def test_case_fixture_without_decorator_errors_clearly(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        def test_missing_decorator(case):
            assert case is not None
        """
    )
    result = pytester.runpytest()
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*not*decorated with @eval_case*"])

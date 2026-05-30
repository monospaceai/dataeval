"""``@eval_case``: the Python authoring decorator for test cases.

Decorates a ``def test_x(case): ...`` function with the declarative parts of an
``EvalCase`` (input, expected outcome, platform, optional id/metadata/comparison). It
builds the ``EvalCase`` eagerly — at decoration time, i.e. when pytest imports the test
module during collection — and stashes it for the pytest plugin's ``case`` fixture to
inject. The function itself is returned **unchanged** (no wrapping): wrapping a test
function breaks pytest's fixture-signature introspection, so we never do it.

``expected`` accepts either a typed ``Expected`` instance or a plain ``dict`` (the §9
ergonomic, e.g. ``{"kind": "result_set", "rows": [{"count": 1297}]}``). A dict is coerced
to the discriminated ``Expected`` union via a reused module-level ``TypeAdapter``. The
decorator's parameter is widened to ``dict | Expected`` precisely so static checkers (ty)
accept both a dict literal and a typed instance at the call site, while ``EvalCase`` stores
only the typed value. A malformed dict raises ``pydantic.ValidationError`` right there at
collection — a typo in test source is programmer error, surfaced loudly (matching Inspect
AI), not an errors-as-value (which we reserve for *runtime* solver/platform failures).

The decorated function is recorded in a ``WeakKeyDictionary`` keyed by the function object
(not an attribute on the function), so resolution is identity-based and type-clean.
"""

from collections.abc import Callable
from typing import Any, TypeVar
from weakref import WeakKeyDictionary

from pydantic import TypeAdapter

from data_eval.types import ComparisonConfig, EvalCase, Expected, PlatformRef

_TestFn = TypeVar("_TestFn", bound=Callable[..., Any])

# Reused per Pydantic's guidance — building a TypeAdapter compiles a core schema, so we
# do it once. Validates a dict into the discriminated ``Expected`` union (dispatch on "kind").
_EXPECTED_ADAPTER: TypeAdapter[Expected] = TypeAdapter(Expected)

# Function object -> its EvalCase. Weak keys so a collected test function that goes away
# takes its entry with it; identity lookup matches what pytest passes as ``request.function``.
_CASES: WeakKeyDictionary[Callable[..., Any], EvalCase] = WeakKeyDictionary()


def eval_case(
    *,
    input: str,
    expected: dict[str, Any] | Expected,
    platform: PlatformRef,
    id: str | None = None,
    metadata: dict[str, Any] | None = None,
    comparison: ComparisonConfig | None = None,
) -> Callable[[_TestFn], _TestFn]:
    """Attach an ``EvalCase`` to a test function for the ``case`` fixture to inject.

    Args:
        input: The natural-language question / instruction under test.
        expected: The expected outcome — a typed ``Expected`` or a dict coerced to one.
        platform: A ``PlatformRef`` (build one with ``duckdb_platform`` / ``postgres_platform``).
        id: Case identifier; defaults to the decorated function's name.
        metadata: Optional free-form tags/owner/source metadata.
        comparison: Optional result-set comparison rules; defaults to ``ComparisonConfig()``.

    Returns:
        A decorator that records the case and returns the function unchanged.
    """
    coerced: Expected = _EXPECTED_ADAPTER.validate_python(expected) if isinstance(expected, dict) else expected

    def decorator(func: _TestFn) -> _TestFn:
        extra: dict[str, Any] = {}
        if metadata is not None:
            extra["metadata"] = metadata
        if comparison is not None:
            extra["comparison"] = comparison
        _CASES[func] = EvalCase(
            id=id or getattr(func, "__name__", ""),
            input=input,
            expected=coerced,
            platform=platform,
            **extra,
        )
        return func

    return decorator


def read_eval_case(func: Callable[..., Any]) -> EvalCase | None:
    """Return the ``EvalCase`` attached to ``func`` by ``@eval_case``, or ``None``."""
    return _CASES.get(func)

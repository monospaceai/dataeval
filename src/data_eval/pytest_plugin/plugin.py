"""The data-eval pytest plugin: the ``case`` fixture + session-end adapter cleanup.

Loaded automatically via the ``pytest11`` entry point declared in ``pyproject.toml`` — so
``pytest tests/`` "just works" with zero conftest ceremony (design principle 4). The plugin
is deliberately side-effect-free: importing it does nothing, and its only contributions are
the ``case`` fixture (active only for tests that request it) and a ``pytest_sessionfinish``
hook that closes any adapters resolved during the run. With no ``@eval_case`` / ``assert_eval``
usage the cache is empty and teardown is a no-op — so the plugin imposes nothing on unrelated
projects that merely have data-eval installed (avoiding the DeepEval-style always-on plugin).
"""

import pytest

from data_eval.loaders.python import read_eval_case
from data_eval.platforms.registry import close_all
from data_eval.types import EvalCase


@pytest.fixture
def case(request: pytest.FixtureRequest) -> EvalCase:
    """Inject the ``EvalCase`` attached by ``@eval_case`` on the requesting test function."""
    evalcase = read_eval_case(request.function)
    if evalcase is None:
        msg = (
            f"test {request.function.__name__!r} requests the 'case' fixture but is not decorated with @eval_case(...)"
        )
        raise pytest.UsageError(msg)
    return evalcase


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Close every adapter resolved from a ``PlatformRef`` during the session."""
    close_all()

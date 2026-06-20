"""Shared pytest fixtures for evaldata's own test suite."""

from collections.abc import Iterator

import pytest

from evaldata.platforms.registry import close_all
from evaldata.reporting.collector import clear


@pytest.fixture(autouse=True)
def _reset_global_state() -> Iterator[None]:
    """Clear the adapter cache and recorded case outcomes after each test, isolating tests."""
    yield
    close_all()
    clear()

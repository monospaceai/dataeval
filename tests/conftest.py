"""Shared pytest fixtures for dataeval's own test suite."""

from collections.abc import Iterator

import pytest

from dataeval.platforms.registry import close_all
from dataeval.reporting.collector import clear


@pytest.fixture(autouse=True)
def _reset_global_state() -> Iterator[None]:
    """Clear the adapter cache and recorded case outcomes after each test, isolating tests."""
    yield
    close_all()
    clear()

"""Shared pytest fixtures for data-eval's own test suite."""

from collections.abc import Iterator

import pytest

from data_eval.platforms.registry import close_all


@pytest.fixture(autouse=True)
def _clear_platform_cache() -> Iterator[None]:
    """Close and clear the session adapter cache after each test, isolating resolution tests.

    In production the plugin closes the cache once at session end; for our own suite we
    clear it per test so cached adapters (and ``PlatformRef.name`` bindings) never leak
    across tests.
    """
    yield
    close_all()

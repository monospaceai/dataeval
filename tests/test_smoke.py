"""Smoke test — the package imports."""

import pytest

import dataeval

pytestmark = pytest.mark.unit


def test_package_imports() -> None:
    assert dataeval is not None

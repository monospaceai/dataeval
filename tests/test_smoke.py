"""Smoke test — the package imports."""

import pytest

import evaldata

pytestmark = pytest.mark.unit


def test_package_imports() -> None:
    assert evaldata is not None

"""Tests for reading and validating dbt artifacts."""

import json
from pathlib import Path
from typing import Any

import pytest

from evaldata.dbt.artifacts import Artifacts, read_artifacts
from evaldata.dbt.errors import DbtError

pytestmark = pytest.mark.unit

FIXTURE_ARTIFACTS = Path(__file__).parent / "fixtures" / "jaffle_duckdb" / "artifacts"


def _write_target(tmp_path: Path, *, manifest: Any, catalog: Any = None) -> Path:
    """Write `manifest`/`catalog` (already JSON-serialisable, or a raw string) into a target dir."""
    target = tmp_path / "target"
    target.mkdir()
    manifest_text = manifest if isinstance(manifest, str) else json.dumps(manifest)
    (target / "manifest.json").write_text(manifest_text, encoding="utf-8")
    if catalog is not None:
        catalog_text = catalog if isinstance(catalog, str) else json.dumps(catalog)
        (target / "catalog.json").write_text(catalog_text, encoding="utf-8")
    return target


def _valid_manifest(**overrides: Any) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "metadata": {"dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json"},
        "nodes": {},
        "sources": {},
    }
    manifest.update(overrides)
    return manifest


def test_reads_fixture_artifacts() -> None:
    result = read_artifacts(FIXTURE_ARTIFACTS)
    assert isinstance(result, Artifacts)
    assert result.schema_version == "v12"
    assert "model.jaffle_duckdb.customers" in result.manifest["nodes"]
    assert result.catalog is not None
    assert "model.jaffle_duckdb.customers" in result.catalog["nodes"]


def test_missing_manifest_is_target_not_found(tmp_path: Path) -> None:
    result = read_artifacts(tmp_path)
    assert isinstance(result, DbtError)
    assert result.kind == "target_not_found"


def test_malformed_manifest_json_is_invalid(tmp_path: Path) -> None:
    target = _write_target(tmp_path, manifest="{not json")
    result = read_artifacts(target)
    assert isinstance(result, DbtError)
    assert result.kind == "artifact_invalid"
    assert result.cause is not None


def test_manifest_not_an_object_is_invalid(tmp_path: Path) -> None:
    target = _write_target(tmp_path, manifest=[1, 2, 3])
    result = read_artifacts(target)
    assert isinstance(result, DbtError)
    assert result.kind == "artifact_invalid"


def test_manifest_without_metadata_is_invalid(tmp_path: Path) -> None:
    target = _write_target(tmp_path, manifest={"nodes": {}, "sources": {}})
    result = read_artifacts(target)
    assert isinstance(result, DbtError)
    assert result.kind == "artifact_invalid"


def test_manifest_without_schema_version_is_invalid(tmp_path: Path) -> None:
    target = _write_target(tmp_path, manifest={"metadata": {}, "nodes": {}, "sources": {}})
    result = read_artifacts(target)
    assert isinstance(result, DbtError)
    assert result.kind == "artifact_invalid"


def test_unsupported_schema_version_is_rejected(tmp_path: Path) -> None:
    manifest = _valid_manifest(metadata={"dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v9.json"})
    target = _write_target(tmp_path, manifest=manifest)
    result = read_artifacts(target)
    assert isinstance(result, DbtError)
    assert result.kind == "unsupported_schema_version"
    assert "v9" in result.message


def test_accepts_fusion_v20_schema(tmp_path: Path) -> None:
    # Fusion emits schema v20, which dbt documents as identical in shape to v12.
    manifest = json.loads((FIXTURE_ARTIFACTS / "manifest.json").read_text(encoding="utf-8"))
    manifest["metadata"]["dbt_schema_version"] = "https://schemas.getdbt.com/dbt/manifest/v20.json"
    target = _write_target(tmp_path, manifest=manifest)
    result = read_artifacts(target)
    assert isinstance(result, Artifacts)
    assert result.schema_version == "v20"


def test_unparseable_schema_version_is_rejected(tmp_path: Path) -> None:
    manifest = _valid_manifest(metadata={"dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/main.json"})
    target = _write_target(tmp_path, manifest=manifest)
    result = read_artifacts(target)
    assert isinstance(result, DbtError)
    assert result.kind == "unsupported_schema_version"


def test_missing_catalog_degrades_to_none(tmp_path: Path) -> None:
    target = _write_target(tmp_path, manifest=_valid_manifest())
    result = read_artifacts(target)
    assert isinstance(result, Artifacts)
    assert result.catalog is None


def test_malformed_catalog_json_is_invalid(tmp_path: Path) -> None:
    target = _write_target(tmp_path, manifest=_valid_manifest(), catalog="{not json")
    result = read_artifacts(target)
    assert isinstance(result, DbtError)
    assert result.kind == "artifact_invalid"

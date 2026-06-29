"""Resolve a dbt profile target to an evaldata `PlatformRef`."""

from pathlib import Path
from typing import Any

from evaldata.dbt._yaml import read_yaml
from evaldata.dbt.errors import DbtError
from evaldata.platforms.registry import duckdb_platform, postgres_platform
from evaldata.types import PlatformRef


def _read_mapping(path: Path) -> dict[str, Any] | DbtError:
    data = read_yaml(path, not_found="profile_not_found", invalid="profile_not_found")
    if isinstance(data, DbtError):
        return data
    if not isinstance(data, dict):
        return DbtError(kind="profile_not_found", message=f"{path} is not a YAML mapping")
    return data


def _pg_conninfo(output: dict[str, Any]) -> str:
    parts = []
    for field in ("host", "port", "dbname", "user"):
        value = output.get(field)
        if value is not None:
            parts.append(f"{field}={value}")
    return " ".join(parts)


def _platform_from_output(name: str, output: dict[str, Any], project_dir: Path) -> PlatformRef | DbtError:
    adapter = output.get("type")
    if adapter == "duckdb":
        path = output.get("path", ":memory:")
        if path != ":memory:" and not Path(path).is_absolute():
            path = str(project_dir / path)
        return duckdb_platform(name=name, path=path)
    if adapter == "postgres":
        return postgres_platform(name=name, conninfo=_pg_conninfo(output))
    return DbtError(kind="unsupported_adapter", message=f"dbt adapter {adapter!r} has no evaldata platform")


def platform_from_profile(
    project_dir: str | Path,
    *,
    profiles_dir: str | Path | None = None,
    target: str | None = None,
) -> PlatformRef | DbtError:
    """Resolve a dbt project's profile target to a `PlatformRef`.

    Reads the project's `dbt_project.yml` for its `profile`, then the matching entry in
    `profiles.yml` (in `profiles_dir`, defaulting to `project_dir`), and maps the selected
    output's warehouse type to an evaldata platform. Supports the `duckdb` and `postgres`
    adapters; a duckdb `path` is resolved relative to `project_dir`. The Postgres conninfo
    carries `host`/`port`/`dbname`/`user`; the password is left to libpq (`PGPASSWORD`,
    `.pgpass`).

    Args:
        project_dir: The dbt project directory (holding `dbt_project.yml`).
        profiles_dir: Directory holding `profiles.yml`; defaults to `project_dir`.
        target: The profile target (output) name; defaults to the profile's `target`.

    Returns:
        A `PlatformRef` for the selected target, or a `DbtError` if the project or profile
        cannot be resolved (`profile_not_found`) or the warehouse type is unsupported
        (`unsupported_adapter`).
    """
    project_dir = Path(project_dir)
    project = _read_mapping(project_dir / "dbt_project.yml")
    if isinstance(project, DbtError):
        return project
    profile_name = project.get("profile")
    if not isinstance(profile_name, str):
        return DbtError(kind="profile_not_found", message=f"dbt_project.yml in {project_dir} has no 'profile'")

    profiles_root = Path(profiles_dir) if profiles_dir is not None else project_dir
    profiles = _read_mapping(profiles_root / "profiles.yml")
    if isinstance(profiles, DbtError):
        return profiles

    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        return DbtError(kind="profile_not_found", message=f"profile {profile_name!r} not found in profiles.yml")
    outputs = profile.get("outputs")
    if not isinstance(outputs, dict):
        return DbtError(kind="profile_not_found", message=f"profile {profile_name!r} has no outputs")

    target_name = target or profile.get("target")
    output = outputs.get(target_name) if isinstance(target_name, str) else None
    if not isinstance(output, dict):
        return DbtError(
            kind="profile_not_found", message=f"target {target_name!r} not found in profile {profile_name!r}"
        )

    return _platform_from_output(f"dbt:{profile_name}:{target_name}", output, project_dir)

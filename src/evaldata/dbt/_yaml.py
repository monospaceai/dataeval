"""YAML reading for dbt config and gold-case files (needs the `dbt` extra: pyyaml)."""

from pathlib import Path
from typing import Any

from evaldata.dbt.errors import DbtError, DbtErrorKind


def read_yaml(path: Path, *, not_found: DbtErrorKind, invalid: DbtErrorKind) -> Any | DbtError:
    """Parse the YAML document at `path`.

    Args:
        path: The file to read.
        not_found: The `DbtError.kind` to return when `path` does not exist.
        invalid: The `DbtError.kind` to return when `path` cannot be read or parsed.

    Returns:
        The parsed YAML value, or a `DbtError` if the file is missing or unparseable.
    """
    import yaml

    if not path.is_file():
        return DbtError(kind=not_found, message=f"no file at {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        return DbtError(kind=invalid, message=f"could not parse {path}: {e}", cause=e)

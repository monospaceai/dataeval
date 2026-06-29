#!/usr/bin/env bash
# Regenerate the committed dbt artifacts for the jaffle_duckdb fixture.
#
# dbt writes to the gitignored target/; this copies the two artifacts the tests read into the
# committed artifacts/ directory. Run only when the fixture project changes.
# Requires the `fixtures` dependency group (dbt-duckdb): `uv run --group fixtures bash regen.sh`.
set -euo pipefail
cd "$(dirname "$0")"
export DBT_PROFILES_DIR="$PWD"

rm -f jaffle.duckdb
rm -rf target logs dbt_packages

# Sources are not DAG-linked to the seeds that populate them, so seed before run (a single
# threaded `dbt build` can otherwise race the staging views ahead of the seed inserts).
dbt seed --profiles-dir "$PWD"
dbt run --profiles-dir "$PWD"
dbt docs generate --profiles-dir "$PWD"

mkdir -p artifacts
cp target/manifest.json target/catalog.json artifacts/
rm -f .user.yml

# Normalise volatile/identifying metadata so the committed artifacts are deterministic.
python - <<'PY'
import json
import pathlib

placeholders = {
    "user_id": None,
    "invocation_id": "00000000-0000-0000-0000-000000000000",
    "invocation_started_at": "1970-01-01T00:00:00.000000+00:00",
    "generated_at": "1970-01-01T00:00:00.000000Z",
    "run_started_at": "1970-01-01T00:00:00.000000+00:00",
}
for name in ("manifest.json", "catalog.json"):
    path = pathlib.Path("artifacts") / name
    doc = json.loads(path.read_text())
    metadata = doc.get("metadata", {})
    for key, value in placeholders.items():
        if key in metadata:
            metadata[key] = value
    path.write_text(json.dumps(doc))
PY

echo "regenerated: artifacts/manifest.json, artifacts/catalog.json, jaffle.duckdb"

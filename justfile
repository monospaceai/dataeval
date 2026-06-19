test *args:
    uv run --all-extras pytest {{args}}

test-cov *args:
    uv run coverage erase
    uv run --all-extras coverage run -m pytest {{args}}
    uv run coverage combine
    uv run coverage report

# `cloud` e2e against credentialed hosted backends (Databricks, …). Needs secrets in the env;
# run in a fork-gated CI job, not part of the default `check`.
test-cloud *args:
    uv run --all-extras pytest -m cloud {{args}}

lint:
    uv run ruff check
    uv run ruff format --check

fix:
    uv run ruff check --fix
    uv run ruff format

typecheck:
    uv run --all-extras ty check src examples

precommit:
    uv run pre-commit run --all-files --show-diff-on-failure

build:
    uv build

# Everyday gate: excludes `cloud` (those run in their own fork-gated CI job).
check: lint typecheck
    just test-cov '-m "not cloud"'

ci: check build

release *args="auto":
    changie batch {{args}}
    changie merge

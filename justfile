test *args:
    uv run pytest {{args}}

test-cov *args:
    uv run coverage erase
    uv run --extra postgres coverage run -m pytest {{args}}
    uv run coverage combine
    uv run coverage report

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

check: lint typecheck test-cov

ci: check build

release *args="auto":
    changie batch {{args}}
    changie merge

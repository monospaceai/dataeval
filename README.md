# data-eval

AI evals framework for data & analytics engineering teams.

> Status: pre-alpha. The API will change.

## Install (once published)

```bash
uv add data-eval                              # core
uv add "data-eval[snowflake]"                 # + Snowflake adapter
uv add "data-eval[all-platforms,litellm]"     # everything
```

## Develop locally

```bash
git clone https://github.com/code-alexander/data-eval.git
cd data-eval
uv sync                       # core + dev tooling
uv run pre-commit install
uv run pytest                 # tests (add --cov=data_eval for coverage)
uv run ruff check && uv run ruff format --check
uv run --all-extras ty check  # typecheck with every adapter driver installed
```

### Platform e2e tests

Adapter conformance for real platforms is marked `e2e` and skips when the platform
isn't reachable, so the default `uv run pytest` is green without one. To run the
Postgres suite locally:

```bash
docker compose up -d                  # postgres:17 on localhost:5432
uv run --extra postgres pytest -m e2e # connection via POSTGRES_TEST_* env (defaults match compose)
```

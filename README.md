# evaldata

[![CI](https://github.com/monospaceai/evaldata/actions/workflows/ci.yml/badge.svg)](https://github.com/monospaceai/evaldata/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://github.com/monospaceai/evaldata/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

**The evaluation framework for AI-generated SQL.**

Evaluate AI-generated SQL in your warehouse and catch regressions when prompts, models, or code change.

Pytest-native. CI-friendly. Built for data teams.

## Install

```bash
uv add evaldata                # core (includes the DuckDB adapter)
uv add "evaldata[postgres]"    # + Postgres adapter
uv add "evaldata[databricks]"  # + Databricks adapter
uv add "evaldata[litellm]"     # + litellm, to call a model as the AI under test
```

DuckDB, Postgres, and Databricks are the adapters available today. Snowflake and
BigQuery are planned.

## Examples

Runnable examples in [`examples/`](examples/):

| Example | Shows |
| --- | --- |
| [Deterministic](examples/01_deterministic/test_golden_questions.py) | Every expected-type and scorer with fixed SQL — no model or network |
| [Local AI](examples/02_local_ai/test_text_to_sql.py) | A self-hosted Ollama model as the AI under test, via litellm |
| [Hosted AI](examples/03_hosted_ai/test_text_to_sql.py) | Hosted-model plumbing, mocked so it runs without a live call or key |

See [`examples/README.md`](examples/README.md) for details.

## Develop locally

```bash
git clone https://github.com/monospaceai/evaldata.git
cd evaldata
uv sync                       # core + dev tooling
uv run pre-commit install
just check                    # lint + typecheck + tests with coverage (runs everything)
```

`just check` runs lint, typecheck, and tests with coverage (held at 100%). See the
`justfile` for the full set of commands.

### Platform e2e tests

Adapter conformance for real platforms is marked `e2e`. CI provisions Postgres as a
service container and runs the suite on every push, so the Postgres adapter is exercised
against a real engine on every change.

Run it locally against Postgres with:

```bash
docker compose up -d                  # postgres:17 on localhost:5432
uv run --extra postgres pytest -m e2e # connection via POSTGRES_TEST_* env (defaults match compose)
```

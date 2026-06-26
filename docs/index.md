# evaldata

Evaluate AI-generated SQL in your warehouse and catch regressions when prompts, models, or code change.

Pytest-native. CI-friendly. Built for data teams.

## Install

```bash
uv add evaldata                # core (includes the DuckDB adapter)
uv add "evaldata[postgres]"    # + Postgres adapter
uv add "evaldata[databricks]"  # + Databricks adapter
uv add "evaldata[litellm]"     # + litellm, to call a model as the AI under test
```

DuckDB, Postgres, and Databricks are the adapters available today. Snowflake and BigQuery
adapters are planned.

## Where to go next

- **[Getting started](getting-started.md)** — write and run your first eval in a few minutes.
- **Guides** — evaluate [a local Ollama model](guides/local-ollama.md),
  [a hosted model](guides/hosted-model.md), or [against Databricks](guides/databricks.md); check
  [semantic equivalence](guides/semantic-equivalence.md) or [score with an LLM judge](guides/llm-judge.md).
- **[Concepts](concepts.md)** — the building blocks: cases, solvers, scorers, platforms.
- **[API reference](reference/index.md)** — the public API, generated from docstrings.

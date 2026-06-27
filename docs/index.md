# evaldata

**The evaluation framework for AI-generated SQL.**
`pytest`-native. CI-friendly. Built for data teams.

`evaldata` catches regressions on every prompt and model change, before they reach production.

## Why evaldata

`evaldata` can prove two queries are equivalent without executing them or asking an LLM
to judge.

MLflow, Ragas, and DeepEval reach for an LLM even when the answer is exact and provable
— a slow, costly guess at something you can settle for free.

- **Semantic equivalence.** Confirm two queries have the same meaning by comparing their
  structure. No execution, no guessing — when it can't confirm, it returns `unknown`.
- **Execution in your warehouse.** Run the query on DuckDB, Postgres, or Databricks and
  compare the results, accounting for row order, NULLs, float tolerance, and types.
- **It's just `pytest`.** Every eval is a test, run in your suite and your CI on every PR.
  No new runner, notebook, or dashboard.
- **An LLM judge when you need one.** For ambiguous questions, missing reference answers,
  or an explanation to grade: the right tool for the job, fully supported.

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
- **Guides** — [semantic equivalence](guides/semantic-equivalence.md), [LLM judge](guides/llm-judge.md), [a local Ollama model](guides/local-ollama.md), [a hosted model](guides/hosted-model.md), [Databricks](guides/databricks.md).
- **[Concepts](concepts.md)** — the building blocks: cases, solvers, scorers, platforms.
- **[API reference](reference/index.md)** — the public API, generated from docstrings.

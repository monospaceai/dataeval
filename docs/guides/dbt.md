# Evaluate against a dbt project

Point evaldata at a built [dbt](https://www.getdbt.com/) project and a set of golden questions
to measure **execution accuracy (EX)** — the fraction of questions where the model's SQL returns
the same rows as the gold query.

evaldata reads the project's compiled artifacts (`manifest.json` and `catalog.json`) for the
table and column schema and warehouse connection. It runs against your own warehouse
(DuckDB, Postgres, …) with no dbt Cloud account.

## Prerequisites

- Install the dbt extra: `pip install evaldata[dbt]`.
- A built dbt project. Compile it and generate its catalog so `target/` holds both artifacts:

  ```bash
  dbt build          # or: dbt compile
  dbt docs generate  # writes catalog.json with resolved column types
  ```

  `catalog.json` is optional — without it, evaldata uses the column types declared in your model
  YAML instead of the resolved warehouse types.

## Write golden questions

A golds file is a YAML (or JSON) list of questions paired with the SQL whose result is the
correct answer:

```yaml
# golds.yml
- question: How many customers placed an order in 2024?
  gold_sql: |
    select count(distinct customer_id) as n
    from customers
    where first_order >= '2024-01-01'
  select: [customers]   # optional: scope the schema shown to the model

- question: What is total revenue by month?
  gold_sql: select date_trunc('month', ordered_at) as month, sum(amount) as revenue from orders group by 1
```

Each entry needs a `question` and a `gold_sql`. Optionally set `select` to limit the schema
context to specific tables, and `id` to name the case.

## Run the benchmark

```bash
evaldata dbt-bench path/to/dbt_project --model openai/gpt-4o-mini --golds golds.yml
```

evaldata resolves the warehouse from the project's dbt profile, injects the schema into the
prompt, runs the model against each question, compares results, and prints the EX:

```
EX (dbt): 72.0% (18/25)
```

`--model` is any [litellm](https://docs.litellm.ai/docs/providers) model id. Useful options:

- `--mode model` — skip the golds file and build a case from every documented model, using the
  model's description as the question and its compiled SQL as the gold answer.
- `--target-dir DIR` — where the artifacts live, if not `<project>/target`.
- `--profiles-dir DIR` / `--target NAME` — locate and select the dbt profile target.
- `--limit N` — run only the first `N` cases.
- `--json PATH` — also write the scores and every case's result to a JSON file.

## Check the connection

Confirm evaldata can resolve and reach the project's warehouse:

```bash
evaldata doctor --dbt-project path/to/dbt_project
```

## How it works

- The warehouse comes from the project's dbt profile. `duckdb` and `postgres` targets are
  supported; the duckdb path is resolved relative to the project.
- The schema in the prompt is the project's sources and models, rendered as `CREATE TABLE`
  statements with column types from `catalog.json` and descriptions from your model YAML.
- Scoring is `ExecutionAccuracy` with order-insensitive set semantics: a case passes when the
  model's SQL and the gold SQL return the same rows.

## In pytest

To run dbt evals as ordinary pytest tests — with your own prompt, a fine-tune, an agent, or a
different scorer — load the cases and drive them yourself:

```python
import pytest

from evaldata import ExecutionAccuracy, assert_eval
from evaldata.dbt import load_dbt, platform_from_profile
from evaldata.solvers import SCHEMA_PROMPT_TEMPLATE, PromptSolver

platform = platform_from_profile("path/to/dbt_project")
cases = load_dbt("path/to/dbt_project/target", platform=platform, golds="golds.yml")


@pytest.mark.parametrize("case", cases, ids=lambda case: case.id)
def test_dbt_question(case):
    solver = PromptSolver("openai/gpt-4o-mini", prompt_template=SCHEMA_PROMPT_TEMPLATE)
    assert_eval(case, solver, scorers=[ExecutionAccuracy(row_order="ignore", multiplicity="set")])
```

`load_dbt` and `platform_from_profile` return a `DbtError` when the project cannot be read;
check for it before iterating. The cases are ordinary `EvalCase` objects and can be scored with
any scorer.

## Next steps

- [Concepts](../concepts.md) — solvers, scorers, and expected types in depth.
- [Scorers reference](../reference/scorers.md) — `ExecutionAccuracy` and its options.
- [dbt reference](../reference/dbt.md) — `DbtContext`, `load_dbt`, and `platform_from_profile`.

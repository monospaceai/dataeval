# Check semantic equivalence

There are many ways to write the same query. `SemanticEquivalence` checks whether the
AI's SQL *means* the same thing as a gold query rather than whether the syntax is identical.

For example, in each row below the AI's SQL has the same meaning as the gold query:

| Gold query | AI's SQL | Same meaning because |
| --- | --- | --- |
| `SELECT amount + 1` | `SELECT 1 + amount` | `+` is commutative |
| `WHERE x IN (1, 2)` | `WHERE x IN (2, 1)` | `IN`-list order doesn't matter |
| `WHERE country = 'US' AND id > 1` | `WHERE id > 1 AND country = 'US'` | `AND` operands reorder freely |
| `WHERE id > 1` | `WHERE 1 < id` | `<` is the converse of `>` |

## Two ways to establish equivalence

Equivalence can be shown two ways, with opposite strengths:

- **By reasoning about the queries** — `SemanticEquivalence` compares their structure without
  running them. It *proves* a match holds on every dataset; but when it can't see why two queries
  match it returns `unknown`, never *unequal* — the next dataset might be the one that tells them
  apart.
- **By running the queries** — `ResultSetEquivalence` executes both and compares the rows. It can
  *refute* a match with a diff, but a match *observed* on one dataset is evidence, not proof.

So `SemanticEquivalence` returns one of two verdicts per check — `equivalent` (confirmed) or
`unknown` (could not confirm) — and can never falsely reject a correct query. Today it ships one
check:

- **`AstEquivalence`** — parses both queries, normalizes their syntax trees, and compares them.
  Matching trees mean the queries are equivalent, decided without running either query.
  Differing trees are inconclusive, so it returns `unknown`.

It runs its checks in order and stops at the first that confirms. If none confirm, the result is
inconclusive, with the explanation `"no semantic check could confirm equivalence"`.

The expected outcome must be a [`GoldQuery`][evaldata.types.GoldQuery]: equivalence compares one
query against another, so there must be a reference query.

## What the syntax check normalizes

`AstEquivalence` confirms equivalences that hold regardless of the data, by rewriting both
trees into a canonical form before comparing. It normalizes:

- commutative and associative operators (`AND`, `OR`, the bitwise operators, `+`, `*`) —
  operands are reordered and re-associated;
- `IN`-list order;
- comparison direction (`1 < id` becomes `id > 1`);
- constant expressions (`id > 2 - 1` folds to `id > 1`);
- identifier casing.

Equivalences that depend on the query's shape rather than its operators fall through: wrapping a
query in a CTE or a subquery, or a different join shape, produces a different tree even when the
results are identical. The syntax check returns `unknown` on those.

## Non-determinism

A query whose result is not a function of its inputs cannot be compared on syntax: two textually
identical `SELECT current_timestamp` queries return different values each run. `AstEquivalence`
detects non-deterministic calls — `rand()`, `current_timestamp`, `uuid()`, and similar — and
returns `unknown` rather than risk a false confirmation.

## Compose with execution: `observed_equivalence`

On its own, `SemanticEquivalence` either confirms or is inconclusive. To *decide* the cases it
can't confirm, pair it with execution. `observed_equivalence()` does exactly that: it confirms by
structure when it can, and otherwise runs both queries and diffs the results.

```python
from evaldata import observed_equivalence

scorer = observed_equivalence()
```

`observed_equivalence()` is a `FirstDecisive` over two scorers:

1. `SemanticEquivalence` — compares the queries; it confirms or returns `unknown`. A structural
   confirmation passes immediately and execution is skipped.
2. `ResultSetEquivalence` — runs both queries and diffs the result sets under the case's
   `ComparisonConfig`. Equal result sets pass; a difference fails and carries the diff. This is
   the layer that can refute.

`FirstDecisive` is the generic combinator behind this: it runs member scorers in order and
returns the first that passes, else the last (so the last member's diagnostics, such as a diff,
surface). Note that [`assert_eval`](../reference/eval.md) **ANDs** the scorers you pass it — a
case passes only when *every* scorer passes. A "first that passes wins" fallback is the opposite
shape, so it needs a combinator: pass `observed_equivalence()` (a single scorer) rather than the
two scorers separately.

```python
from evaldata import FirstDecisive, ResultSetEquivalence, SemanticEquivalence

# observed_equivalence() is shorthand for:
FirstDecisive([SemanticEquivalence(), ResultSetEquivalence()])
```

When you can't run the queries — no warehouse, or a result that depends on live data — its
sibling `judged_equivalence(model)` keeps the structural confirmation but replaces the execution
member with an LLM judge that grades whether the two queries are equivalent:

```python
from evaldata import judged_equivalence

scorer = judged_equivalence("openai/gpt-4o-mini")
```

The result of a `FirstDecisive` carries a `metadata["first_decisive"]` trail — one
`{"scorer", "passed", "verdict"}` entry per member that ran — so you can see which layer decided.

## Comparison options

The execution member, `ResultSetEquivalence`, diffs result sets under the case's
[`ComparisonConfig`][evaldata.types.ComparisonConfig]:

- **`column_order`** — `"ignore"` (default) compares columns by name; `"strict"` also requires
  the same column order.
- **`null_equality`** — `"equal"` (default) treats two NULLs as matching; `"distinct"` treats
  them as different (and requires a `match_key`).
- **`float_tolerance`** — the absolute tolerance for numeric columns; values within it compare
  as equal.
- **`match_key`** — when set, rows are aligned on these key columns and compared per column,
  reporting which columns differ; when empty, rows are compared as an unordered bag.

The syntax check ignores these options — it decides on query structure, not on data.

## Write the eval

```python
--8<-- "examples/01_deterministic/test_semantic_equivalence.py"
```

The composite cases read back the `metadata["first_decisive"]` trail to show which layer
decided; the case that only compares the queries reads back `metadata["verdicts"]`:

- **Confirmed by syntax, no query run** — the AI reorders the `AND` predicates and changes
  casing; the trees match and only `("semantic_equivalence", True)` is in the trail.
- **Confirmed by execution** — the AI wraps the query in a CTE; the syntax check returns `unknown`
  and the execution member confirms, so the trail is `semantic_equivalence` (inconclusive) then
  `result_set_equivalence` (pass).
- **Refuted by execution** — the AI filters on the wrong country; the syntax check returns `unknown`
  and the execution member refutes with a diff of the differing rows.
- **Inconclusive on non-determinism** — `current_timestamp` cannot be compared on syntax; with
  `SemanticEquivalence` alone, nothing decides and the result is inconclusive.

## Run it

```bash
uv run pytest test_semantic_equivalence.py -q
```

!!! tip "Run it from a clone"
    This is the bundled `examples/01_deterministic/test_semantic_equivalence.py` example. If
    you've cloned the repo, run it directly with
    `uv run pytest examples/01_deterministic/test_semantic_equivalence.py`.

## Choose the checks

| Scorer | What it does | Use when |
| --- | --- | --- |
| `SemanticEquivalence()` | Compares query structure; confirms or returns `unknown` | You want structural proof only, no execution |
| `observed_equivalence()` | Structure first, else runs both queries and diffs the results | Grading AI SQL against a gold query (the usual choice) |
| `judged_equivalence(model)` | Structure first, else an LLM judge; runs no query | Execution isn't available |

!!! note "Plan equivalence (future tier)"
    A logical-plan check is a planned addition. Spark's `DataFrame.sameSemantics` is the model:
    it canonicalises the logical *plan* a DataFrame compiles to and compares those plans. That
    is a different layer from `AstEquivalence`, which canonicalises the SQL syntax tree — a plan
    check sees through more rewrites (a CTE, a pushed-down filter) that leave the syntax tree
    different. It would slot in as another `SemanticEquivalence` check.

## Next steps

- [Concepts](../concepts.md) — scorers, solvers, and expected-types in depth.
- [Scorers reference](../reference/scorers.md) — the scorer and check API.

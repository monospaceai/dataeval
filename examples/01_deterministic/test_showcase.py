"""Showcase: semantic equivalence with an execution fallback, via the clean `assert_eval` API.

`observed_equivalence()` proves two queries equivalent from their structure when it can — no
query is run — and otherwise executes both and compares the results. It needs only the core
package and a local DuckDB file, so the whole file runs with no model, network, or extras.
"""

import tempfile
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from evaldata import CallableSolver, EvalCase, assert_eval, eval_case, observed_equivalence
from evaldata.platforms import duckdb_platform

_DB_PATH = Path(tempfile.mkdtemp(prefix="evaldata_showcase_")) / "shop.duckdb"
_PLATFORM = duckdb_platform(name="examples-showcase", path=str(_DB_PATH))


@pytest.fixture(scope="module", autouse=True)
def _seed_db() -> Iterator[None]:
    con = duckdb.connect(str(_DB_PATH))
    con.execute("CREATE TABLE customers (id INTEGER, name VARCHAR, country VARCHAR)")
    con.execute("INSERT INTO customers VALUES (1, 'Ada', 'GB'), (2, 'Bo', 'US'), (3, 'Cy', 'US')")
    con.close()
    yield


# Proven without running: the AI reorders the predicates and changes the casing. The syntax
# trees normalize to the same form, so the queries are confirmed equivalent — no query runs.
@eval_case(
    input="Name the US customers with an id above 1.",
    expected={"kind": "gold_query", "sql": "SELECT name FROM customers WHERE country = 'US' AND id > 1"},
    platform=_PLATFORM,
)
def test_proven_equivalent(case: EvalCase) -> None:
    """Reordered predicates and casing; confirmed by structure, without executing either query."""
    solver = CallableSolver(lambda c: "select NAME from customers where id > 1 and country = 'US'")
    assert_eval(case, solver, scorers=[observed_equivalence()])


# Confirmed by execution: a CTE the syntax check can't match. `observed_equivalence` falls back
# to running both queries and comparing the results, which agree.
@eval_case(
    input="Name the US customers.",
    expected={"kind": "gold_query", "sql": "SELECT name FROM customers WHERE country = 'US'"},
    platform=_PLATFORM,
)
def test_confirmed_by_execution(case: EvalCase) -> None:
    """A CTE the syntax check leaves inconclusive; the execution fallback runs both and confirms."""
    solver = CallableSolver(lambda c: "WITH us AS (SELECT * FROM customers WHERE country = 'US') SELECT name FROM us")
    assert_eval(case, solver, scorers=[observed_equivalence()])

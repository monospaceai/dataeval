"""§9 acceptance: the full pytest-native surface end-to-end against a real DuckDB file.

Dogfoods the headline UX — ``@eval_case`` with a dict ``expected`` and a ``duckdb_platform``
ref, the plugin-injected ``case``, and ``assert_eval`` with NO explicit adapter (resolved
from ``case.platform``). Uses ``CallableSolver`` so the chain is deterministic and CI-safe;
the live-LLM path is covered separately by the PromptSolver e2e test.
"""

import tempfile
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from data_eval import CallableSolver, ResultSetEquivalence, assert_eval, eval_case
from data_eval.platforms import duckdb_platform
from data_eval.types import EvalCase

# Resolved at import (decoration) time, before fixtures run; the file is seeded by
# ``_seed_db`` and opened lazily by ``assert_eval`` when the test executes.
_DB_PATH = Path(tempfile.mkdtemp(prefix="data_eval_accept_")) / "chinook.duckdb"
_ROCK_SQL = "SELECT count(*) AS count FROM tracks WHERE genre = 'Rock'"


@pytest.fixture(scope="module", autouse=True)
def _seed_db() -> Iterator[None]:
    con = duckdb.connect(str(_DB_PATH))
    con.execute("CREATE TABLE tracks (id INTEGER, genre VARCHAR)")
    con.execute("INSERT INTO tracks VALUES (1, 'Rock'), (2, 'Rock'), (3, 'Jazz')")
    con.close()
    yield


@pytest.mark.unit
@eval_case(
    input="How many tracks are in the 'Rock' genre?",
    expected={"kind": "result_set", "rows": [{"count": 2}]},
    platform=duckdb_platform(name="acceptance-local", path=str(_DB_PATH)),
)
def test_rock_track_count(case: EvalCase) -> None:
    solver = CallableSolver(lambda c: _ROCK_SQL)
    assert_eval(case, solver, scorers=[ResultSetEquivalence()])

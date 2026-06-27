"""Benchmark example: load a text-to-SQL dataset and measure execution accuracy (EX).

This builds a tiny Spider-shaped dataset in a temp directory so the example is self-contained.
To run a real benchmark, download Spider or BIRD and point the CLI at it:

    evaldata bench spider /path/to/spider --model openai/gpt-4o-mini
    evaldata bench bird /path/to/bird --model openai/gpt-4o-mini --limit 100
"""

import json
import os
import sqlite3
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from evaldata import ExecutionAccuracy, PromptSolver, load_spider, run_benchmark
from evaldata.solvers import SCHEMA_PROMPT_TEMPLATE

_ROOT = Path(tempfile.mkdtemp(prefix="evaldata_ex06_"))
_DB_ID = "ex06_shop"
_MODEL = os.getenv("EVALDATA_HOSTED_MODEL", "openai/gpt-4o-mini")


@pytest.fixture(scope="module", autouse=True)
def _build_dataset() -> Iterator[None]:
    db_dir = _ROOT / "database" / _DB_ID
    db_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_dir / f"{_DB_ID}.sqlite")
    con.execute("CREATE TABLE items (id INTEGER, name TEXT, price REAL)")
    con.executemany("INSERT INTO items VALUES (?, ?, ?)", [(1, "apple", 3.0), (2, "pear", 2.0), (3, "kiwi", 5.0)])
    con.commit()
    con.close()
    questions = [
        {"db_id": _DB_ID, "question": "How many items are there?", "query": "SELECT count(*) FROM items"},
        {"db_id": _DB_ID, "question": "What is the total price of all items?", "query": "SELECT sum(price) FROM items"},
        {
            "db_id": _DB_ID,
            "question": "List item names alphabetically.",
            "query": "SELECT name FROM items ORDER BY name",
        },
    ]
    (_ROOT / "dev.json").write_text(json.dumps(questions), encoding="utf-8")
    yield


def test_execution_accuracy() -> None:
    """Load the dataset, run a schema-prompted solver, and check the aggregate EX."""
    cases = load_spider(_ROOT)
    solver = PromptSolver(model=_MODEL, prompt_template=SCHEMA_PROMPT_TEMPLATE, temperature=0)
    summary = run_benchmark(cases, solver, scorers=[ExecutionAccuracy()])

    # The mocked model answers the first two questions and misses the third, so 2 of 3 pass.
    assert summary.total == 3
    assert summary.passed == 2
    assert summary.accuracy == pytest.approx(2 / 3)

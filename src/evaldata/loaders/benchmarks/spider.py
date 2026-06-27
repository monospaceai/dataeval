"""Loader for the Spider 1.0 text-to-SQL benchmark."""

import json
from collections.abc import Iterator
from pathlib import Path

from evaldata.loaders.benchmarks.sqlite_benchmark import build_case
from evaldata.types import EvalCase


def load_spider(root: str | Path, *, split: str = "dev") -> Iterator[EvalCase]:
    """Yield Spider cases from an unzipped Spider dataset directory.

    Reads `<root>/<split>.json` (a list of `{db_id, question, query}` records) and pairs each
    question with its `db_id`'s SQLite database at `<root>/database/<db_id>/<db_id>.sqlite`. The
    gold `query` becomes the case's `GoldQuery`, scored with `ExecutionAccuracy`. The dataset is
    not redistributed; download it from the Spider project and pass its directory here.

    Args:
        root: Path to the unzipped Spider dataset directory.
        split: The split file stem to read (`"dev"` reads `dev.json`).

    Yields:
        One `EvalCase` per question, in file order, on the `sqlite` platform.
    """
    root = Path(root)
    records = json.loads((root / f"{split}.json").read_text(encoding="utf-8"))
    for index, record in enumerate(records):
        db_id = record["db_id"]
        db_path = root / "database" / db_id / f"{db_id}.sqlite"
        yield build_case(
            source="spider",
            case_id=f"spider/{db_id}/{index}",
            question=record["question"],
            gold_sql=record["query"],
            db_id=db_id,
            db_path=db_path,
            extra_metadata={"split": split},
        )

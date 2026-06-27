"""Loader for the BIRD text-to-SQL benchmark."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from evaldata.loaders.benchmarks.sqlite_benchmark import build_case
from evaldata.types import EvalCase


def load_bird(root: str | Path, *, split: str = "dev", include_evidence: bool = True) -> Iterator[EvalCase]:
    """Yield BIRD cases from an unzipped BIRD dataset directory.

    Reads `<root>/<split>.json` (records with `db_id`, `question`, `evidence`, `SQL`, and on the
    dev split `question_id`/`difficulty`) and pairs each question with its `db_id`'s SQLite
    database at `<root>/<split>_databases/<db_id>/<db_id>.sqlite`. The gold `SQL` becomes the
    case's `GoldQuery`, scored with `ExecutionAccuracy`. The dataset is not redistributed;
    download it from the BIRD project and pass its directory here.

    Args:
        root: Path to the unzipped BIRD dataset directory.
        split: The split file stem to read (`"dev"` reads `dev.json` and `dev_databases/`).
        include_evidence: When `True` (default), fold each record's external-knowledge
            `evidence` into the question input. The raw evidence is kept in metadata either way.

    Yields:
        One `EvalCase` per question, in file order, on the `sqlite` platform.
    """
    root = Path(root)
    records = json.loads((root / f"{split}.json").read_text(encoding="utf-8"))
    for index, record in enumerate(records):
        db_id = record["db_id"]
        db_path = root / f"{split}_databases" / db_id / f"{db_id}.sqlite"
        evidence = record.get("evidence", "") or ""
        question = record["question"]
        if include_evidence and evidence:
            question = f"{question}\nEvidence: {evidence}"
        extra_metadata: dict[str, Any] = {"split": split, "evidence": evidence}
        if "difficulty" in record:
            extra_metadata["difficulty"] = record["difficulty"]
        question_id = record.get("question_id")
        case_id = f"bird/{question_id}" if question_id is not None else f"bird/{db_id}/{index}"
        yield build_case(
            source="bird",
            case_id=case_id,
            question=question,
            gold_sql=record["SQL"],
            db_id=db_id,
            db_path=db_path,
            extra_metadata=extra_metadata,
        )

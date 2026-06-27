"""Tests for the Spider and BIRD benchmark loaders."""

import json
import sqlite3
from pathlib import Path

import pytest

from evaldata.loaders import load_bird, load_spider
from evaldata.loaders.benchmarks.sqlite_benchmark import schema_ddl
from evaldata.types import GoldQuery


def _make_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE items (id INTEGER, name TEXT)")
    con.execute("INSERT INTO items VALUES (1, 'a')")
    con.commit()
    con.close()


@pytest.mark.unit
class TestLoadSpider:
    def test_builds_cases_with_gold_platform_and_schema(self, tmp_path: Path) -> None:
        _make_db(tmp_path / "database" / "shop_sp" / "shop_sp.sqlite")
        (tmp_path / "dev.json").write_text(
            json.dumps(
                [
                    {"db_id": "shop_sp", "question": "how many items?", "query": "SELECT count(*) FROM items"},
                    {"db_id": "shop_sp", "question": "names?", "query": "SELECT name FROM items"},
                ]
            )
        )
        cases = list(load_spider(tmp_path))

        assert [c.id for c in cases] == ["spider/shop_sp/0", "spider/shop_sp/1"]
        first = cases[0]
        assert first.input == "how many items?"
        assert isinstance(first.expected, GoldQuery)
        assert first.expected.sql == "SELECT count(*) FROM items"
        assert first.platform.kind == "sqlite"
        assert first.platform.name == "spider:shop_sp"
        assert first.metadata["source"] == "spider"
        assert first.metadata["db_id"] == "shop_sp"
        assert "CREATE TABLE items" in first.metadata["schema_ddl"]


@pytest.mark.unit
class TestLoadBird:
    def test_folds_evidence_and_keeps_metadata(self, tmp_path: Path) -> None:
        _make_db(tmp_path / "dev_databases" / "shop_bd" / "shop_bd.sqlite")
        (tmp_path / "dev.json").write_text(
            json.dumps(
                [
                    {
                        "question_id": 7,
                        "db_id": "shop_bd",
                        "question": "how many items?",
                        "evidence": "item means row",
                        "SQL": "SELECT count(*) FROM items",
                        "difficulty": "simple",
                    }
                ]
            )
        )
        (case,) = list(load_bird(tmp_path))

        assert case.id == "bird/7"
        assert case.input == "how many items?\nEvidence: item means row"
        assert isinstance(case.expected, GoldQuery)
        assert case.metadata["evidence"] == "item means row"
        assert case.metadata["difficulty"] == "simple"
        assert case.platform.name == "bird:shop_bd"

    def test_excludes_evidence_when_disabled_and_handles_missing_fields(self, tmp_path: Path) -> None:
        _make_db(tmp_path / "dev_databases" / "plain_bd" / "plain_bd.sqlite")
        (tmp_path / "dev.json").write_text(
            json.dumps(
                [
                    {
                        "db_id": "plain_bd",
                        "question": "how many items?",
                        "evidence": "",
                        "SQL": "SELECT count(*) FROM items",
                    }
                ]
            )
        )
        (case,) = list(load_bird(tmp_path, include_evidence=False))

        assert case.id == "bird/plain_bd/0"  # no question_id -> positional id
        assert case.input == "how many items?"  # no evidence folded
        assert "difficulty" not in case.metadata


@pytest.mark.unit
def test_schema_ddl_empty_for_tableless_db(tmp_path: Path) -> None:
    path = tmp_path / "empty.sqlite"
    sqlite3.connect(path).close()
    assert schema_ddl(str(path)) == ""

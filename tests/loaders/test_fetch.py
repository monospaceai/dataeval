"""Tests for the benchmark fetch/verify/cache module (no network)."""

import hashlib
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest

import evaldata.loaders.benchmarks.fetch as fetch
from evaldata.loaders.benchmarks.fetch import (
    BenchmarkSource,
    cached_dataset_path,
    fetch_benchmark,
)


def _make_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE items (id INTEGER, name TEXT)")
    con.execute("INSERT INTO items VALUES (1, 'a')")
    con.commit()
    con.close()


def _build_benchmark_zip(
    tmp: Path,
    *,
    cases: int,
    databases_dirname: str,
    nested_databases_zip: bool,
    wrapper_name: str,
    db_name: str = "shop",
    corrupt: bool = False,
) -> Path:
    """Build a benchmark archive under `wrapper_name/`, with `dev.json` and databases.

    When `nested_databases_zip=True`, the databases directory is packed as a nested zip and a
    `__MACOSX/` dir is included (exercises both extraction and cleanup).
    """
    staging = tmp / "staging"
    wrapper = staging / wrapper_name
    db_dir = wrapper / databases_dirname / db_name
    db_dir.mkdir(parents=True)
    db_path = db_dir / f"{db_name}.sqlite"
    if corrupt:
        db_path.write_text("not a sqlite database")
    else:
        _make_db(db_path)

    records = [{"db_id": db_name, "question": f"q{i}", "evidence": "", "SQL": "SELECT 1"} for i in range(cases)]
    (wrapper / "dev.json").write_text(json.dumps(records))

    if nested_databases_zip:
        nested = wrapper / f"{databases_dirname}.zip"
        with zipfile.ZipFile(nested, "w") as zf:
            for file in (wrapper / databases_dirname).rglob("*"):
                zf.write(file, file.relative_to(wrapper))
        shutil.rmtree(wrapper / databases_dirname)

        # An ignorable macOS metadata folder at the top level.
        (wrapper / "__MACOSX").mkdir()
        (wrapper / "__MACOSX" / "junk").write_text("ignore me")

    archive = tmp / "dev.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for file in staging.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(staging))
    return archive


def _build_bird_zip(tmp: Path, *, cases: int, db_name: str = "shop", corrupt: bool = False) -> Path:
    """Build a BIRD-shaped dev.zip with a nested dev_databases.zip wrapper and a __MACOSX dir."""
    return _build_benchmark_zip(
        tmp,
        cases=cases,
        databases_dirname="dev_databases",
        nested_databases_zip=True,
        wrapper_name="dev_20240627",
        db_name=db_name,
        corrupt=corrupt,
    )


def _build_spider_zip(tmp: Path, *, cases: int, db_name: str = "shop", corrupt: bool = False) -> Path:
    """Build a Spider-shaped zip with a plain database/ dir under a spider_data/ wrapper."""
    return _build_benchmark_zip(
        tmp,
        cases=cases,
        databases_dirname="database",
        nested_databases_zip=False,
        wrapper_name="spider_data",
        db_name=db_name,
        corrupt=corrupt,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def fake_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stand up a fake bird archive + monkeypatched _download, returning useful handles."""
    cache = tmp_path / "cache"
    archive = _build_bird_zip(tmp_path, cases=3)
    real_sha = _sha256(archive)

    calls = {"n": 0}

    def fake_download(url: str, dest: Path, *, progress: bool) -> str:
        calls["n"] += 1
        shutil.copyfile(archive, dest)
        return _sha256(dest)

    monkeypatch.setattr(fetch, "_download", fake_download)

    def install(*, archive_sha256: str | None, expected_cases: int = 3) -> None:
        fetch.SOURCES["bird"] = BenchmarkSource(
            name="bird",
            url="https://example.invalid/dev.zip",
            archive_sha256=archive_sha256,
            expected_cases=expected_cases,
            split="dev",
            license="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
            databases_dirname="dev_databases",
            nested_databases_zip=True,
        )

    original = fetch.SOURCES["bird"]
    yield {"cache": cache, "real_sha": real_sha, "calls": calls, "install": install, "archive": archive}
    fetch.SOURCES["bird"] = original


@pytest.fixture
def fake_spider_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stand up a fake Spider archive + monkeypatched _download, returning useful handles."""
    cache = tmp_path / "cache"
    archive = _build_spider_zip(tmp_path, cases=3)
    real_sha = _sha256(archive)

    calls = {"n": 0}

    def fake_download(url: str, dest: Path, *, progress: bool) -> str:
        calls["n"] += 1
        shutil.copyfile(archive, dest)
        return _sha256(dest)

    monkeypatch.setattr(fetch, "_download", fake_download)

    def install(*, archive_sha256: str | None, expected_cases: int = 3) -> None:
        fetch.SOURCES["spider"] = BenchmarkSource(
            name="spider",
            url="https://example.invalid/spider_data.zip",
            archive_sha256=archive_sha256,
            expected_cases=expected_cases,
            split="dev",
            license="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
            databases_dirname="database",
            nested_databases_zip=False,
        )

    original = fetch.SOURCES["spider"]
    yield {"cache": cache, "real_sha": real_sha, "calls": calls, "install": install, "archive": archive}
    fetch.SOURCES["spider"] = original


@pytest.mark.unit
class TestFetchBenchmark:
    def test_pinned_hash_match_caches_and_returns_root(self, fake_source: dict) -> None:
        fake_source["install"](archive_sha256=fake_source["real_sha"])
        root = fetch_benchmark("bird", cache_dir=fake_source["cache"])
        assert (root / "dev.json").is_file()
        assert (root / "dev_databases").is_dir()
        assert (root / ".evaldata-meta.json").is_file()

    def test_pinned_hash_mismatch_raises_and_writes_no_cache(self, fake_source: dict) -> None:
        fake_source["install"](archive_sha256="0" * 64)
        with pytest.raises(RuntimeError, match="does not match the pinned"):
            fetch_benchmark("bird", cache_dir=fake_source["cache"])
        assert cached_dataset_path("bird", cache_dir=fake_source["cache"]) is None

    def test_unpinned_untrusted_refuses_before_downloading(self, fake_source: dict) -> None:
        fake_source["install"](archive_sha256=None)
        with pytest.raises(RuntimeError, match="not yet pinned"):
            fetch_benchmark("bird", trust=False, cache_dir=fake_source["cache"])
        # Fails fast: no download, no cache.
        assert fake_source["calls"]["n"] == 0
        assert cached_dataset_path("bird", cache_dir=fake_source["cache"]) is None

    def test_unpinned_trusted_caches(self, fake_source: dict) -> None:
        fake_source["install"](archive_sha256=None)
        root = fetch_benchmark("bird", trust=True, cache_dir=fake_source["cache"])
        assert (root / "dev.json").is_file()

    def test_expected_cases_mismatch_raises(self, fake_source: dict) -> None:
        fake_source["install"](archive_sha256=fake_source["real_sha"], expected_cases=99)
        with pytest.raises(RuntimeError, match="wrong dataset version"):
            fetch_benchmark("bird", cache_dir=fake_source["cache"])
        assert cached_dataset_path("bird", cache_dir=fake_source["cache"]) is None

    def test_corrupt_sqlite_fails_integrity(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cache = tmp_path / "cache"
        archive = _build_bird_zip(tmp_path, cases=3, corrupt=True)

        monkeypatch.setattr(
            fetch,
            "_download",
            lambda url, dest, *, progress: (shutil.copyfile(archive, dest), _sha256(dest))[1],
        )
        original = fetch.SOURCES["bird"]
        fetch.SOURCES["bird"] = BenchmarkSource(
            name="bird",
            url="https://example.invalid/dev.zip",
            archive_sha256=_sha256(archive),
            expected_cases=3,
            split="dev",
            license="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
            databases_dirname="dev_databases",
            nested_databases_zip=True,
        )
        try:
            with pytest.raises(RuntimeError, match="SQLite|integrity"):
                fetch_benchmark("bird", cache_dir=cache)
        finally:
            fetch.SOURCES["bird"] = original

    def test_valid_cache_skips_second_download(self, fake_source: dict) -> None:
        fake_source["install"](archive_sha256=fake_source["real_sha"])
        fetch_benchmark("bird", cache_dir=fake_source["cache"])
        assert fake_source["calls"]["n"] == 1
        fetch_benchmark("bird", cache_dir=fake_source["cache"])
        assert fake_source["calls"]["n"] == 1


@pytest.mark.unit
class TestFetchSpider:
    def test_pinned_hash_match_caches_and_returns_root(self, fake_spider_source: dict) -> None:
        fake_spider_source["install"](archive_sha256=fake_spider_source["real_sha"])
        root = fetch_benchmark("spider", cache_dir=fake_spider_source["cache"])
        assert (root / "dev.json").is_file()
        assert (root / "database").is_dir()
        assert (root / ".evaldata-meta.json").is_file()

    def test_unpinned_untrusted_refuses_before_downloading(self, fake_spider_source: dict) -> None:
        fake_spider_source["install"](archive_sha256=None)
        with pytest.raises(RuntimeError, match="not yet pinned"):
            fetch_benchmark("spider", trust=False, cache_dir=fake_spider_source["cache"])
        assert fake_spider_source["calls"]["n"] == 0
        assert cached_dataset_path("spider", cache_dir=fake_spider_source["cache"]) is None

    def test_expected_cases_mismatch_raises(self, fake_spider_source: dict) -> None:
        fake_spider_source["install"](archive_sha256=fake_spider_source["real_sha"], expected_cases=99)
        with pytest.raises(RuntimeError, match="wrong dataset version"):
            fetch_benchmark("spider", cache_dir=fake_spider_source["cache"])
        assert cached_dataset_path("spider", cache_dir=fake_spider_source["cache"]) is None

    def test_corrupt_sqlite_fails_integrity(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cache = tmp_path / "cache"
        archive = _build_spider_zip(tmp_path, cases=3, corrupt=True)

        monkeypatch.setattr(
            fetch,
            "_download",
            lambda url, dest, *, progress: (shutil.copyfile(archive, dest), _sha256(dest))[1],
        )
        original = fetch.SOURCES["spider"]
        fetch.SOURCES["spider"] = BenchmarkSource(
            name="spider",
            url="https://example.invalid/spider_data.zip",
            archive_sha256=_sha256(archive),
            expected_cases=3,
            split="dev",
            license="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
            databases_dirname="database",
            nested_databases_zip=False,
        )
        try:
            with pytest.raises(RuntimeError, match="SQLite|integrity"):
                fetch_benchmark("spider", cache_dir=cache)
        finally:
            fetch.SOURCES["spider"] = original


@pytest.mark.unit
def test_non_zip_download_raises_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "cache"
    html = tmp_path / "quota.html"
    html.write_bytes(b"<!DOCTYPE html><html>Google Drive quota exceeded</html>")

    monkeypatch.setattr(
        fetch,
        "_download",
        lambda url, dest, *, progress: (shutil.copyfile(html, dest), _sha256(dest))[1],
    )
    original = fetch.SOURCES["spider"]
    fetch.SOURCES["spider"] = BenchmarkSource(
        name="spider",
        url="https://example.invalid/spider_data.zip",
        archive_sha256=_sha256(html),
        expected_cases=3,
        split="dev",
        license="CC BY-SA 4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        databases_dirname="database",
        nested_databases_zip=False,
    )
    try:
        with pytest.raises(RuntimeError, match="not a valid zip"):
            fetch_benchmark("spider", cache_dir=cache)
    finally:
        fetch.SOURCES["spider"] = original


@pytest.mark.unit
def test_unknown_name_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown benchmark"):
        fetch_benchmark("nope", cache_dir=tmp_path)


@pytest.mark.unit
def test_cached_dataset_path_none_when_absent(tmp_path: Path) -> None:
    assert cached_dataset_path("bird", cache_dir=tmp_path) is None
    assert cached_dataset_path("nope", cache_dir=tmp_path) is None


@pytest.mark.unit
def test_cache_root_explicit_dir(tmp_path: Path) -> None:
    explicit = tmp_path / "my_cache"
    assert fetch.cache_root(explicit) == explicit


@pytest.mark.unit
def test_cache_root_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVALDATA_CACHE_DIR", str(tmp_path / "from_env"))
    result = fetch.cache_root(None)
    assert result == tmp_path / "from_env"


@pytest.mark.unit
def test_cache_root_platformdirs_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """When neither explicit dir nor env var is set, delegates to platformdirs."""
    monkeypatch.delenv("EVALDATA_CACHE_DIR", raising=False)
    result = fetch.cache_root(None)
    # Just check it returns a Path — the exact value is platform-dependent.
    assert isinstance(result, Path)


@pytest.mark.unit
def test_cache_root_missing_platformdirs(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.delenv("EVALDATA_CACHE_DIR", raising=False)
    # Simulate platformdirs not being installed.
    monkeypatch.setitem(sys.modules, "platformdirs", None)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="platformdirs is required"):
        fetch.cache_root(None)


@pytest.mark.unit
def test_cached_dataset_path_parent_exists_but_no_valid_child(tmp_path: Path) -> None:
    # Create the parent dir and put a directory in it that is NOT a valid cache.
    parent = tmp_path / "datasets" / "bird"
    child = parent / "abc123"
    child.mkdir(parents=True)
    # Missing both .evaldata-meta.json and dev.json → not valid.
    assert cached_dataset_path("bird", cache_dir=tmp_path) is None


# — the trust=False path is already tested via fetch_benchmark; cover the


@pytest.mark.unit
def test_verify_hash_unpinned_trusted_passes(tmp_path: Path) -> None:
    source = BenchmarkSource(
        name="test",
        url="https://example.invalid/x.zip",
        archive_sha256=None,
        expected_cases=1,
        split="dev",
        license="MIT",
        license_url="https://mit.example/",
        databases_dirname="database",
        nested_databases_zip=False,
    )
    # Must not raise.
    fetch._verify_hash(source, "abc" * 20, tmp_path / "archive.zip", trust=True)


@pytest.mark.unit
def test_verify_hash_unpinned_untrusted_raises(tmp_path: Path) -> None:
    source = BenchmarkSource(
        name="test",
        url="https://example.invalid/x.zip",
        archive_sha256=None,
        expected_cases=1,
        split="dev",
        license="MIT",
        license_url="https://mit.example/",
        databases_dirname="database",
        nested_databases_zip=False,
    )
    temp = tmp_path / "archive.zip"
    temp.write_bytes(b"data")
    with pytest.raises(RuntimeError, match="not yet pinned"):
        fetch._verify_hash(source, "abc" * 20, temp, trust=False)
    # File should be deleted.
    assert not temp.exists()


@pytest.mark.unit
def test_normalize_layout_missing_split_json(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    source = BenchmarkSource(
        name="test",
        url="",
        archive_sha256=None,
        expected_cases=0,
        split="dev",
        license="MIT",
        license_url="",
        databases_dirname="database",
        nested_databases_zip=False,
    )
    with pytest.raises(RuntimeError, match="dev.json not found"):
        fetch._normalize_layout(extracted, source)


@pytest.mark.unit
def test_normalize_layout_missing_databases_dir(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    wrapper = extracted / "wrapper"
    wrapper.mkdir(parents=True)
    (wrapper / "dev.json").write_text("[]")
    # No databases dir.
    source = BenchmarkSource(
        name="test",
        url="",
        archive_sha256=None,
        expected_cases=0,
        split="dev",
        license="MIT",
        license_url="",
        databases_dirname="database",
        nested_databases_zip=False,
    )
    with pytest.raises(RuntimeError, match="database/ not found"):
        fetch._normalize_layout(extracted, source)


@pytest.mark.unit
def test_normalize_layout_nested_zip_absent_does_not_crash(tmp_path: Path) -> None:
    """nested_databases_zip=True but no <databases>.zip present — no error, skip."""
    extracted = tmp_path / "extracted"
    wrapper = extracted / "wrapper"
    db_dir = wrapper / "dev_databases" / "shop"
    db_dir.mkdir(parents=True)
    (wrapper / "dev.json").write_text("[]")
    _make_db(db_dir / "shop.sqlite")
    source = BenchmarkSource(
        name="test",
        url="",
        archive_sha256=None,
        expected_cases=0,
        split="dev",
        license="MIT",
        license_url="",
        databases_dirname="dev_databases",
        nested_databases_zip=True,  # zip should be extracted, but file is absent
    )
    root = fetch._normalize_layout(extracted, source)
    assert (root / "dev.json").exists()


@pytest.mark.unit
def test_validate_integrity_check_database_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A SQLite file that raises DatabaseError on open → RuntimeError."""
    source = BenchmarkSource(
        name="test",
        url="",
        archive_sha256=None,
        expected_cases=1,
        split="dev",
        license="MIT",
        license_url="",
        databases_dirname="database",
        nested_databases_zip=False,
    )
    db_dir = tmp_path / "database" / "shop"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "shop.sqlite"
    db_path.write_bytes(b"notasqlite")

    records = [{"db_id": "shop", "question": "q"}]
    (tmp_path / "dev.json").write_text(json.dumps(records))

    with pytest.raises(RuntimeError, match="SQLite|not a valid"):
        fetch._validate(tmp_path, source)


@pytest.mark.unit
def test_validate_integrity_check_non_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A SQLite file that opens but whose integrity_check returns non-'ok' → RuntimeError."""
    source = BenchmarkSource(
        name="test",
        url="",
        archive_sha256=None,
        expected_cases=1,
        split="dev",
        license="MIT",
        license_url="",
        databases_dirname="database",
        nested_databases_zip=False,
    )
    db_dir = tmp_path / "database" / "shop"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "shop.sqlite"
    # Mock the connection so integrity_check returns a non-'ok' result.

    class _FakeConn:
        def execute(self, sql: str) -> "_FakeCursor":
            return _FakeCursor()

        def close(self) -> None: ...

    class _FakeCursor:
        def fetchone(self) -> tuple[str]:
            return ("*** index corruption ***",)

    monkeypatch.setattr(fetch.sqlite3, "connect", lambda *a, **kw: _FakeConn())

    records = [{"db_id": "shop", "question": "q"}]
    (tmp_path / "dev.json").write_text(json.dumps(records))
    # The file just needs to exist for rglob to find it.
    db_path.write_bytes(b"placeholder")

    with pytest.raises(RuntimeError, match="failed integrity_check"):
        fetch._validate(tmp_path, source)


@pytest.mark.unit
def test_force_redownload_ignores_valid_cache(fake_source: dict) -> None:
    fake_source["install"](archive_sha256=fake_source["real_sha"])
    # First download.
    fetch_benchmark("bird", cache_dir=fake_source["cache"])
    assert fake_source["calls"]["n"] == 1
    # force=True → re-downloads even though cache is valid.
    fetch_benchmark("bird", force=True, cache_dir=fake_source["cache"])
    assert fake_source["calls"]["n"] == 2


@pytest.mark.unit
def test_bad_zip_file_raises_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """is_zipfile returns True but ZipFile.extractall raises BadZipFile → RuntimeError."""
    cache = tmp_path / "cache"
    # Use a real (empty) zip so is_zipfile() passes, then make ZipFile raise BadZipFile.
    valid_zip = tmp_path / "placeholder.zip"
    with zipfile.ZipFile(valid_zip, "w"):
        pass  # empty zip — is_zipfile returns True

    monkeypatch.setattr(
        fetch,
        "_download",
        lambda url, dest, *, progress: (dest.write_bytes(valid_zip.read_bytes()), "a" * 64)[1],
    )

    original_zipfile_cls = fetch.zipfile.ZipFile

    class _BadZipFile:
        def __init__(self, *a: object, **kw: object) -> None: ...

        def __enter__(self) -> "_BadZipFile":
            msg = "simulated extraction failure"
            raise zipfile.BadZipFile(msg)

        def __exit__(self, *a: object) -> None: ...

    monkeypatch.setattr(fetch.zipfile, "ZipFile", _BadZipFile)

    original = fetch.SOURCES["bird"]
    fetch.SOURCES["bird"] = BenchmarkSource(
        name="bird",
        url="https://example.invalid/dev.zip",
        archive_sha256="a" * 64,
        expected_cases=3,
        split="dev",
        license="CC BY-SA 4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        databases_dirname="dev_databases",
        nested_databases_zip=True,
    )
    try:
        with pytest.raises(RuntimeError, match="not a valid zip"):
            fetch_benchmark("bird", cache_dir=cache)
    finally:
        fetch.SOURCES["bird"] = original
        monkeypatch.setattr(fetch.zipfile, "ZipFile", original_zipfile_cls)


@pytest.mark.unit
def test_unpinned_trusted_prints_pin_hint(fake_source: dict, capsys: pytest.CaptureFixture[str]) -> None:
    fake_source["install"](archive_sha256=None)
    fetch_benchmark("bird", trust=True, cache_dir=fake_source["cache"])
    captured = capsys.readouterr()
    assert "pin this version" in captured.out
    assert "archive_sha256=" in captured.out


@pytest.mark.unit
def test_force_overwrites_existing_destination(fake_source: dict) -> None:
    fake_source["install"](archive_sha256=fake_source["real_sha"])
    root1 = fetch_benchmark("bird", cache_dir=fake_source["cache"])
    # Destination already exists; force re-download should overwrite it cleanly.
    root2 = fetch_benchmark("bird", force=True, cache_dir=fake_source["cache"])
    assert (root2 / "dev.json").is_file()
    # Both calls land at the same content-addressed dir (same archive → same hash prefix).
    assert root1 == root2

"""The ``data-eval`` command-line interface: ``run`` and ``doctor``.

Two Typer commands on one flat app (Typer's recommended shape for a small, non-namespaced
CLI; ``add_typer`` is for sub-apps we don't have):

* ``data-eval run [PATH] [pytest args...]`` — runs the suite via pytest. It is a thin,
  faithful wrapper: pytest is invoked as a **subprocess** (``sys.executable -m pytest``),
  not in-process ``pytest.main()``. Subprocess is what tox/nox and pytest's own docs use;
  it forwards args cleanly (unknown args pass straight through via ``ctx.args``), honors the
  project's ``addopts``, and isolates a hung/``sys.exit``-ing test from the CLI. Using
  ``sys.executable -m pytest`` (not a bare ``pytest`` binary) keeps it correct under uv /
  venv without depending on uv itself. The one thing ``run`` adds over bare pytest is the
  ``--json`` opt-in, which forwards to the plugin's ``--data-eval-json`` artifact. The
  plugin auto-loads via its ``pytest11`` entry point, so no ``-p`` injection is needed.

* ``data-eval doctor`` — platform connection diagnostics. Args-only by design: there is no
  project-level config yet, so platforms are passed as per-kind flags that map 1:1 to the
  ``platforms.registry`` ref builders (``--duckdb PATH`` / ``--postgres CONNINFO``, each also
  reading an env var). Each is resolved to a live adapter and probed with ``SELECT 1``;
  results render as a Rich OK/FAIL checklist (dbt ``debug`` style). Connection failures
  surface as a FAIL line — adapter construction may *raise* (e.g. psycopg can't connect), so
  the probe catches broadly: a diagnostics command reports failures, it never crashes on one.

A new platform kind is added in one place (``PlatformKind``); ``_build_refs`` then needs a
flag for it (the ``test_doctor_covers_every_supported_kind`` drift test fails until it does),
and ``registry.resolve`` already dispatches over the kind exhaustively (match/assert_never).
"""

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from data_eval.platforms.registry import close_all, duckdb_platform, postgres_platform, resolve
from data_eval.types import PlatformRef

app = typer.Typer(help="AI evals for data & analytics engineering teams.", no_args_is_help=True)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,
    path: str | None = typer.Argument(None, help="Path or test id to run; omit to use pytest's testpaths."),
    json_path: Path | None = typer.Option(
        None,
        "--json",
        metavar="PATH",
        help="Also write the structured data-eval results JSON to PATH (off by default).",
    ),
) -> None:
    """Run the eval suite via pytest, forwarding any extra pytest arguments verbatim."""
    cmd = [sys.executable, "-m", "pytest"]
    if path is not None:
        cmd.append(path)
    if json_path is not None:
        cmd.append(f"--data-eval-json={json_path}")
    cmd.extend(ctx.args)  # unknown args (-k, -m, -x, plugin flags, ...) pass straight to pytest
    completed = subprocess.run(cmd)  # noqa: PLW1510 - exit code is forwarded, not raised on
    raise typer.Exit(completed.returncode)


def _build_refs(*, duckdb: str | None, postgres: str | None) -> list[PlatformRef]:
    """Build a ``PlatformRef`` for each platform flag that was provided.

    Each branch routes through the typed registry builder, so a flag can only ever name a
    real ``PlatformKind``. The drift test asserts this covers every supported kind.
    """
    refs: list[PlatformRef] = []
    if duckdb is not None:
        refs.append(duckdb_platform(name="duckdb", path=duckdb))
    if postgres is not None:
        refs.append(postgres_platform(name="postgres", conninfo=postgres))
    return refs


def _probe(ref: PlatformRef) -> tuple[bool, str]:
    """Resolve ``ref`` to a live adapter and run ``SELECT 1``; return (ok, detail).

    Catches broadly on purpose: adapter construction can raise (e.g. psycopg fails to
    connect, or an optional driver is missing), and ``doctor`` must report that as a FAIL
    rather than crash. A query that fails as a value (``ExecutionResult.error``) is a FAIL too.
    """
    try:
        result = resolve(ref).execute("SELECT 1")
    except Exception as e:  # noqa: BLE001 - diagnostics: any failure is a reported FAIL
        return False, str(e)
    if result.error is not None:
        return False, result.error
    return True, "connected"


@app.command()
def doctor(
    duckdb: str | None = typer.Option(
        None, "--duckdb", metavar="PATH", envvar="DATA_EVAL_DUCKDB_PATH", help="DuckDB database path to check."
    ),
    postgres: str | None = typer.Option(
        None,
        "--postgres",
        metavar="CONNINFO",
        envvar="DATA_EVAL_POSTGRES_CONNINFO",
        help='PostgreSQL libpq conninfo to check (empty "" uses PG* env vars / libpq defaults).',
    ),
) -> None:
    """Check that the given platform connections work (one --<kind> flag per platform)."""
    refs = _build_refs(duckdb=duckdb, postgres=postgres)
    if not refs:
        raise typer.BadParameter("specify at least one platform, e.g. --duckdb PATH or --postgres CONNINFO")

    console = Console()
    table = Table(title="data-eval doctor", title_justify="left")
    table.add_column("platform")
    table.add_column("kind")
    table.add_column("status")

    all_ok = True
    try:
        for ref in refs:
            ok, detail = _probe(ref)
            all_ok = all_ok and ok
            mark = "OK" if ok else "FAIL"
            # Text (not markup) so bracketed driver messages render verbatim.
            table.add_row(ref.name, ref.kind, Text(f"{mark} {detail}", style="green" if ok else "red"))
    finally:
        close_all()  # this CLI invocation owns the adapters it resolved

    console.print(table)
    if not all_ok:
        raise typer.Exit(1)

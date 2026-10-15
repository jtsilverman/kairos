"""Reviewer-caught (dossier-data): every omitted line must trace to a named
run-log line (AC3) — the P/S-history path skipped silently on empty closes
while the RS-decomposition path logged.

Plus the manifest write, which a subset run must MERGE rather than overwrite:
`panel_prepare` reads every name's doc ids from the manifest, so a 10-name
retry that rewrote it dropped 160 compiled dossiers out of the funnel without
any error (seen live on the 2026-05-01 rewind directory).
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "thesis_dossiers",
    Path(__file__).resolve().parents[2] / "scripts" / "thesis_dossiers.py")
td = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(td)

AS_OF = "2026-05-01"


def test_ps_history_omission_logged_on_empty_closes(monkeypatch, caplog):
    monkeypatch.setattr(td.edgar, "fetch_companyfacts", lambda t: {})
    monkeypatch.setattr(
        td.edgar, "annual_series",
        lambda facts, tags, filed_lte=None: [("2025-12-31", 1_000.0)])
    monkeypatch.setattr(
        td.edgar, "quarterly_series",
        lambda facts, tags, filed_lte=None: [("2026-03-31", 250.0)])
    with caplog.at_level(logging.WARNING, logger="thesis_dossiers"):
        out = td.build_financials("XYZ", closes=[], as_of="2026-07-07")
    assert "ps_history" not in out
    assert any("P/S history line omitted" in r.message for r in caplog.records)


@pytest.fixture
def compile_run(tmp_path, monkeypatch):
    """Drive the real main() with every network seam stubbed.

    The manifest merge must be tested through the shipped entry point: a test
    that reimplements the merge passes just as happily with the fix deleted.
    """
    out = tmp_path / "dossiers"
    screen = tmp_path / "screen.json"
    screen.write_text(json.dumps({
        "as_of": AS_OF,
        "survivors": [{"ticker": t, "forensics": {}} for t in ("AAA", "BBB", "CCC", "DDD")]}))
    sha = {}

    monkeypatch.setattr(td, "bars_history", lambda as_of, targets: ({}, {}))
    monkeypatch.setattr(td, "compile_inputs", lambda t, row, as_of, **kw: t)
    monkeypatch.setattr(td, "dossier", SimpleNamespace(build=lambda t: SimpleNamespace(
        text=f"# {t}", sha256=sha.get(t, "a") * 64, doc_ids=("P1", "Q1"))))

    def run(tickers: str, **recompiled: str):
        sha.update(recompiled)
        monkeypatch.setattr(sys, "argv",
                            ["td", "--screen", str(screen), "--tickers", tickers,
                             "--out-dir", str(out)])
        td.main()
        return json.loads((out / AS_OF / "manifest.json").read_text())

    return run


def test_a_subset_run_keeps_every_name_it_did_not_compile(compile_run):
    compile_run("AAA,BBB,CCC")
    rows = compile_run("DDD")
    assert [r["ticker"] for r in rows] == ["AAA", "BBB", "CCC", "DDD"]


def test_a_recompile_replaces_that_name_and_only_that_name(compile_run):
    compile_run("AAA,BBB")
    rows = compile_run("AAA", AAA="b")
    assert [(r["ticker"], r["sha256"][0]) for r in rows] == [("AAA", "b"), ("BBB", "a")]


def test_the_first_run_writes_a_manifest_from_nothing(compile_run):
    assert [r["ticker"] for r in compile_run("AAA")] == ["AAA"]

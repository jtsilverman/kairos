"""Reviewer-caught (dossier-data): every omitted line must trace to a named
run-log line (AC3) — the P/S-history path skipped silently on empty closes
while the RS-decomposition path logged."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "thesis_dossiers",
    Path(__file__).resolve().parents[2] / "scripts" / "thesis_dossiers.py")
td = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(td)


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

"""thesis-rewind-eval A1: the rewind dossier compile is PIT end to end.

Loads scripts/thesis_dossiers.py, monkeypatches every network fetcher, and
proves compile_inputs threads the as-of bound into each block, replaces
[E1]/[R1] with data-gap dicts, and NEVER calls the live-only estimates
module under rewind (the raise-on-call fakes are the standing guard against
a future live-only read sneaking into the rewind path).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "thesis_dossiers.py"
_spec = importlib.util.spec_from_file_location("thesis_dossiers", _SCRIPT)
td = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(td)

_AS_OF = "2026-02-02"


class _LiveOnlyCalled(AssertionError):
    pass


def _forbid(name):
    def guard(*a, **k):
        raise _LiveOnlyCalled(f"live-only estimates.{name} called under rewind")
    return guard


@pytest.fixture()
def pit_fakes(monkeypatch):
    seen: dict = {}
    facts = {"facts": {"us-gaap": {
        tag: {"units": {"USD": [
            {"form": "10-K", "fp": "FY", "start": "2024-01-01",
             "end": "2024-12-31", "val": 50_000_000.0, "filed": "2025-02-20"},
        ]}}
        for tag in ("Revenues", "NetIncomeLoss",
                    "NetCashProvidedByUsedInOperatingActivities",
                    "CommonStockSharesOutstanding")}}}

    monkeypatch.setattr(td.edgar, "fetch_companyfacts", lambda t: facts)
    monkeypatch.setattr(td.edgar, "fetch_submissions", lambda t: {"sub": 1})

    def fake_recent_filings(subs, *, forms, limit, filed_lte=None):
        seen["filings_filed_lte"] = filed_lte
        return []

    def fake_form4(t, *, limit=20, filed_lte=None):
        seen["form4_filed_lte"] = filed_lte
        return []

    def fake_news(t, *, limit, published_lte=None, **kw):
        seen["news_published_lte"] = published_lte
        return []

    def fake_digests(t, *, as_of=None, **kw):
        seen["digests_as_of"] = as_of
        return []

    def fake_short_interest(t, *, as_of=None, **kw):
        seen["finra_as_of"] = as_of
        return []

    monkeypatch.setattr(td.edgar, "recent_filings", fake_recent_filings)
    monkeypatch.setattr(td.edgar, "fetch_form4_rows", fake_form4)
    monkeypatch.setattr(td, "fetch_ticker_news", fake_news)
    monkeypatch.setattr(td.transcripts, "load_digests", fake_digests)
    monkeypatch.setattr(td.finra, "fetch_short_interest", fake_short_interest)
    for name in ("profile", "next_earnings", "earnings_dispersion",
                 "revision_snapshot"):
        monkeypatch.setattr(td.estimates, name, _forbid(name))
    return seen


_SURVIVOR = {"price": 4.9, "rs": 95.0, "forensics": {}}


def _closes():
    d = dt.date(2025, 1, 2)
    out = []
    while len(out) < 260:
        if d.weekday() < 5:
            out.append((d.isoformat(), 4.9))
        d += dt.timedelta(days=1)
    return out


def test_a1_rewind_compile_threads_asof_and_never_calls_estimates(pit_fakes):
    inputs = td.compile_inputs("ZETA", _SURVIVOR, _AS_OF, closes=_closes(),
                               rewind=True)
    assert pit_fakes["filings_filed_lte"] == _AS_OF
    assert pit_fakes["form4_filed_lte"] == _AS_OF
    assert pit_fakes["news_published_lte"] == _AS_OF
    assert pit_fakes["digests_as_of"] == _AS_OF
    assert pit_fakes["finra_as_of"] == dt.date.fromisoformat(_AS_OF)
    assert inputs.earnings == {
        "data_gap": "no point-in-time estimates vintage exists (rewind)"}
    assert inputs.revisions == {
        "data_gap": "no point-in-time revisions vintage exists (rewind)"}


def test_a1_rewind_market_cap_is_close_times_vintage_shares(pit_fakes):
    inputs = td.compile_inputs("ZETA", _SURVIVOR, _AS_OF, closes=_closes(),
                               rewind=True)
    # 4.90 x 50M vintage shares; the live estimates.profile mcap is forbidden
    assert inputs.financials["market_cap"] == pytest.approx(245_000_000.0)

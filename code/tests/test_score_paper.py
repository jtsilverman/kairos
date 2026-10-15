"""live-paper: the ledger is written once, windows fill only when their close exists."""

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("score_paper", _ROOT / "scripts" / "score_paper.py")
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)

STRONG = {"business_case": "strong", "fundamentals": "strong", "demand_case": "strong", "positioned": "strong"}


def _run(tmp_path, d):
    (tmp_path / f"panel-results-sim-middle-{d}.json").write_text(json.dumps({"summary": [
        {"slug": "AAA", "ruler_pass": True}, {"slug": "BBB", "ruler_pass": True}, {"slug": "CCC", "ruler_pass": False}]}))
    (tmp_path / f"panel-results-sim-l3-{d}.json").write_text(json.dumps({"summary": [
        {"slug": "AAA", "shortlist": True, "p_judge": 0.625, "thesis": "t", "rating_basis": "b"},
        {"slug": "BBB", "shortlist": False}]}))
    (tmp_path / f"sim-grades-{d}.json").write_text(json.dumps({"rows": [{"ticker": t, "grades": STRONG} for t in "AAA BBB CCC".split()]}))


def test_open_writes_picks_and_the_comparison_group_once(tmp_path):
    d = "2026-10-07"
    _run(tmp_path, d)
    led = sp.open_ledger(d, root=tmp_path)
    assert [p["ticker"] for p in led["picks"]] == ["AAA"] and led["picks"][0]["tier"] == "good"
    assert [r["ticker"] for r in led["rest"]] == ["BBB", "CCC"]
    assert set(led["horizons"]) == {"6w", "12w", "24w"}
    with pytest.raises(sp.LedgerExistsError):
        sp.open_ledger(d, root=tmp_path)


def test_a_window_fills_only_once_its_exit_close_exists_and_is_never_recomputed():
    as_of = (dt.date.today() - dt.timedelta(days=50)).isoformat()   # 6w closed, 12w and 24w not
    entry = (dt.date.fromisoformat(as_of) + dt.timedelta(days=1)).isoformat()
    exit6 = (dt.date.fromisoformat(as_of) + dt.timedelta(days=42)).isoformat()
    prices = {"SPY": {entry: 100.0, exit6: 125.0}, "AAA": {entry: 10.0, exit6: 15.0}}
    closes = lambda t, s, e: sorted(prices[t].items())
    led = {"as_of": as_of, "horizons": sp.HORIZONS, "picks": [{"ticker": "AAA", "windows": {}}], "rest": []}
    assert sp.fill(led, closes) == 1
    w = led["picks"][0]["windows"]
    assert w["6w"]["alpha"] == 0.25 and w["12w"] == "pending" and w["24w"] == "pending"
    prices["AAA"][exit6] = 999.0            # a later price change must not rewrite a filled window
    assert sp.fill(led, closes) == 0 and w["6w"]["alpha"] == 0.25


def test_open_defaults_the_anchor_to_as_of_and_refuses_one_before_it(tmp_path):
    d = "2026-10-06"
    _run(tmp_path, d)
    assert sp.open_ledger(d, root=tmp_path)["entry_after"] == d
    with pytest.raises(ValueError):
        sp.open_ledger("2026-10-06", root=tmp_path / "x", entry_after="2026-10-05")


def test_windows_anchor_on_entry_after_not_as_of():
    # Prices exist only around the later anchor. Anchored on as_of, the first close
    # after it would be the decoy entry and the 6w exit would fall on a different day.
    as_of = (dt.date.today() - dt.timedelta(days=56)).isoformat()
    anchor = (dt.date.fromisoformat(as_of) + dt.timedelta(days=6)).isoformat()
    decoy = (dt.date.fromisoformat(as_of) + dt.timedelta(days=1)).isoformat()
    entry = (dt.date.fromisoformat(anchor) + dt.timedelta(days=1)).isoformat()
    exit6 = (dt.date.fromisoformat(anchor) + dt.timedelta(days=42)).isoformat()
    prices = {"SPY": {decoy: 50.0, entry: 100.0, exit6: 125.0},
              "AAA": {decoy: 1.0, entry: 10.0, exit6: 15.0}}
    closes = lambda t, s, e: sorted((d, c) for d, c in prices[t].items() if s <= d <= e)
    led = {"as_of": as_of, "entry_after": anchor, "horizons": sp.HORIZONS,
           "picks": [{"ticker": "AAA", "windows": {}}], "rest": []}
    assert sp.fill(led, closes) == 1
    w = led["picks"][0]["windows"]["6w"]
    assert w["entry_date"] == entry and w["alpha"] == 0.25


def test_set_entry_moves_the_anchor_only_while_every_window_is_pending():
    led = {"as_of": "2026-10-06", "entry_after": "2026-10-06",
           "picks": [{"ticker": "AAA", "windows": {"6w": "pending"}}], "rest": []}
    assert sp.set_entry(led, "2026-10-12")["entry_after"] == "2026-10-12"
    with pytest.raises(ValueError):
        sp.set_entry(led, "2026-10-01")
    led["picks"][0]["windows"]["6w"] = {"alpha": 0.25}
    with pytest.raises(sp.EntryLockedError):
        sp.set_entry(led, "2026-10-13")
    assert led["entry_after"] == "2026-10-12"

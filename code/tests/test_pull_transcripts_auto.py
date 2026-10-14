"""RED: pull_transcripts --auto (daily corpus builder).

The launchd job maxes the 25/day AV quota unattended, so the script must
pick its own work: pool names fewest-stored-first (else the same names
re-pull daily), skip quarters known-empty within 30 days (AXGN burned 5
calls on transcript-less quarters; a daily job would re-burn them every
day — but a CURRENT fiscal quarter can fill in later, hence retry after
30 days, not never), and compute the candidate quarters from today (a
hardcoded list goes stale under a durable job).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pull_transcripts.py"
_spec = importlib.util.spec_from_file_location("pull_transcripts", _SCRIPT)
pt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pt)


def _screen(tmp_path, tickers):
    p = tmp_path / "screen.json"
    p.write_text(json.dumps(
        {"as_of": "2026-07-07", "survivors": [{"ticker": t} for t in tickers]}))
    return p


def _store(out_dir, ticker, quarters):
    for q in quarters:
        d = out_dir / ticker
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{q}.json").write_text("{}")


def test_auto_selects_fewest_stored_first_pool_order_within_ties(tmp_path):
    out = tmp_path / "transcripts"
    screen = _screen(tmp_path, ["MU", "BAND", "ATEX", "ALAB"])
    _store(out, "BAND", ["2026Q2", "2026Q1"])   # full at per_ticker=2
    _store(out, "ATEX", ["2026Q2"])             # half
    # MU, ALAB: zero stored -> first, in pool order; BAND full -> excluded
    assert pt.select_auto(screen, out, per_ticker=2) == ["MU", "ALAB", "ATEX"]


def test_known_empty_quarter_skipped_within_30_days(tmp_path):
    out = tmp_path / "transcripts"
    now = dt.date(2026, 7, 11)
    pt.mark_empty(out, "AXGN", "2026Q1", today=now)
    assert pt.known_empty(out, "AXGN", today=now) == {"2026Q1"}
    # 31 days later the quarter is retry-eligible again
    assert pt.known_empty(out, "AXGN",
                          today=now + dt.timedelta(days=31)) == set()


def test_default_quarters_roll_with_today():
    assert pt.default_quarters(dt.date(2026, 7, 11)) == [
        "2026Q3", "2026Q2", "2026Q1", "2025Q4"]
    assert pt.default_quarters(dt.date(2027, 1, 2)) == [
        "2027Q1", "2026Q4", "2026Q3", "2026Q2"]


def test_quota_notice_never_logs_the_api_key(tmp_path, monkeypatch, capsys):
    """RED: AV's quota error echoes the full API key ('We have detected your
    API key as ...'); the QUOTA HIT print logged it verbatim into
    data/logs/transcripts.log (scrubbed by hand 2026-07-12). Redact the key
    from any AV notice before printing."""
    key = "SECRETKEY123456"
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", key)
    monkeypatch.setattr(pt, "_OUT", tmp_path / "transcripts")
    monkeypatch.setattr(pt.time, "sleep", lambda s: None)
    monkeypatch.setattr(pt, "fetch", lambda t, q, k: {
        "Information": f"We have detected your API key as {key} and our "
                       "standard API rate limit is 25 requests per day."})
    monkeypatch.setattr(
        pt.sys, "argv",
        ["pull_transcripts.py", "--tickers", "MU", "--quarters", "2026Q2"])
    assert pt.main() == 2
    out = capsys.readouterr().out
    assert "QUOTA HIT" in out
    assert key not in out
    assert "***" in out

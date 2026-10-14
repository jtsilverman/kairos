#!/usr/bin/env python3
"""Realized outcomes for every name in a cohort, one quarter out.

`outcomes-<as_of>.json` used to hold only the names the tuning draw sampled.
A live-like run needs a window for every name the funnel could reach, so this
writes one per ticker in the cohort's anonymization map (every screen
survivor), through the same frozen `score_rewind.outcome` the tuning dates
used: entry on the first close after as_of, exit on the first close on or
after as_of + 91 days, alpha against SPY over the same two dates.

A name with no bar on either date is listed under `_missing` rather than
given a fabricated window. Refuses to overwrite an existing file: an outcome
file is a label set, and a silent rewrite changes every score computed on it.

CLI:
    write_outcomes.py --as-of 2026-06-01 [--root data]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_rewind  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = _ROOT / "data"


def closes_by_day(start: str, end: str) -> dict[str, dict[str, float]]:
    """{iso_date: {ticker: close}} from the grouped daily bars, one fetch a day."""
    from kairos.data.polygon import fetch_grouped_daily
    out = {}
    d, stop = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    while d <= stop:
        if d.weekday() < 5:
            bars = fetch_grouped_daily(d.isoformat())
            if bars:
                out[d.isoformat()] = {b.ticker: b.close for b in bars}
        d += dt.timedelta(days=1)
    return out


def build(as_of: str, tickers: list[str], days: dict[str, dict[str, float]],
          horizon_days: int = score_rewind.HORIZON_DAYS) -> dict:
    series = lambda t: [(d, m[t]) for d, m in sorted(days.items()) if t in m]
    spy = series("SPY")
    out, missing = {}, []
    for t in sorted(set(tickers)):
        try:
            out[t] = score_rewind.outcome(series(t), spy, as_of=as_of, horizon_days=horizon_days)
        except score_rewind.IncompleteWindowError:
            missing.append(t)
    if missing:
        out["_missing"] = missing
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    a = ap.parse_args(argv)
    root = Path(a.root)
    dest = root / f"outcomes-{a.as_of}.json"
    if dest.exists():
        print(f"{dest} exists; refusing to overwrite a label set", file=sys.stderr)
        return 1
    tickers = sorted(set(json.loads((root / f"factsheets-anon-{a.as_of}-map.json").read_text()).values()))
    end = (dt.date.fromisoformat(a.as_of) + dt.timedelta(days=score_rewind.HORIZON_DAYS + 21)).isoformat()
    days = closes_by_day(a.as_of, end)
    out = build(a.as_of, tickers, days)
    dest.write_text(json.dumps(out, indent=1))
    n = len(out) - (1 if "_missing" in out else 0)
    print(f"{a.as_of}: {n} of {len(tickers)} names scored, {len(out.get('_missing', []))} missing -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

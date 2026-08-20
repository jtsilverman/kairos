#!/usr/bin/env python3
"""Pull the most recent earnings-call transcript per ticker from Alpha
Vantage into data/transcripts/<TICKER>/<QUARTER>.json (raw response +
fetched_at). Free-tier aware: 1 req/sec spacing, stops cleanly on the
25/day quota message and reports what remains (resumable — already-stored
tickers are skipped).

Quarter walk: fiscal calendars differ per name, so for each ticker try the
candidate quarters newest-first and keep the first non-empty transcript.

Usage:
    .venv/bin/python scripts/pull_transcripts.py --tickers MU,BAND [--quarters 2026Q3,2026Q2,2026Q1,2025Q4]
    .venv/bin/python scripts/pull_transcripts.py --auto   # daily corpus builder (launchd)

--auto picks its own work from the latest screen: pool names
fewest-stored-first, quarters computed from today, quarters known-empty
skipped for 30 days (a current fiscal quarter can fill in later; a daily
job must not re-burn quota on transcript-less quarters every day).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "data" / "transcripts"
_URL = "https://www.alphavantage.co/query"
_EMPTY_RETRY_DAYS = 30


def default_quarters(today: dt.date) -> list[str]:
    """Current calendar quarter + the three before it, newest-first."""
    year, q = today.year, (today.month - 1) // 3 + 1
    out = []
    for _ in range(4):
        out.append(f"{year}Q{q}")
        q -= 1
        if q == 0:
            year, q = year - 1, 4
    return out


def _stored(out_dir: Path, ticker: str) -> set[str]:
    d = out_dir / ticker
    return ({p.stem for p in d.glob("*.json") if p.stem != "_empty"}
            if d.exists() else set())


def _empty_path(out_dir: Path, ticker: str) -> Path:
    return out_dir / ticker / "_empty.json"


def known_empty(out_dir: Path, ticker: str, *,
                today: dt.date | None = None) -> set[str]:
    p = _empty_path(out_dir, ticker)
    if not p.exists():
        return set()
    today = today or dt.date.today()
    marked = json.loads(p.read_text())
    return {q for q, iso in marked.items()
            if (today - dt.date.fromisoformat(iso)).days <= _EMPTY_RETRY_DAYS}


def mark_empty(out_dir: Path, ticker: str, quarter: str, *,
               today: dt.date | None = None) -> None:
    p = _empty_path(out_dir, ticker)
    p.parent.mkdir(parents=True, exist_ok=True)
    marked = json.loads(p.read_text()) if p.exists() else {}
    marked[quarter] = (today or dt.date.today()).isoformat()
    p.write_text(json.dumps(marked))


def select_auto(screen_path: Path, out_dir: Path, *,
                per_ticker: int) -> list[str]:
    """Pool names still needing quarters, fewest-stored-first (pool order
    within ties) — else a daily job re-pulls the same covered names."""
    survivors = [s["ticker"]
                 for s in json.loads(Path(screen_path).read_text())["survivors"]]
    needing = [t for t in survivors if len(_stored(out_dir, t)) < per_ticker]
    return sorted(needing, key=lambda t: len(_stored(out_dir, t)))


def fetch(ticker: str, quarter: str, key: str) -> dict:
    q = urllib.parse.urlencode({"function": "EARNINGS_CALL_TRANSCRIPT",
                                "symbol": ticker, "quarter": quarter,
                                "apikey": key})
    with urllib.request.urlopen(f"{_URL}?{q}", timeout=30) as resp:
        return json.loads(resp.read())


def _latest_screen() -> Path:
    screens = sorted((_ROOT / "data" / "screen").glob("*.json"))
    if not screens:
        raise SystemExit("--auto needs a data/screen/*.json survivor list")
    return screens[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default=None)
    ap.add_argument("--auto", action="store_true",
                    help="pick pool names fewest-stored-first from the "
                         "latest screen; run until quota or list end")
    ap.add_argument("--screen", default=None,
                    help="screen json for --auto (default: latest)")
    ap.add_argument("--quarters", default=",".join(
        default_quarters(dt.date.today())))
    ap.add_argument("--per-ticker", type=int, default=1,
                    help="stored quarters wanted per ticker (default 1)")
    args = ap.parse_args()
    if bool(args.tickers) == args.auto:
        raise SystemExit("exactly one of --tickers / --auto is required")
    key = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not key:
        raise SystemExit("ALPHAVANTAGE_API_KEY env var is required")

    quarters = args.quarters.split(",")
    if args.auto:
        screen = Path(args.screen) if args.screen else _latest_screen()
        tickers = select_auto(screen, _OUT, per_ticker=args.per_ticker)
        print(f"auto: {len(tickers)} pool names need quarters "
              f"(screen {screen.name}): {','.join(tickers) or '-'}")
    else:
        tickers = args.tickers.split(",")

    got, empty = [], []
    for i, t in enumerate(tickers):
        stored = _stored(_OUT, t)
        if len(stored) >= args.per_ticker:
            print(f"{t}: already stored ({sorted(stored, reverse=True)}), skip")
            got.append(t)
            continue
        skip = known_empty(_OUT, t)
        for quarter in quarters:
            if quarter in stored or quarter in skip:
                continue
            time.sleep(1.2)
            body = fetch(t, quarter, key)
            if "Information" in body:  # daily quota exhausted (or other
                # AV notice — key redacted: AV's quota message echoes the
                # full API key, which landed verbatim in transcripts.log
                notice = body["Information"].replace(key, "***")
                print(f"QUOTA HIT at {t} — AV says: {notice!r} "
                      f"— stored {len(got)}, remaining: {','.join(tickers[i:])}")
                return 2
            if body.get("transcript"):
                (_OUT / t).mkdir(parents=True, exist_ok=True)
                body["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                (_OUT / t / f"{quarter}.json").write_text(json.dumps(body))
                stored.add(quarter)
                n = len(body["transcript"])
                chars = sum(len(s["content"]) for s in body["transcript"])
                print(f"{t}: {quarter}, {n} turns, {chars} chars")
                if len(stored) >= args.per_ticker:
                    break
            else:
                # no transcript for this quarter (call not held / not
                # covered): remember for 30 days so the daily job does not
                # re-burn quota on it every morning
                mark_empty(_OUT, t, quarter)
        if stored:
            got.append(t)
        if len(stored) < args.per_ticker:
            print(f"{t}: only {len(stored)}/{args.per_ticker} quarters in "
                  f"{args.quarters}", file=sys.stderr)
            if not stored:
                empty.append(t)

    print(f"\nstored {len(got)}/{len(tickers)}; none-found: {empty or '-'}")
    return 1 if empty else 0


if __name__ == "__main__":
    sys.exit(main())

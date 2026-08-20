#!/usr/bin/env python3
"""Compile the judge-only market-context block (thesis-regime-v1 AC5).

Pulls the three FRED series live (T10Y3M, BAMLH0A0HYM2, VIXCLS) plus SPY
daily bars via the existing polygon wrapper, builds the regime snapshot,
renders the hashed text block, and writes it to data/market/<date>.md.
Omit-never-fake: any missing core series aborts with no file written.

Usage (needs POLYGON_API_KEY in the environment, e.g. via the .env-sourcing
launchd wrapper or a Jake-run shell):
    .venv/bin/python scripts/thesis_market.py [--as-of YYYY-MM-DD] [-v]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "code" / "src"))

from kairos.data.fred import clip_series, fetch_series
from kairos.data.polygon import fetch_aggs
from kairos.thesis.market_context import render, write_block
from kairos.thesis.regime import build_snapshot

logger = logging.getLogger("thesis_market")

# 430d back: 365d for the 12m return base + padding for weekends/holidays so
# a close at-or-before the cutoff always exists, and a full 1yr percentile
# window for the FRED series.
_LOOKBACK_DAYS = 430


def compile_block(as_of: str, *, extra_lines: list[str] | None = None):
    """Return the rendered MarketContext block as of `as_of`."""
    start = (_dt.date.fromisoformat(as_of)
             - _dt.timedelta(days=_LOOKBACK_DAYS)).isoformat()
    logger.debug("FRED window start=%s as_of=%s", start, as_of)
    series = {}
    for sid in ("T10Y3M", "BAMLH0A0HYM2", "VIXCLS"):
        # clip to as_of: fredgraph always serves to today, and a rewind
        # regime block reading post-as-of macro is a PIT leak (A1); a live
        # run (as_of=today) clips nothing
        series[sid] = clip_series(fetch_series(sid, start=start), end=as_of)
        logger.debug("%s: %d obs, latest %s", sid, len(series[sid]),
                     series[sid][-1])

    aggs = fetch_aggs("SPY", from_date=start, to_date=as_of)
    spy_closes = [
        (_dt.datetime.fromtimestamp(a.timestamp / 1000,
                                    tz=_dt.timezone.utc).date().isoformat(),
         a.close)
        for a in aggs
    ]
    logger.debug("SPY: %d bars, last %s", len(spy_closes),
                 spy_closes[-1] if spy_closes else None)

    snapshot = build_snapshot(
        t10y3m=series["T10Y3M"], hy_oas=series["BAMLH0A0HYM2"],
        vix=series["VIXCLS"], spy_closes=spy_closes,
    )
    block = render(snapshot, extra_lines=extra_lines)
    if block is None:
        raise SystemExit(
            "market block NOT compiled: a core series is missing or SPY "
            "history is short — omit-never-fake, no file written")
    return block


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=_dt.date.today().isoformat())
    ap.add_argument("--out-dir", default=str(_ROOT / "data" / "market"))
    ap.add_argument("--base-rate-line", default=None,
                    help="extra anchor line (rewind: the survivor 8wk "
                         "SPY-beat base rate) joined under the sha")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr, format="%(name)s %(levelname)s %(message)s")

    block = compile_block(
        args.as_of,
        extra_lines=[args.base_rate_line] if args.base_rate_line else None)
    out = Path(args.out_dir) / f"{args.as_of}.md"
    write_block(block, out)
    print(block.text)
    print(f"\nsha256 {block.sha256}")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

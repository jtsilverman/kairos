#!/usr/bin/env python3
"""Weekly mechanical screen, live (thesis-engine unit 3b). Manual runs only
until Jake arms a schedule.

Builds the bars field from Polygon grouped-daily (cached), runs the
all-hard-gate funnel, prints the survivor list + exclusions. Usage:

    .venv/bin/python scripts/weekly_screen.py [--as-of 2026-07-07] [--verbose]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code" / "src"))

from kairos import screen
from kairos.data import edgar, estimates
from kairos.data.polygon import fetch_grouped_daily

TRADING_DAYS = 253  # RS needs 252 returns; +1 close


def trading_days_back(as_of: dt.date, n: int) -> list[str]:
    days: list[str] = []
    d = as_of
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= dt.timedelta(days=1)
    return list(reversed(days))


def build_bars(as_of: dt.date) -> dict[str, screen.BarsSummary]:
    # current RS window + the t-21 prior-percentile lag (premove cohort);
    # ~5% weekday-holiday pad so >= keep real sessions land
    keep = TRADING_DAYS + screen.RS_RISING_LAG
    candidates = trading_days_back(as_of, keep + 16)
    # Field membership stays OLD-window-relative: a name is rankable iff it
    # has >= TRADING_DAYS closes within the original TRADING_DAYS+14
    # candidate suffix. Counting over the extended window instead admits
    # ~20 just-rankable young names and drifts every percentile vs the
    # cohort-1 baseline (caught live 2026-07-14: field 3815 vs stored 3793).
    suffix_start = len(candidates) - (TRADING_DAYS + 14)
    closes_by_ticker: dict[str, list[float]] = {}
    highs_by_ticker: dict[str, list[float]] = {}
    lows_by_ticker: dict[str, list[float]] = {}
    dvol_recent: dict[str, list[float]] = {}
    suffix_count: dict[str, int] = {}
    sessions = 0
    for day_idx, day in enumerate(candidates):
        bars = fetch_grouped_daily(day)
        if not bars:
            continue  # holiday
        sessions += 1
        in_suffix = day_idx >= suffix_start
        for b in bars:
            closes_by_ticker.setdefault(b.ticker, []).append(b.close)
            highs_by_ticker.setdefault(b.ticker, []).append(b.high)
            lows_by_ticker.setdefault(b.ticker, []).append(b.low)
            dvol_recent.setdefault(b.ticker, []).append(b.close * b.volume)
            if in_suffix:
                suffix_count[b.ticker] = suffix_count.get(b.ticker, 0) + 1
    logging.debug("build_bars: %d sessions, %d tickers", sessions, len(closes_by_ticker))

    out: dict[str, screen.BarsSummary] = {}
    lag = screen.RS_RISING_LAG
    for t, closes in closes_by_ticker.items():
        if suffix_count.get(t, 0) < TRADING_DAYS:
            continue  # < 12mo history in the original window: IPO exclusion
        closes = closes[-keep:]
        dvols_all = dvol_recent[t]
        prior_dvols = dvols_all[-(20 + lag):-lag]
        out[t] = screen.BarsSummary(
            price=closes[-1],
            dollar_vol_20d_median=statistics.median(dvols_all[-20:]),
            closes=closes,
            highs=highs_by_ticker[t][-keep:],
            lows=lows_by_ticker[t][-keep:],
            dollar_vol_20d_median_prior=(
                statistics.median(prior_dvols) if len(prior_dvols) == 20
                else None),
        )
    return out


def make_fundamentals_fetch(as_of: dt.date):
    """PIT gate fetcher (thesis-rewind-eval A2): companyfacts rows filed
    after as_of are invisible, so the gate judges the as-filed vintage.
    Identical path for the live weekly run (filed_lte=today serves the
    latest filings)."""
    memo: dict[str, screen.Fundamentals] = {}

    def fetch(ticker: str) -> screen.Fundamentals:
        # memoized: the profile fetcher re-reads shares for the PIT mcap,
        # and one companyfacts GET per name is enough
        if ticker not in memo:
            memo[ticker] = screen.fundamentals_from_facts(
                edgar.fetch_companyfacts(ticker),
                filed_lte=as_of.isoformat())
        return memo[ticker]
    return fetch


def make_profile_fetch(as_of: dt.date, bars: dict[str, screen.BarsSummary],
                       fundamentals_fetch) -> "callable":
    """PIT profile (A2): market cap = as-of close x vintage shares (the
    stale-sharecount-market-cap audit fix, live path included). Industry
    stays a live yfinance read — labels have no historical vintage anywhere
    (named degradation, spec Orientation)."""
    def fetch(ticker: str) -> screen.Profile:
        industry = estimates.profile(ticker)["industry"]
        mcap = screen.pit_market_cap(bars[ticker].price,
                                     fundamentals_fetch(ticker).shares)
        return screen.Profile(market_cap=mcap, industry=industry)
    return fetch


def _technicals(b: screen.BarsSummary) -> dict:
    """Stock-health context for the dossier [P1] line. high/low_52wk come
    from intraday HIGH/LOW bars: close-based values understate the range
    (AMAT printed high_52wk 723.0 beside a Form-4 sale @ 735.22)."""
    closes = list(b.closes)
    high = max(b.highs[-252:])
    return {
        "high_52wk": round(high, 2),
        "low_52wk": round(min(b.lows[-252:]), 2),
        "pct_off_high": round(b.price / high - 1.0, 4),
        "ma50": round(sum(closes[-50:]) / 50, 2),
        "ma200": round(sum(closes[-200:]) / 200, 2),
        "dollar_vol_20d_median": round(b.dollar_vol_20d_median),
    }


def payload(as_of: dt.date, result: screen.ScreenResult,
            bars: dict[str, screen.BarsSummary], *, cohort: str | None = None) -> dict:
    """Survivors JSON payload. cohort=None keeps the cohort-1 shape
    byte-identical (no cohort key — downstream consumers pin the old shape);
    a named cohort tags the payload for the ledger thread."""
    p = {
        "as_of": as_of.isoformat(),
        "survivors": [
            {"ticker": c.ticker, "rs": c.rs, "forensics": c.forensics,
             "price": bars[c.ticker].price,
             "technicals": _technicals(bars[c.ticker])}
            for c in sorted(result.survivors, key=lambda c: c.rs, reverse=True)
        ],
        "exclusions": result.exclusions,
    }
    if cohort is not None:
        p["cohort"] = cohort
    return p


def default_json_path(as_of: dt.date, cohort: str | None) -> Path | None:
    """Cohort runs write their survivors file by default, OUTSIDE the
    data/screen/*.json glob (pull_transcripts._latest_screen would otherwise
    lexicographic-resolve a cohort file as 'the' screen). Cohort-1 default
    stays no-write (unchanged)."""
    if cohort is None:
        return None
    return Path("data/screen") / cohort / f"{as_of.isoformat()}.json"


def revisions_fetch(ticker: str) -> "estimates.RevisionSnapshot":
    return estimates.revision_snapshot(ticker)


def main() -> int:
    from kairos import config

    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None, help="last completed trading day (ISO)")
    ap.add_argument("--json", default=None,
                    help="also write survivors+exclusions to this path")
    ap.add_argument("--cohort", default=None, choices=["premove"],
                    help="run the named cohort-2 funnel instead of the RS>=90 screen")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr, format="%(name)s %(levelname)s %(message)s")

    as_of = (dt.date.fromisoformat(args.as_of) if args.as_of
             else dt.date.today() - dt.timedelta(days=1))
    label = f" cohort={args.cohort}" if args.cohort else ""
    print(f"weekly screen as of {as_of}{label}", flush=True)

    bars = build_bars(as_of)
    print(f"field: {len(bars)} names with full history", flush=True)

    fundamentals_fetch = make_fundamentals_fetch(as_of)
    profile_fetch = make_profile_fetch(as_of, bars, fundamentals_fetch)
    if args.cohort == "premove":
        result = screen.run_premove_screen(
            bars, profile_fetch=profile_fetch,
            fundamentals_fetch=fundamentals_fetch,
            revisions_fetch=revisions_fetch,
            net_up_floor=config.PREMOVE_NET_UP_FLOOR)
    else:
        result = screen.run_screen(
            bars, profile_fetch=profile_fetch,
            fundamentals_fetch=fundamentals_fetch)

    print(f"\nSURVIVORS ({len(result.survivors)}):")
    for c in sorted(result.survivors, key=lambda c: c.rs, reverse=True):
        fx = {k: (round(v, 3) if isinstance(v, float) else v)
              for k, v in c.forensics.items()}
        print(f"  {c.ticker:6s} RS {c.rs:5.1f}  forensics {json.dumps(fx)}")
    print(f"\nEXCLUSIONS at fetch stage ({len(result.exclusions)}):")
    for t, reason in sorted(result.exclusions.items()):
        print(f"  {t:6s} {reason}")
    if len(result.survivors) > 100:
        print("\nANOMALY: > 100 survivors — surface to Jake before the LLM stage.")
    json_path = Path(args.json) if args.json else default_json_path(as_of, args.cohort)
    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(
            payload(as_of, result, bars, cohort=args.cohort), indent=1))
        print(f"\nwrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

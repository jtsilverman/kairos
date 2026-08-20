"""Analyst estimate-revision wrapper (thesis-engine unit 2): yfinance
eps_trend + eps_revisions -> the screen's archetype-1 revision signal.

yfinance is an UNOFFICIAL Yahoo transport (decision 2026-07-08: only viable
$0 source) -- every accessor fails loud on empty/missing frames rather than
degrading, because a silently-empty frame would read as "no positive signal"
and quietly starve the archetype-1 track.

Signal operationalization (framework doc, frozen): positive = breadth AND
magnitude agree -- net up-revisions over the last 30 days >= 0 AND the
current-year EPS estimate above its own value 90 days ago.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)

_YEAR_ROW = "0y"  # current fiscal year: the thesis horizon's estimate row


class MissingEstimatesError(Exception):
    """Estimate frames empty or missing the current-year row."""


@dataclass(frozen=True)
class RevisionSnapshot:
    net_up_30d: int          # up minus down revisions, last 30d, current FY
    trend_delta_90d: float   # current FY EPS estimate now vs 90 days ago
    positive: bool           # both breadth and magnitude agree


def revision_snapshot_from_frames(
    *, trend: pd.DataFrame, revisions: pd.DataFrame
) -> RevisionSnapshot:
    if trend.empty or revisions.empty:
        raise MissingEstimatesError("empty estimate frame(s)")
    if _YEAR_ROW not in trend.index or _YEAR_ROW not in revisions.index:
        raise MissingEstimatesError(f"no {_YEAR_ROW!r} row in estimate frames")
    net_up = int(revisions.loc[_YEAR_ROW, "upLast30days"]
                 - revisions.loc[_YEAR_ROW, "downLast30days"])
    delta = float(trend.loc[_YEAR_ROW, "current"] - trend.loc[_YEAR_ROW, "90daysAgo"])
    positive = net_up >= 0 and delta > 0
    logger.debug("revision_snapshot: net_up_30d=%d delta_90d=%.4f positive=%s",
                 net_up, delta, positive)
    return RevisionSnapshot(net_up_30d=net_up, trend_delta_90d=delta, positive=positive)


def profile_from_info(info: dict) -> dict:
    """{market_cap, industry} out of a yfinance .info payload, fail-loud on
    absent/None keys -- a None mcap passed downstream would fail the band gate
    silently as False and read as a legitimate exclusion."""
    mcap, industry = info.get("marketCap"), info.get("industry")
    if mcap is None or industry is None:
        raise MissingEstimatesError(f"profile missing marketCap/industry: {sorted(info)[:8]}")
    return {"market_cap": mcap, "industry": industry}


def profile(symbol: str) -> dict:
    """Live {market_cap, industry} via yfinance."""
    import yfinance as yf

    return profile_from_info(yf.Ticker(symbol).info or {})


def earnings_from_calendar(cal: dict, as_of: str | None = None) -> dict:
    """Next-earnings date + consensus bands out of a yfinance .calendar dict.
    Fail-loud on a missing date (an earnings-date-less [E1] would render
    nothing useful); consensus bands are optional — omit-never-fake.
    With as_of (ISO date): dates <= as_of are stale yfinance calendar rows
    (the already-reported print — BLZE 2026-05-04, PENG 2026-07-07); drop
    them, fail loud if none survive so [E1] omits rather than prints a past
    date. Date-prefix compare, never full-ISO lex."""
    dates = cal.get("Earnings Date") or []
    if not dates:
        raise MissingEstimatesError("calendar has no Earnings Date")
    if as_of is not None:
        dates = [d for d in dates if d.isoformat()[:10] > as_of[:10]]
        if not dates:
            raise MissingEstimatesError(
                f"all earnings dates stale (<= as_of {as_of})")
    out = {"next_earnings_date": min(dates).isoformat()}
    eps = {k: cal.get(f"Earnings {n}") for k, n in
           (("low", "Low"), ("avg", "Average"), ("high", "High"))}
    rev = {k: cal.get(f"Revenue {n}") for k, n in
           (("low", "Low"), ("avg", "Average"), ("high", "High"))}
    if all(v is not None for v in eps.values()):
        out["eps_consensus"] = eps
    if all(v is not None for v in rev.values()):
        out["revenue_consensus"] = rev
    logger.debug("earnings_from_calendar: %s", out)
    return out


def next_earnings(symbol: str, as_of: str | None = None) -> dict:
    """Live next-earnings snapshot via yfinance."""
    import yfinance as yf

    return earnings_from_calendar(yf.Ticker(symbol).calendar or {}, as_of=as_of)


def dispersion_from_estimate_frame(frame: pd.DataFrame) -> dict:
    """Current-FY estimate dispersion from a yfinance earnings_estimate
    frame: {low, high, avg, spread, analysts}, spread = (high-low)/|avg|
    (high dispersion predicts lower returns up to ~9 months — an [E1] LLM
    input, not a gate). Fail-loud on missing/NaN bands or zero avg — a
    silently-faked spread would be cited as evidence."""
    import math

    if frame.empty or _YEAR_ROW not in frame.index:
        raise MissingEstimatesError(f"no {_YEAR_ROW!r} row in earnings_estimate")
    row = frame.loc[_YEAR_ROW]
    low, high, avg = float(row["low"]), float(row["high"]), float(row["avg"])
    analysts = float(row["numberOfAnalysts"])
    if (any(not math.isfinite(v) for v in (low, high, avg, analysts))
            or avg == 0.0):
        raise MissingEstimatesError(
            f"unusable estimate bands: low={low} high={high} avg={avg} "
            f"analysts={analysts}")
    out = {"low": low, "high": high, "avg": avg,
           "spread": (high - low) / abs(avg),
           "analysts": int(analysts)}
    logger.debug("dispersion: %s", out)
    return out


def earnings_dispersion(symbol: str) -> dict:
    """Live current-FY dispersion via yfinance."""
    import yfinance as yf

    frame = yf.Ticker(symbol).earnings_estimate
    if frame is None:
        raise MissingEstimatesError(f"no earnings_estimate frame for {symbol}")
    return dispersion_from_estimate_frame(frame)


def revision_snapshot(symbol: str) -> RevisionSnapshot:
    """Live snapshot via yfinance (import deferred: the unofficial dependency
    stays out of test collection)."""
    import yfinance as yf

    t = yf.Ticker(symbol)
    trend, revisions = t.eps_trend, t.eps_revisions
    if trend is None or revisions is None:
        raise MissingEstimatesError(f"yfinance returned no estimate frames for {symbol}")
    return revision_snapshot_from_frames(trend=trend, revisions=revisions)



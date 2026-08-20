"""Opening-range breakout signal core (orb-0dte-spy): RTH clamp, OR high/low,
first-close-through-range breakout detection. Consumed by the Stage-1 excursion
gate and the Stage-2 backtest.

Bars are Agg-shaped (epoch-ms ``timestamp``, open/high/low/close). All session
math converts through America/New_York: a fixed-UTC clamp misreads winter opens
by an hour (EST vs EDT), and Polygon option aggs carry post-close prints (probe
2026-05-15: bars to 20:14 UTC) that must not leak into same-day exit logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_OPEN = time(9, 30)
_CLOSE = time(16, 0)


def _et(bar) -> datetime:
    return datetime.fromtimestamp(bar.timestamp / 1000, tz=_ET)


def rth_bars(bars):
    """Bars within regular trading hours [9:30, 16:00) ET, DST-aware."""
    return [b for b in bars if _OPEN <= _et(b).time() < _CLOSE]


def opening_range(bars, *, minutes: int):
    """(high, low) of the first `minutes` RTH bars. Raises on a short session
    (fewer RTH bars than the range needs) -- a truncated feed must fail loud,
    not produce a fake narrow range."""
    rth = rth_bars(bars)
    if len(rth) < minutes:
        raise ValueError(f"only {len(rth)} RTH bars; opening range needs {minutes}")
    window = rth[:minutes]
    return max(b.high for b in window), min(b.low for b in window)


@dataclass(frozen=True)
class Breakout:
    side: str          # "long" | "short"
    bar_index: int     # index into rth_bars(bars) of the breakout CLOSE
    entry_price: float # next bar's open (the executable fill anchor)
    or_high: float
    or_low: float


def detect_breakout(bars, *, minutes: int, cutoff_minutes: int):
    """First RTH bar after the opening range whose CLOSE exceeds the OR high
    (long) or undercuts the OR low (short), within `cutoff_minutes` of the open.
    Entry anchors at the NEXT bar's open; a breakout on the session's last bar
    (no next bar to enter on) returns None."""
    rth = rth_bars(bars)
    if len(rth) < minutes:
        return None
    or_high, or_low = opening_range(bars, minutes=minutes)
    open_et = _et(rth[0])
    for i in range(minutes, len(rth) - 1):
        if (_et(rth[i]) - open_et).total_seconds() / 60.0 > cutoff_minutes:
            return None
        if rth[i].close > or_high:
            return Breakout("long", i, rth[i + 1].open, or_high, or_low)
        if rth[i].close < or_low:
            return Breakout("short", i, rth[i + 1].open, or_high, or_low)
    return None

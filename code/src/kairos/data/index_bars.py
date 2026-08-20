"""Daily index/underlying OHLC bars (Yahoo) for the vol-hedge term-structure gate.

The hedge gate needs a daily ``^VIX`` and ``^VIX3M`` series (VIX3M/VIX < 1 =
backwardation = spike regime). Yahoo's chart endpoint is the free source; bars
land in the ``daily_index_bars`` ledger table (persist), and the backtest reads a
date window (read). ``fetch_index_daily`` is the network edge — live-smoked, never
hit in a unit test (MagicMock masks a wrong URL shape).

Stub state: ``read_index_window`` / ``fetch_index_daily`` are not yet implemented
(RED). ``persist_index_bars`` is the seed path the read test needs.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone


@dataclass(frozen=True)
class IndexBar:
    """One daily bar. ``date`` is a bare ISO string (YYYY-MM-DD)."""

    symbol: str
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float


def persist_index_bars(conn: sqlite3.Connection, bars: list[IndexBar]) -> int:
    """Upsert bars into ``daily_index_bars``. Returns the count written.

    INSERT OR REPLACE on the (symbol, date) PK: a re-fetch of the same day
    overwrites rather than duplicating or erroring.
    """
    rows = [(b.symbol, b.date, b.open, b.high, b.low, b.close) for b in bars]
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO daily_index_bars "
            "(symbol, date, open, high, low, close) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def read_index_window(
    conn: sqlite3.Connection, symbol: str, start: str, end: str
) -> list[IndexBar]:
    """Bars for ``symbol`` in the inclusive [start, end] date window, date-ordered."""
    rows = conn.execute(
        "SELECT symbol, date, open, high, low, close FROM daily_index_bars "
        "WHERE symbol = ? AND date >= ? AND date <= ? ORDER BY date",
        (symbol, start, end),
    ).fetchall()
    return [IndexBar(*r) for r in rows]


def fetch_index_daily(symbol: str, start: str, end: str) -> list[IndexBar]:
    """Fetch daily bars for a Yahoo symbol (e.g. ``^VIX``) over [start, end].

    Uses the Yahoo chart endpoint with explicit period1/period2 unix seconds
    (``range=max`` returns a monthly series — do not use it). Bars whose close is
    ``None`` (today's incomplete intraday bar, holidays) are dropped. Network
    edge; live-smoked, not unit-tested (MagicMock masks a wrong URL shape).
    """
    p1 = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    # +1 day so the end date's bar is included (period2 is exclusive).
    p2 = int(
        datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    ) + 86_400
    q = urllib.request.quote(symbol)
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}"
        f"?period1={p1}&period2={p2}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    result = payload["chart"]["result"][0]
    ts = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    bars: list[IndexBar] = []
    for i, t in enumerate(ts):
        close = quote["close"][i]
        if close is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
        bars.append(
            IndexBar(
                symbol=symbol,
                date=d,
                open=quote["open"][i],
                high=quote["high"][i],
                low=quote["low"][i],
                close=close,
            )
        )
    return bars

"""Earnings events cache — the PEAD anchor.

Populated by an agent sweep of the universe via the RH MCP `get_earnings_results`
(MCP is callable only inside a Claude session; the Python backtest reads this table,
never the MCP directly). `parse_mcp_earnings_results` converts the MCP payload to
rows; `persist_earnings_events` upserts them; `read_earnings_events` serves the
backtest. Dates are ISO; the date-window filter is half-open [since, until).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class EarningsEvent:
    symbol: str
    year: int
    quarter: int
    report_date: str  # ISO YYYY-MM-DD
    timing: str | None  # "am" | "pm" | None
    eps_estimate: float | None
    eps_actual: float | None
    surprise_pct: float | None
    verified: bool


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_surprise_pct(estimate: float | None, actual: float | None) -> float | None:
    """(actual - estimate) / abs(estimate). None if either missing or estimate is 0."""
    if estimate is None or actual is None or estimate == 0:
        return None
    return (actual - estimate) / abs(estimate)


def parse_mcp_earnings_results(payload: dict[str, Any]) -> list[EarningsEvent]:
    """Parse a get_earnings_results payload into EarningsEvent rows.

    Accepts the full ``{"data": {"results": [...]}}`` envelope or a bare results
    list. Entries whose actual EPS is null (not yet reported) are dropped.
    """
    if isinstance(payload, dict):
        results = payload.get("data", {}).get("results", payload.get("results", []))
    else:
        results = payload
    events: list[EarningsEvent] = []
    for r in results:
        eps = r.get("eps", {})
        estimate = _to_float(eps.get("estimate"))
        actual = _to_float(eps.get("actual"))
        if actual is None:
            continue  # unreported quarter
        report = r.get("report", {})
        events.append(
            EarningsEvent(
                symbol=r["symbol"],
                year=int(r["year"]),
                quarter=int(r["quarter"]),
                report_date=report["date"],
                timing=report.get("timing"),
                eps_estimate=estimate,
                eps_actual=actual,
                surprise_pct=compute_surprise_pct(estimate, actual),
                verified=bool(report.get("verified", False)),
            )
        )
    return events


def persist_earnings_events(
    conn: sqlite3.Connection, events: list[EarningsEvent]
) -> int:
    """Upsert events keyed on (symbol, year, quarter). Returns the count written."""
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO earnings_events "
            "(symbol, year, quarter, report_date, timing, eps_estimate, eps_actual, "
            " surprise_pct, verified, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    e.symbol, e.year, e.quarter, e.report_date, e.timing,
                    e.eps_estimate, e.eps_actual, e.surprise_pct,
                    1 if e.verified else 0, now,
                )
                for e in events
            ],
        )
    return len(events)


def earnings_between(
    conn: sqlite3.Connection,
    symbol: str,
    start: date,
    end: date,
) -> list[date]:
    """Report dates for `symbol` falling in the INCLUSIVE window [start, end], sorted.

    Inclusive on both ends: a trade that is still open ON its exit day held THROUGH an
    earnings report landing that day, so `end` must count. `read_earnings_events` takes
    a half-open [since, until) window, so the inclusive upper bound is `end + 1 day`."""
    evs = read_earnings_events(
        conn,
        symbol=symbol,
        since=start.isoformat(),
        until=(end + timedelta(days=1)).isoformat(),
    )
    return [date.fromisoformat(e.report_date) for e in evs]


def read_earnings_events(
    conn: sqlite3.Connection,
    *,
    symbol: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[EarningsEvent]:
    """Read events, optionally filtered by symbol and a half-open [since, until)
    report-date window. Sorted by report_date ascending."""
    clauses: list[str] = []
    params: list[Any] = []
    if symbol is not None:
        clauses.append("symbol = ?")
        params.append(symbol)
    if since is not None:
        clauses.append("report_date >= ?")
        params.append(since)
    if until is not None:
        clauses.append("report_date < ?")
        params.append(until)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        "SELECT symbol, year, quarter, report_date, timing, eps_estimate, eps_actual, "
        "surprise_pct, verified FROM earnings_events" + where + " ORDER BY report_date",
        params,
    ).fetchall()
    return [
        EarningsEvent(
            symbol=r[0], year=r[1], quarter=r[2], report_date=r[3], timing=r[4],
            eps_estimate=r[5], eps_actual=r[6], surprise_pct=r[7], verified=bool(r[8]),
        )
        for r in rows
    ]

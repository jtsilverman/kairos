"""Fetch full-history observations from FRED for one series id.

Reads the public, keyless CSV endpoint at
``https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series>`` (the same URL
the browser hits on a FRED graph's Download button; idiom shared with
wealth-manager's latest-value fetcher, extended here to full history because
the regime snapshot needs 1yr percentiles and trends). Live probe 2026-07-10:
a 200 response is a two-column CSV ``observation_date,<SERIES_ID>``; missing
observations arrive as EMPTY cells (holiday rows) in current responses, with
``.`` the documented legacy marker (both skipped); a missing series id returns
HTTP 404 with an HTML error page; ``cosd=<YYYY-MM-DD>`` pins the window start
(BAMLH0A0HYM2 otherwise defaults to a 3yr window).
"""

from __future__ import annotations

import csv
import io
import urllib.error
from urllib.parse import urlencode
from urllib.request import urlopen

ENDPOINT = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def fetch_series(
    series_id: str, *, start: str | None = None, timeout: float = 15.0
) -> list[tuple[str, float]]:
    """Return the full ``[(iso_date, value), ...]`` history, oldest first.

    Raises ValueError on an unknown series id (FRED 404s it) and on a series
    whose window carries no numeric observation (all ``.`` markers).
    """
    params = {"id": series_id}
    if start is not None:
        params["cosd"] = start
    url = f"{ENDPOINT}?{urlencode(params)}"
    try:
        with urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise ValueError(
                f"FRED series {series_id!r} not found (HTTP 404)") from err
        raise ValueError(
            f"FRED series {series_id!r} fetch failed: HTTP {err.code}") from err
    return _parse(series_id, body)


def _parse(series_id: str, body: str) -> list[tuple[str, float]]:
    rows = list(csv.reader(io.StringIO(body)))
    series: list[tuple[str, float]] = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        cell = row[1].strip()
        if not cell or cell == ".":
            continue
        series.append((row[0].strip(), float(cell)))
    if not series:
        raise ValueError(f"FRED series {series_id!r} returned no numeric observations")
    return series


def clip_series(
    series: list[tuple[str, float]], *, end: str
) -> list[tuple[str, float]]:
    """Observations on or before `end` (ISO date). fetch_series has no end
    param (the CSV endpoint always serves to today), so a rewind caller must
    clip before the regime math or the 1yr percentiles read future macro."""
    return [(d, v) for d, v in series if d <= end]

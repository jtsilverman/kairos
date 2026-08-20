"""FINRA consolidated short interest wrapper (dossier-v4 unit 3): the [S1]
section's data source. Keyless POST to the otcMarket/consolidatedShortInterest
dataset (covers listed names despite the group name; the similarly-named
equityShortInterest dataset is OTC-only — MU returns 204 empty — never use it).

Live-probed 2026-07-09/10: JSON needs `Accept: application/json` (default is
CSV); filter = compareFilters EQUAL symbolCode + dateRangeFilters on
settlementDate (sortFields rejected without a settlementDate EQUAL filter).
Settlements are bi-weekly. Fail-loud on error payloads and missing fields —
a silently-empty read would render as "no short-interest data" and hide a
squeeze/crowding signal.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)

_URL = ("https://api.finra.org/data/group/otcMarket/name/"
        "consolidatedShortInterest")
# bi-weekly settlements: ~140 days comfortably covers 6 plus publication lag
_WINDOW_DAYS = 140


class FinraError(Exception):
    """Error payload or unrecognized row shape from the FINRA API."""


def _contact() -> str:
    """FINRA 500s on the default Python-urllib User-Agent (live 2026-07-10)."""
    from kairos import config  # noqa: PLC0415
    return config.CONTACT


def short_interest_rows(payload) -> list[dict]:
    """API payload -> ascending-settlement rows {settlement_date,
    short_shares, days_to_cover, change_pct}."""
    if not isinstance(payload, list):
        raise FinraError(f"error payload: {payload!r}")
    rows = []
    for r in payload:
        try:
            rows.append({
                "settlement_date": r["settlementDate"],
                "short_shares": int(r["currentShortPositionQuantity"]),
                "days_to_cover": float(r["daysToCoverQuantity"]),
                "change_pct": float(r["changePercent"]),
            })
        except (KeyError, TypeError) as e:
            raise FinraError(f"row missing field {e}: {sorted(r)}") from None
    rows.sort(key=lambda r: r["settlement_date"])
    logger.debug("short_interest_rows: %d settlements", len(rows))
    return rows


def fetch_short_interest(ticker: str, *, settlements: int = 6,
                         as_of: _dt.date | None = None) -> list[dict]:
    """Live last-N-settlement rows for a ticker (ascending)."""
    end = as_of or _dt.date.today()
    body = json.dumps({
        "compareFilters": [{"compareType": "EQUAL", "fieldName": "symbolCode",
                            "fieldValue": ticker}],
        "dateRangeFilters": [{
            "fieldName": "settlementDate",
            "startDate": (end - _dt.timedelta(days=_WINDOW_DAYS)).isoformat(),
            "endDate": end.isoformat()}],
        "limit": 50,
    }).encode()
    # FINRA 500s on the default Python-urllib User-Agent (live 2026-07-10)
    req = urllib.request.Request(_URL, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": _contact()})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    return short_interest_rows(payload)[-settlements:]

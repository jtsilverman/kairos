"""Macro-regime snapshot for the thesis-engine JUDGE seat (thesis-regime-v1).

Pure computation over INJECTED series — no fetching here (kairos.data.fred
and the polygon wrapper feed scripts/thesis_market.py, which adapts to the
``[(iso_date, value), ...]`` shape). Four facts + one flag, deliberately
minimal (no regime state machine, no tilts): T10Y3M slope, HY OAS level +
1yr percentile + trend, VIX level + 1yr percentile, SPY trailing-12m return,
and the Daniel-Moskowitz momentum-crash-risk flag (trailing market return
negative AND vol elevated). Any missing core series returns None —
omit-never-fake: a partial snapshot must never masquerade as the market
state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from kairos import config

Series = list[tuple[str, float]]  # [(iso_date, value), ...] oldest first


@dataclass(frozen=True)
class RegimeSnapshot:
    t10y3m: float
    hy_oas_level: float
    hy_oas_pctile_1yr: float
    hy_oas_trend: str  # widening | narrowing | flat
    vix_level: float
    vix_pctile_1yr: float
    spy_12m_return: float
    momentum_crash_risk: bool


def build_snapshot(
    *,
    t10y3m: Series | None,
    hy_oas: Series | None,
    vix: Series | None,
    spy_closes: Series | None,
) -> RegimeSnapshot | None:
    if not t10y3m or not hy_oas or not vix or not spy_closes:
        return None
    spy_12m = _trailing_12m_return(spy_closes)
    if spy_12m is None:
        return None
    vix_pctile = _pctile_1yr(vix)
    return RegimeSnapshot(
        t10y3m=t10y3m[-1][1],
        hy_oas_level=hy_oas[-1][1],
        hy_oas_pctile_1yr=_pctile_1yr(hy_oas),
        hy_oas_trend=_trend(hy_oas),
        vix_level=vix[-1][1],
        vix_pctile_1yr=vix_pctile,
        spy_12m_return=spy_12m,
        momentum_crash_risk=(
            spy_12m < 0 and vix_pctile >= config.REGIME_VIX_CRASH_PCTILE
        ),
    )


def _pctile_1yr(series: Series) -> float:
    """Inclusive rank of the latest value within the trailing 365 days."""
    latest_date = date.fromisoformat(series[-1][0])
    cutoff = latest_date - timedelta(days=365)
    window = [v for d, v in series if date.fromisoformat(d) >= cutoff]
    latest = series[-1][1]
    return sum(1 for v in window if v <= latest) / len(window)


def _trend(series: Series) -> str:
    ref = series[max(0, len(series) - 1 - config.REGIME_OAS_TREND_LOOKBACK_OBS)][1]
    latest = series[-1][1]
    if latest > ref:
        return "widening"
    if latest < ref:
        return "narrowing"
    return "flat"


def _trailing_12m_return(spy_closes: Series) -> float | None:
    """Last close vs the close at-or-before (last date - 365d); None if the
    history does not reach back that far."""
    last_date = date.fromisoformat(spy_closes[-1][0])
    cutoff = last_date - timedelta(days=365)
    base = None
    for d, v in spy_closes:
        if date.fromisoformat(d) <= cutoff:
            base = v
        else:
            break
    if base is None:
        return None
    return spy_closes[-1][1] / base - 1.0

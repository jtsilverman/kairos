"""Mechanical screen (thesis-engine unit 3b): weekly all-hard-gate funnel from
the whole market to the thesis-engine survivor list.

Redesigned 2026-07-08 (Jake): no mcap band, no admission tracks, no ranking —
every survivor goes to the LLM. Pure filter logic on injected records; fetching
lives in the runner. Frozen numbers per docs/framework-thesis-engine.md:
admission $10 price / $25M dollar-vol / $500M mcap floor, trend template
(close > 50d MA > 200d MA, 200d rising vs 21 sessions ago), RS >= 90 over the
broad $5/$5M percentile field, revenue growth > 0 + OCF > 0 (latest annual).
Forensic accrual ratios are COMPUTED per survivor for the LLM's dimension-7
read, never gates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)

Series = Sequence[tuple[str, float]]  # ordered [(period_end, value)]

_RS_FIELD_PRICE = 5.0
_RS_FIELD_DVOL = 5_000_000.0
_PRICE_FLOOR = 10.0
_DVOL_FLOOR = 25_000_000.0
_MCAP_FLOOR = 500_000_000
_RS_ADMIT = 90.0
_MA_RISING_SESSIONS = 21
_PREMOVE_RS_MIN = 70.0
# Public: the runner's bars window must cover TRADING_DAYS + this lag, or
# every prior percentile silently reads None (rising never fires). Frozen
# with the entry-gate "rising vs 21 sessions ago" (framework doc).
RS_RISING_LAG = 21


@dataclass(frozen=True)
class BarsSummary:
    price: float
    dollar_vol_20d_median: float
    closes: Sequence[float]
    # intraday ranges for [P1] high/low_52wk; close-based highs understate
    # the true range (a Form-4 sale printed above the section's own "high").
    # None only for screen-gate paths that never render [P1].
    highs: Sequence[float] | None = None
    lows: Sequence[float] | None = None
    # 20d dollar-vol median ending RS_RISING_LAG sessions ago; None = unknown
    # (short dvol history), which reads as ineligible at t-21, never eligible.
    dollar_vol_20d_median_prior: float | None = None


@dataclass(frozen=True)
class Fundamentals:
    revenue: Series
    receivables: Series
    net_income: Series
    operating_cash_flow: Series
    shares: Series


@dataclass(frozen=True)
class Profile:
    market_cap: float
    industry: str


@dataclass(frozen=True)
class Candidate:
    ticker: str
    rs: float
    forensics: dict[str, float | int | None]


@dataclass(frozen=True)
class ScreenResult:
    survivors: list[Candidate]
    exclusions: dict[str, str]  # ticker -> reason, for names that reached fetching


def rs_field_eligible(b: BarsSummary) -> bool:
    """The broad percentile field: RS ~ 'top decile of tradeable US stocks'."""
    return b.price >= _RS_FIELD_PRICE and b.dollar_vol_20d_median >= _RS_FIELD_DVOL


def admission_eligible(b: BarsSummary) -> bool:
    return b.price >= _PRICE_FLOOR and b.dollar_vol_20d_median >= _DVOL_FLOOR


def premove_band(pct: float) -> bool:
    """Cohort-2 admission band [70, 90), half-open: the upper bound IS the
    cohort-1 threshold, so the two cohorts cannot overlap by construction."""
    return _PREMOVE_RS_MIN <= pct < _RS_ADMIT


def premove_rising(*, current: float, prior: float | None) -> bool:
    """Strictly rising vs the t-21 percentile snapshot. A None prior
    (unrankable or field-ineligible at t-21) is never rising: a name whose
    month-ago rank is unknown cannot prove direction of travel."""
    return prior is not None and current > prior


def prior_field_percentiles(
    bars_by_ticker: dict[str, BarsSummary],
) -> dict[str, float]:
    """The RS percentile field as it stood RS_RISING_LAG sessions ago.

    Eligibility is evaluated WITH t-21 data (spec U1): price = the t-21
    close, dollar-vol = BarsSummary.dollar_vol_20d_median_prior (None =
    unknown = ineligible). The lag indexes each name's own session series,
    the same appearance-indexed discipline as rs_raw's windows. Names
    unrankable at t-21 (< 253 closes then) drop out via rs_raw None."""
    from kairos.signals import rs

    scores: dict[str, float | None] = {}
    for t, b in bars_by_ticker.items():
        if len(b.closes) <= RS_RISING_LAG:
            continue
        prior_closes = b.closes[:-RS_RISING_LAG]
        if prior_closes[-1] < _RS_FIELD_PRICE:
            continue
        if (b.dollar_vol_20d_median_prior is None
                or b.dollar_vol_20d_median_prior < _RS_FIELD_DVOL):
            continue
        scores[t] = rs.rs_raw(prior_closes)
    pct = rs.rs_percentile(scores)
    logger.debug("prior_field_percentiles: %d eligible at t-%d, %d ranked",
                 len(scores), RS_RISING_LAG, len(pct))
    return pct


def fundamentals_from_facts(facts: dict, *,
                            filed_lte: str | None = None) -> Fundamentals:
    """Fundamentals from a companyfacts JSON. `filed_lte` (ISO date) serves
    the as-filed vintage for a rewind screen: rows filed after the bound are
    invisible, so the gate judges the numbers the market had at as_of
    (thesis-rewind-eval A2)."""
    from kairos.data import edgar

    def series(tags):
        return edgar.annual_series(facts, tags, filed_lte=filed_lte)

    return Fundamentals(
        revenue=series(edgar.REVENUE_TAGS),
        receivables=series(edgar.RECEIVABLES_TAGS),
        net_income=series(edgar.NET_INCOME_TAGS),
        operating_cash_flow=series(edgar.OPERATING_CASH_FLOW_TAGS),
        shares=series(edgar.SHARES_TAGS),
    )


def stratified_rs_sample(survivors: list[dict], *, per_quartile: int = 5,
                         seed: int) -> list[dict]:
    """Seeded stratified cohort draw (thesis-rewind-eval A3): survivors are
    ranked by RS, split into four contiguous quartile blocks (lowest first,
    larger blocks first on uneven n), and `per_quartile` names are drawn at
    RANDOM from each block. Representative across the RS spread with nothing
    admitted BY rank (the random-top-K lesson). An under-full quartile
    drains entirely; the draw never invents names. Same seed, same draw."""
    import random

    ranked = sorted(survivors, key=lambda s: s["rs"])
    n = len(ranked)
    sizes = [n // 4 + (1 if i < n % 4 else 0) for i in range(4)]
    rng = random.Random(seed)
    out: list[dict] = []
    start = 0
    for size in sizes:
        block = ranked[start:start + size]
        start += size
        take = min(per_quartile, len(block))
        out.extend(rng.sample(block, take))
    return out


def pit_market_cap(close: float, shares: Series,
                   *, split_factor: float = 1.0) -> float:
    """as-of close x latest vintage share count. Replaces the live provider
    profile mcap for a rewind screen AND the live dossier (the
    stale-sharecount-market-cap audit fix): the shares series arrives
    already filed-bounded, so the product is point-in-time by construction.

    `split_factor` reconciles the two feeds. Grouped-daily closes are
    SPLIT-ADJUSTED; the filed share count is not. A company that split between
    the filing and the as-of date therefore has a price on one basis and a
    share count on another, and the product is wrong by the split ratio. Pass
    the cumulative ratio of splits executed after the filing period end and on
    or before the as-of date (25.0 for a 25-for-1, 0.1 for a 1-for-10).
    Default 1.0 leaves every existing caller unchanged.

    Caught live 2026-08-18: Booking Holdings split 1-for-25 on 2026-04-06 and
    the screen reported a $6.9B market cap against roughly $163B."""
    return close * shares[-1][1] * split_factor


def mcap_floor_pass(mcap: float) -> bool:
    return mcap >= _MCAP_FLOOR


def trend_template(closes: Sequence[float]) -> bool:
    """Minervini-lite: close > 50d MA > 200d MA, 200d MA rising vs 21 sessions
    ago. Requires 200 + 21 closes; shorter history cannot be judged and fails."""
    if len(closes) < 200 + _MA_RISING_SESSIONS:
        return False
    close = closes[-1]
    ma50 = sum(closes[-50:]) / 50
    ma200 = sum(closes[-200:]) / 200
    ma200_prior = sum(closes[-200 - _MA_RISING_SESSIONS:-_MA_RISING_SESSIONS]) / 200
    return close > ma50 > ma200 and ma200 > ma200_prior


def _growth(series: Series) -> float | None:
    """YoY growth; None when the prior-year base is zero (SPAC/shell filers)
    — growth vs a zero base is unjudgeable, and a raw division killed a
    whole as-of sweep (ZeroDivisionError, 2025-07-07)."""
    prior = series[-2][1]
    if prior == 0:
        return None
    return series[-1][1] / prior - 1.0


def fundamentals_pass(f: Fundamentals) -> bool:
    """Revenue growth > 0 (latest annual vs prior) AND OCF > 0 (latest annual).
    An unjudgeable growth (zero prior-year base) fails the name."""
    if len(f.revenue) < 2 or not f.operating_cash_flow:
        return False
    g = _growth(f.revenue)
    return g is not None and g > 0 and f.operating_cash_flow[-1][1] > 0


def technicals(b: BarsSummary) -> dict:
    """Stock-health context for the dossier's [P1] line.

    high/low_52wk come from intraday HIGH/LOW bars: close-based values
    understate the range (AMAT printed high_52wk 723.0 beside a Form-4 sale
    at 735.22).
    """
    closes = list(b.closes)
    high = max(b.highs[-252:])
    return {
        "high_52wk": round(high, 2),
        "low_52wk": round(min(b.lows[-252:]), 2),
        "pct_off_high": round(b.price / high - 1.0, 4),
        "ma50": round(sum(closes[-50:]) / len(closes[-50:]), 2),
        "ma200": round(sum(closes[-200:]) / len(closes[-200:]), 2),
        "dollar_vol_20d_median": round(b.dollar_vol_20d_median),
    }


def dossier_row(*, ticker: str, cik: int | None, sic: int | None, rs: float,
                rev_growth: float | None, market_cap: float,
                bars: BarsSummary, series: dict) -> dict:
    """One survivor, in the shape `thesis_dossiers.py` reads.

    The rule-out screen and the weekly screen emitted two different survivor
    shapes and nothing bridged them, so a real compile failed 25 of 25 on
    `KeyError: 'price'`. This is that bridge, and it lives beside `forensics`
    so the ratios have exactly one definition.
    """
    return {
        "ticker": ticker,
        "cik": cik,
        "sic": sic,
        "rs": rs,
        "rev_growth": rev_growth,
        "mcap_b": round(market_cap / 1e9, 2),
        "price": bars.price,
        "technicals": technicals(bars),
        "forensics": forensics(Fundamentals(
            revenue=series.get("revenue") or [],
            receivables=series.get("receivables") or [],
            net_income=series.get("net_income") or [],
            operating_cash_flow=series.get("operating_cash_flow") or [],
            shares=series.get("shares") or [])),
    }


def forensics(f: Fundamentals) -> dict[str, float | int | None]:
    """Accrual-quality ratios handed to the thesis engine (dimension 7), never
    gates: each false-fires without context (annual-billing SaaS, financials,
    SBC-heavy tech). None = insufficient series to compute."""
    ar_growth = _growth(f.receivables) if len(f.receivables) >= 2 else None
    revenue_growth = _growth(f.revenue) if len(f.revenue) >= 2 else None
    ni_by_end = dict(f.net_income)
    ocf_by_end = dict(f.operating_cash_flow)
    ni_exceeds = 0
    for end in sorted(set(ni_by_end) & set(ocf_by_end), reverse=True):
        if ni_by_end[end] > ocf_by_end[end]:
            ni_exceeds += 1
        else:
            break
    dilution = _growth(f.shares) if len(f.shares) >= 2 else None
    return {
        "ar_growth": ar_growth,
        "revenue_growth": revenue_growth,
        "ni_exceeds_ocf_years": ni_exceeds,
        "dilution_rate": dilution,
    }


def industry_excluded(industry: str) -> bool:
    return "biotech" in industry.lower()


def _ranked_field(bars_by_ticker: dict[str, BarsSummary]):
    """The broad $5/$5M field + its RS percentiles — built ONCE per funnel
    call, identically for both cohorts (a field-eligibility change here
    reaches cohort 1 and 2 together; the admission rules differ downstream)."""
    from kairos.signals import rs

    field = {t: b for t, b in bars_by_ticker.items() if rs_field_eligible(b)}
    pct = rs.rs_percentile({t: rs.rs_raw(b.closes) for t, b in field.items()})
    return field, pct


def run_screen(
    bars_by_ticker: dict[str, BarsSummary],
    *,
    profile_fetch,
    fundamentals_fetch,
) -> ScreenResult:
    """The weekly funnel. Bars-only gates (floors, trend template, RS >= 90)
    run first and are free; provider-backed fetches (profile, fundamentals)
    happen only for bars-stage survivors, so provider volume scales with the
    survivor count, not the market. Names cut at the bars stage are not logged
    as exclusions (the whole market fails somewhere); names that reached
    fetching and were cut are logged, never silent."""
    from kairos.data.edgar import MissingFactError
    from kairos.data.estimates import MissingEstimatesError

    field, pct = _ranked_field(bars_by_ticker)

    shortlist: list[tuple[str, float]] = []
    for t, b in field.items():
        t_rs = pct.get(t)
        if t_rs is None:
            continue  # insufficient history (IPO < 12mo): out of the field
        if admission_eligible(b) and t_rs >= _RS_ADMIT and trend_template(b.closes):
            shortlist.append((t, t_rs))
    logger.debug("run_screen: %d in field, %d past bars gates",
                 len(field), len(shortlist))

    exclusions: dict[str, str] = {}
    survivors: list[Candidate] = []
    for t, t_rs in shortlist:
        try:
            facts, reason = _fetch_gates(
                t, profile_fetch=profile_fetch,
                fundamentals_fetch=fundamentals_fetch)
            if reason is not None:
                exclusions[t] = reason
                continue
            survivors.append(Candidate(ticker=t, rs=t_rs, forensics=forensics(facts)))
        except (MissingEstimatesError, MissingFactError) as e:
            # ETFs/ADRs/odd filers: one name's missing data is an exclusion
            # event, never a dead sweep
            exclusions[t] = f"data_error:{type(e).__name__}"
            logger.debug("run_screen: %s data error: %s", t, e)
    logger.debug("run_screen: %d survivors, %d excluded at fetch stage",
                 len(survivors), len(exclusions))
    return ScreenResult(survivors=survivors, exclusions=exclusions)


def _fetch_gates(t: str, *, profile_fetch, fundamentals_fetch):
    """Provider-backed gates shared by BOTH cohort funnels (one fact, one
    place: a gate change here reaches cohort 1 and 2 together). Returns
    (facts, None) on pass or (None, exclusion_reason) on cut."""
    prof = profile_fetch(t)
    if not mcap_floor_pass(prof.market_cap):
        return None, "mcap_floor"
    if industry_excluded(prof.industry):
        return None, "industry"
    facts = fundamentals_fetch(t)
    if not fundamentals_pass(facts):
        return None, "fundamentals"
    return facts, None


def run_premove_screen(
    bars_by_ticker: dict[str, BarsSummary],
    *,
    profile_fetch,
    fundamentals_fetch,
    revisions_fetch,
    net_up_floor: int = 0,
) -> ScreenResult:
    """Cohort-2 weekly funnel (premove): RS percentile [70, 90) RISING vs
    the t-21 snapshot, the cohort-1 fetch-stage gates, and a hard
    revisions-positive gate (RevisionSnapshot.positive — reused, never
    re-derived). Same percentile field construction as run_screen: one
    field, two admission rules, disjoint by the band's half-open top.

    Exclusion logging: bars-stage cuts below/above the band are unlogged
    (mirrors cohort 1 — the whole market fails somewhere); IN-BAND names
    cut by the rising rule are logged (rs_prior_unrankable / rs_not_rising)
    and every fetch-stage cut is logged — the AC3 probe's per-gate counts
    key on these. net_up_floor is the one AC3-adjustable knob, layered ON
    TOP of the frozen positive definition (default 0 = no extra floor)."""
    from kairos.data.edgar import MissingFactError
    from kairos.data.estimates import MissingEstimatesError

    field, pct = _ranked_field(bars_by_ticker)
    prior = prior_field_percentiles(bars_by_ticker)

    exclusions: dict[str, str] = {}
    shortlist: list[tuple[str, float]] = []
    for t, b in field.items():
        t_rs = pct.get(t)
        if t_rs is None:
            continue  # insufficient history: out of the field
        if not (admission_eligible(b) and premove_band(t_rs)
                and trend_template(b.closes)):
            continue
        p = prior.get(t)
        if p is None:
            exclusions[t] = "rs_prior_unrankable"
            continue
        if not premove_rising(current=t_rs, prior=p):
            exclusions[t] = "rs_not_rising"
            continue
        shortlist.append((t, t_rs))
    logger.debug("run_premove_screen: %d in field, %d in band past rising",
                 len(field), len(shortlist))

    survivors: list[Candidate] = []
    for t, t_rs in shortlist:
        try:
            facts, reason = _fetch_gates(
                t, profile_fetch=profile_fetch,
                fundamentals_fetch=fundamentals_fetch)
            if reason is not None:
                exclusions[t] = reason
                continue
            try:
                snap = revisions_fetch(t)
            except MissingEstimatesError as e:
                # the >20% stop-risk keys on this count: yfinance coverage
                # gap is a NAMED reason, never folded into data_error
                exclusions[t] = "revisions_missing"
                logger.debug("run_premove_screen: %s revisions missing: %s", t, e)
                continue
            if not snap.positive:
                exclusions[t] = "revisions_negative"
                continue
            if snap.net_up_30d < net_up_floor:
                exclusions[t] = "revisions_below_floor"
                continue
            survivors.append(Candidate(ticker=t, rs=t_rs, forensics=forensics(facts)))
        except (MissingEstimatesError, MissingFactError) as e:
            exclusions[t] = f"data_error:{type(e).__name__}"
            logger.debug("run_premove_screen: %s data error: %s", t, e)
    logger.debug("run_premove_screen: %d survivors, %d excluded",
                 len(survivors), len(exclusions))
    return ScreenResult(survivors=survivors, exclusions=exclusions)

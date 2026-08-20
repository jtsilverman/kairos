"""Rule-outs 5rev, 6, 7 and 8 of the screen of record.

Recorded with evidence in docs/ruleout-screen-2026-08.md and coded here
2026-08-18. A rule-out attacks whether an investment case can EXIST, never
how good the case is (wiki/concepts/rule-out-screen-design.md), so every
function below returns a verdict on a fact no story rescues.

Pure logic on injected series. Fetching lives in the runner, matching
kairos.screen.
"""

from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)

Series = Sequence[tuple[str, float]]  # ordered [(period_end, value)]

# Rule 6. Businesses whose results are set by a price nobody at the company
# controls: metals, oil and gas, utilities, shipping, hospital reimbursement,
# freight rates. Found independently by eight blind readers of the 382-name
# August 2026 list. An agent panel writing company-level theses produces
# nothing usable about them. SIC bands, inclusive.
DENY_SIC: tuple[tuple[int, int], ...] = (
    (1000, 1499),   # mining, oil and gas extraction
    (3300, 3399),   # steel, aluminium, nonferrous metals
    (3533, 3533),   # oil and gas field machinery
    (4400, 4499),   # water transportation
    (4731, 4731),   # freight forwarding
    (4900, 4999),   # utilities
    (8062, 8062),   # general medical and surgical hospitals
)

# Banks, insurers and REITs. They report no capex and no research line, so
# the non-financial test would cut them by accident; book value per share is
# what they compound instead.
FINANCIAL_SIC = (6000, 6799)

# Rule 5, non-financial. A modest earnings dip is ordinary business noise.
NI_COLLAPSE = -0.25

# Rule 7. Growth computed off a base this small is arithmetic, not a trend.
REVENUE_BASE_MIN = 20_000_000.0


def is_exogenous_sector(sic: int | None) -> bool:
    """Rule 6. A missing or zero SIC returns False: an unreadable code is not
    evidence of an exogenous business, and a rule-out never fires on absent
    evidence."""
    if not sic:
        return False
    return any(low <= sic <= high for low, high in DENY_SIC)


def is_financial(sic: int | None) -> bool:
    """Which of the two rule-5 tests a company answers to."""
    if not sic:
        return False
    return FINANCIAL_SIC[0] <= sic <= FINANCIAL_SIC[1]


def book_value_per_share(equity: Series, shares: Series) -> list[tuple[str, float]]:
    """Equity over share count, on the periods both series report. A period
    present in one series only is dropped rather than carried forward: a
    book value per share built from two different period ends is a wrong
    number wearing a right shape."""
    by_period = dict(shares)
    return [(end, value / by_period[end]) for end, value in equity
            if by_period.get(end)]


def financial_compounding(ni_growth: float | None,
                          bvps_growth: float | None) -> bool:
    """Rule 5, financial: earnings AND book value per share both growing.
    Either proof unreadable rules the name out, because rule 5 asks the
    company to demonstrate something and a blank is not a demonstration."""
    if ni_growth is None or bvps_growth is None:
        return False
    return ni_growth > 0 and bvps_growth > 0


def nonfinancial_collapsing(ni_growth: float | None,
                            capex_growth: float | None,
                            rd_growth: float | None) -> bool:
    """Rule 5, non-financial: earnings fell past NI_COLLAPSE AND neither
    capex nor research spend rose. The conjunction is what makes the fact
    unrescuable; "earnings fell" alone is rescued by "we are investing"
    (Jake, 2026-08-18). Unreadable earnings is not a collapse."""
    if ni_growth is None or ni_growth >= NI_COLLAPSE:
        return False
    invests = ((capex_growth is not None and capex_growth > 0)
               or (rd_growth is not None and rd_growth > 0))
    return not invests


def revenue_base_ok(revenue: Series) -> bool:
    """Rule 7. The prior-year base must clear REVENUE_BASE_MIN for this
    year's growth rate to mean anything. One year of revenue has no prior
    base, so it cannot be judged and fails."""
    if len(revenue) < 2:
        return False
    return abs(revenue[-2][1]) >= REVENUE_BASE_MIN


def first_per_filer(rows: Sequence[tuple[str, int | None]]) -> list[str]:
    """Rule 8. One ticker per filer, keeping the first occurrence, so a dual
    share class (GOOGL and GOOG) takes one panel slot rather than two. A
    ticker with no readable CIK is kept: dropping it would rule out on
    absent evidence."""
    kept: list[str] = []
    seen: set[int] = set()
    for ticker, cik in rows:
        if cik is None:
            kept.append(ticker)
            continue
        if cik in seen:
            logger.debug("first_per_filer: %s shares CIK %d", ticker, cik)
            continue
        seen.add(cik)
        kept.append(ticker)
    return kept

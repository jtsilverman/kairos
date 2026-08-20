"""The stage-2 fact sheet: the evidence a triage agent reads about one name.

Stage 2 asks a cheap agent whether a name that cleared the screen still
carries a fundamental case. A model handed only a ticker answers from what it
has READ about the company, so its score measures coverage and size rather
than quality; that failure is recorded in
wiki/concepts/rule-out-screen-design.md and killed every earlier
agent-ranking attempt.

Two design choices follow from it. The sheet states the fundamentals, so the
agent has something to reason FROM. The sheet states no market cap, no price
and no price strength, so a score that still tracks size can only be name
recognition, and the correlation check stays answerable.

Omit-never-fake: a series the filer does not report omits its line.
"""

from __future__ import annotations

import logging
from typing import Mapping, Sequence

logger = logging.getLogger(__name__)

Series = Sequence[tuple[str, float]]

# Rendered in this order. The margin pairs are computed against revenue.
_ORDER = ("revenue", "gross_profit", "operating_income", "net_income",
          "operating_cash_flow", "capex", "research", "total_assets",
          "stockholders_equity", "cash", "long_term_debt",
          "interest_expense", "shares")

_MARGIN_OF = {"gross_profit": "gross margin",
              "operating_income": "operating margin",
              "net_income": "net margin"}

_YEARS = 5


def _millions(value: float) -> str:
    return f"{value / 1e6:,.1f}M"


def _growth(series: Series) -> float | None:
    if len(series) < 2 or not series[-2][1]:
        return None
    return (series[-1][1] - series[-2][1]) / abs(series[-2][1])


def _latest(series: Series | None) -> float | None:
    return series[-1][1] if series else None


def _at(series: Series | None, period: str) -> float | None:
    """The value a series reports for exactly `period`, or None.

    A ratio built from two different period ends is a wrong number wearing a
    right shape. ARMK's long_term_debt series stops at 2019 with 0.0M, and
    pairing that with 2025 cash flow printed "net cash" for a company paying
    $364M of annual interest (found by the adjudicator, 2026-08-18)."""
    if not series:
        return None
    for end, value in reversed(series):
        if end == period:
            return value
    return None


def _leverage(usable: Mapping[str, Series], period: str) -> list[str]:
    """The two ratios that make a debt balance readable, both computed on
    `period` alone. A debt number with no denominator says nothing about
    whether the business can carry it, and the triage seat cut sound
    compounders on exactly that (MTD, CSW, CSCO, 2026-08-18)."""
    out: list[str] = []
    debt = _at(usable.get("long_term_debt"), period)
    ocf = _at(usable.get("operating_cash_flow"), period)
    if debt is not None and ocf:
        net_debt = debt - (_at(usable.get("cash"), period) or 0.0)
        out.append(f"NET DEBT / OPERATING CASH FLOW {net_debt / ocf:.1f}x")
    operating_income = _at(usable.get("operating_income"), period)
    interest = _at(usable.get("interest_expense"), period)
    if operating_income is not None and interest:
        # Filers tag interest expense either sign; only the magnitude is the
        # denominator. A negative EARNINGS sign is kept, because a loss
        # genuinely fails to cover interest.
        out.append(f"INTEREST COVERAGE {operating_income / abs(interest):.1f}x")
    return out


def _stale(usable: Mapping[str, Series], period: str) -> list[str]:
    """Series whose last row predates `period`. A dead XBRL tag is invisible
    in the rows alone, and a reader treats the last row as current."""
    late = [(name, rows[-1][0]) for name, rows in usable.items()
            if rows[-1][0] < period]
    if not late:
        return []
    return ["", "STALE SERIES (last row predates the latest revenue period)"] + [
        f"  {name} last reported {end}" for name, end in sorted(late)]


def build(ticker: str, *, sic_description: str | None,
          series: Mapping[str, Series]) -> str | None:
    """One name's fact sheet as plain text, or None when no series is usable.

    A sheet with nothing on it would be scored on the ticker alone, which is
    the exact failure this module exists to prevent, so it is refused.
    """
    usable = {name: list(rows) for name, rows in series.items() if rows}
    if not usable:
        logger.warning("%s: no usable series, fact sheet refused", ticker)
        return None

    revenue = usable.get("revenue") or []
    revenue_by_period = dict(revenue)
    latest_period = revenue[-1][0] if revenue else ""

    lines = [f"TICKER {ticker}",
             f"INDUSTRY {sic_description or 'not reported'}",
             "",
             "ANNUAL SERIES (oldest first, USD)"]
    for name in _ORDER:
        rows = usable.get(name)
        if not rows:
            continue
        recent = rows[-_YEARS:]
        rendered = "  ".join(f"{end} {_millions(value)}"
                             for end, value in recent)
        line = f"  {name}: {rendered}"
        growth = _growth(recent)
        if growth is not None:
            line += f"  | latest YoY {growth:+.1%}"
        margin_label = _MARGIN_OF.get(name)
        if margin_label:
            end, value = recent[-1]
            base = revenue_by_period.get(end)
            if base:
                when = "latest" if end == latest_period else None
                line += (f"  | latest {margin_label} {value / base:.1%}"
                         if when else
                         f"  | {margin_label} {value / base:.1%} as of {end}")
        lines.append(line)

    shown = revenue[-_YEARS:]
    if len(shown) >= 2 and shown[0][1] > 0:
        # Over the rows the sheet PRINTS. A CAGR spanning years the reader
        # cannot see is a number they cannot check.
        years = len(shown) - 1
        cagr = (shown[-1][1] / shown[0][1]) ** (1 / years) - 1
        lines += ["", f"REVENUE CAGR over {years}y {cagr:+.1%}"]

    lines += _leverage(usable, latest_period)

    shares = usable.get("shares")
    if shares and len(shares) >= 2:
        dilution = _growth(shares)
        if dilution is not None:
            lines.append(f"SHARE COUNT change latest year {dilution:+.1%}")

    lines += _stale(usable, latest_period)
    return "\n".join(lines)

"""Dossier compiler (thesis-engine unit 5a): one hashed, doc-id-addressed text
bundle per candidate — the single input every thesis agent reads.

Doc ids ([P1] price/RS context, [X1] forensics, [F*] filings, [N*] news,
[I1] insider rows, [R1] revisions) are the citation namespace: memo claims cite
them and record-memos validates that citations resolve. A source with no data
gets NO id (an empty-but-present section would invite citations to nothing —
dimension-3 degraded mode simply omits [R1]).

Pure render on injected records; fetching lives in the runner.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from kairos.thesis import memo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DossierInputs:
    ticker: str
    as_of: str
    price: float
    rs: float
    forensics: dict
    filings: Sequence[tuple[str, str, str]]  # (form, date, text)
    news: Sequence[tuple[str, str, str]]     # (date, title, body)
    insiders: Sequence[dict]
    revisions: Optional[dict]                # None = source unavailable (degraded)
    financials: Optional[dict] = None        # financial_summary() output; None omits [Q1]
    technicals: Optional[dict] = None        # stock-health context; None = bare [P1]
    earnings: Optional[dict] = None          # earnings_from_calendar() output; None omits [E1]
    transcript_digests: Optional[Sequence[dict]] = None  # None omits [T1];
    # each: {quarter, digest, transcript_sha256, prompt_sha256, model_alias}
    short_interest: Optional[dict] = None    # {rows, shares_outstanding};
    # None (fetch failed/absent) omits [S1] — omit-never-fake
    story_age: Optional[dict] = None         # {sessions, left_censored};
    # None (never attained / insufficient history) omits the [P1] line
    rs_decomposition: Optional[dict] = None  # {"63d","126d","252d"} legs;
    # None (insufficient close history) omits the [P1] line


def financial_summary(*, series: dict, quarterly_revenue, market_cap) -> dict:
    """Code-computed financial-health block for the [Q1] section. Derives
    only what its inputs support — a missing tag omits the metric, never
    fakes a value (the omit-never-fake rule: an invented number would be
    cited as evidence)."""
    derived: dict[str, float] = {}

    def latest(name: str) -> Optional[tuple]:
        s = series.get(name)
        return s[-1] if s else None

    def value(name: str, *, matching: str) -> Optional[float]:
        """Latest value of `name` only if its fiscal date matches the other
        operand's — a cross-series ratio whose operands come from different
        fiscal years is an artifact, not a metric (ATEX: gross_profit series
        ends FY2019, revenue FY2026 -> gross_margin -0.1157 printed).
        Omit-never-fake extends to vintage."""
        row = latest(name)
        return row[1] if row is not None and row[0] == matching else None

    ocf_row = latest("operating_cash_flow")
    if ocf_row is not None:
        capex = value("capex", matching=ocf_row[0])
        if capex is not None:
            derived["free_cash_flow"] = ocf_row[1] - capex
    rev_row = latest("revenue")
    if rev_row is not None and rev_row[1]:
        rev_date, revenue = rev_row
        for metric, name in (("gross_margin", "gross_profit"),
                             ("operating_margin", "operating_income"),
                             ("net_margin", "net_income")):
            v = value(name, matching=rev_date)
            if v is not None:
                derived[metric] = v / revenue
        if market_cap is not None:
            derived["ps_ratio"] = market_cap / revenue
    eq_row = latest("stockholders_equity")
    if eq_row is not None and eq_row[1]:
        debt = value("long_term_debt", matching=eq_row[0])
        if debt is not None:
            derived["debt_to_equity"] = debt / eq_row[1]
    return {"series": series, "quarterly_revenue": quarterly_revenue,
            "derived": derived, "market_cap": market_cap}


# Uniform filing-lag proxy: an annual vintage becomes usable 90 days after
# its fiscal end (upper-bounds the true 10-K lag — PIT-safe, coarser).
_FILING_LAG_DAYS = 90
# 1yr of daily P/S points; a thinner distribution renders no percentile.
_PS_MIN_POINTS = 252


def ps_history_percentile(*, closes, shares_series, revenue_series, as_of):
    """Today's P/S as a percentile of the ticker's own trailing daily P/S
    distribution. P/S_t = close_t * shares_known(t) / revenue_known(t),
    where known(t) = latest annual vintage with fiscal_end + 90d <= t —
    the value(matching=) vintage discipline extended across time (a
    cross-vintage ratio is an artifact, not a metric). A bar past as_of
    raises (the runner bounds fetches at as_of; a future bar here is a
    leak, fail loud). Fewer than 252 computable points -> None, omitted
    never faked. Percentile mirrors the rs.rs_percentile convention:
    100 * bisect_left(sorted points, today) / (n - 1), ties share the
    lower rank; today's point is part of its own distribution.

    closes: ordered [(iso_date, close)]; series: ordered
    [(fiscal_end, value)] (edgar.annual_series shape, full series not the
    [-5:] display slice). Returns {percentile, window_sessions, today_ps};
    today_ps stays unrendered (a second printed P/S beside derived
    ps_ratio would be a dual-signed datum).
    """
    import datetime as _dt
    from bisect import bisect_left

    def _known(series, d):
        v = None
        for fiscal_end, value in series:
            usable = (_dt.date.fromisoformat(fiscal_end)
                      + _dt.timedelta(days=_FILING_LAG_DAYS)).isoformat()
            if usable <= d:
                v = value
            else:
                break
        return v

    points = []
    for d, close in closes:
        if d > as_of:
            raise ValueError(f"bar {d} past as_of {as_of} — PIT leak")
        shares = _known(shares_series, d)
        revenue = _known(revenue_series, d)
        if shares is None or revenue is None or revenue <= 0:
            continue
        points.append(close * shares / revenue)
    if len(points) < _PS_MIN_POINTS:
        return None
    today = points[-1]
    ordered = sorted(points)
    return {
        "percentile": 100.0 * bisect_left(ordered, today) / (len(points) - 1),
        "window_sessions": len(points),
        "today_ps": today,
    }


def _insider_line(r: dict) -> str:
    price = r["price"] if r["price"] is not None else "n/a"
    return f"{r['date']} {r['insider']} ({r['role']}): {r['shares']:g} sh @ {price}"


def insider_section(rows: Sequence[dict]) -> str:
    """[I1] from Form 4 rows, four buckets. Non-plan open-market buys are the
    signal and render prominent (with a multi-insider 60-day cluster note);
    non-plan discretionary sales get their own visible group (the dimension-3
    0-anchor — burying heavy discretionary selling would overstate the case);
    10b5-1 plan rows (any code) collapse to a count (scheduled, no signal);
    remaining codes (F/M/A/G — tax, exercises, awards) collapse to per-code
    counts. Empty buckets are omitted, never rendered as zero."""
    import datetime as _dt

    buys = [r for r in rows if r["code"] == "P" and not r["is_10b5_1"]]
    sales = [r for r in rows if r["code"] == "S" and not r["is_10b5_1"]]
    plan = [r for r in rows if r["is_10b5_1"]]
    other = [r for r in rows if not r["is_10b5_1"] and r["code"] not in ("P", "S")]

    lines = ["[I1] INSIDER TRANSACTIONS (SEC Form 4; 10b5-1 plan trades "
             "separated — only non-plan trades are discretionary):"]
    if buys:
        lines.append("OPEN-MARKET BUYS (code P, non-plan):")
        lines.extend(_insider_line(r) for r in buys)
        by_insider = {}
        for r in buys:
            by_insider.setdefault(r["insider"], []).append(
                _dt.date.fromisoformat(r["date"]))
        clustered = {
            a for a in by_insider for b in by_insider if a != b
            and min(abs((da - db).days) for da in by_insider[a]
                    for db in by_insider[b]) <= 60
        }
        if clustered:
            lines.append(f"CLUSTER: {len(clustered)} distinct insiders "
                         "bought within 60 days")
    if sales:
        lines.append("DISCRETIONARY SALES (code S, non-plan):")
        lines.extend(_insider_line(r) for r in sales)
    if plan:
        lines.append(f"10b5-1 plan transactions: {len(plan)} "
                     "(scheduled; no signal)")
    if other:
        counts: dict[str, int] = {}
        for r in other:
            counts[r["code"]] = counts.get(r["code"], 0) + 1
        lines.append("other codes: " + ", ".join(
            f"{c}={n}" for c, n in sorted(counts.items())))
    return "\n".join(lines)


@dataclass(frozen=True)
class Dossier:
    ticker: str
    as_of: str
    text: str
    doc_ids: tuple[str, ...]
    sha256: str


def build(inputs: DossierInputs) -> Dossier:
    sections: list[tuple[str, str]] = []  # (doc_id, rendered block)

    p1 = (f"[P1] CONTEXT — {inputs.ticker} as of {inputs.as_of}: "
          f"price {inputs.price}, RS percentile {inputs.rs}")
    if inputs.technicals:
        p1 += "\nStock health: " + json.dumps(inputs.technicals, sort_keys=True)
    if inputs.rs_decomposition is not None:
        legs = inputs.rs_decomposition
        p1 += ("\nRS decomposition: price change "
               + ", ".join(f"{k} {legs[k]:+.1%}" for k in ("63d", "126d", "252d"))
               + " (the RS score's price legs; estimate-revision side in "
               "[R1]; an LLM input, not a gate)")
    if inputs.story_age is not None:
        sa = inputs.story_age
        age = (f">={sa['sessions']}" if sa["left_censored"]
               else f"{sa['sessions']}")
        p1 += (f"\nStory age: first RS>=90 attainment {age} sessions ago "
               f"({sa['window_sessions']}-session window, from first "
               "rankability; an LLM input, not a gate)")
    sections.append(("P1", p1))
    flagged = memo.flagged_ratios(inputs.forensics)
    sections.append((
        "X1",
        "[X1] FORENSIC RATIOS (screen-computed; each flagged one MUST be "
        "addressed in the memo): " + json.dumps(inputs.forensics, sort_keys=True)
        + f"\nthresholds: ar_growth > {memo.AR_VS_REVENUE}x revenue_growth;"
        f" dilution_rate > {memo.DILUTION_PER_YEAR:.0%}/yr;"
        f" ni > ocf {memo.NI_OCF_YEARS}+ consecutive years"
        + "\nflagged: " + (", ".join(flagged) if flagged else "none"),
    ))
    if inputs.short_interest is not None:
        si = inputs.short_interest
        rows = si["rows"]
        latest = rows[-1]
        lines = ["[S1] SHORT INTEREST (FINRA consolidated short interest; "
                 "bi-weekly settlements; an LLM input, not a gate):",
                 f"latest: {latest['short_shares']} shares short (settlement "
                 f"{latest['settlement_date']}), days-to-cover "
                 f"{latest['days_to_cover']}",
                 "trend: " + ", ".join(
                     f"{r['settlement_date']}: {r['short_shares']} "
                     f"({r['change_pct']:+g}%)" for r in rows)]
        if si.get("shares_outstanding"):
            pct = latest["short_shares"] / si["shares_outstanding"]
            lines.append("short as % of shares outstanding (derived from "
                         "EDGAR shares series; true float unavailable): "
                         f"{pct:.2%}")
        sections.append(("S1", "\n".join(lines)))
    if inputs.financials is not None:
        f = inputs.financials
        lines = ["[Q1] FINANCIAL HISTORY (SEC EDGAR annual series; latest "
                 "values; derived metrics code-computed):"]
        for name, s in f["series"].items():
            lines.append(f"{name}: " + ", ".join(f"{d}: {v}" for d, v in s))
        if f.get("quarterly_revenue"):
            lines.append("quarterly_revenue: " + ", ".join(
                f"{d}: {v}" for d, v in f["quarterly_revenue"]))
        if f.get("market_cap") is not None:
            lines.append(f"market_cap: {f['market_cap']}")
        if f["derived"]:
            lines.append("derived: " + json.dumps(
                {k: round(v, 4) for k, v in f["derived"].items()}, sort_keys=True))
        if f.get("ps_history"):
            ph = f["ps_history"]
            lines.append(
                f"P/S vs own history: percentile {ph['percentile']:.1f} over "
                f"the trailing {ph['window_sessions']}-session daily P/S "
                "series (annual revenue/shares vintage-matched, 90d filing "
                "lag; an LLM input, not a gate)")
        sections.append(("Q1", "\n".join(lines)))
    if inputs.earnings is not None and "data_gap" in inputs.earnings:
        # rewind compile: no point-in-time estimates vintage exists anywhere;
        # the absence is PRINTED and citable, never a silent omission (A1)
        sections.append(
            ("E1", "[E1] EARNINGS CALENDAR: DATA GAP — "
             + inputs.earnings["data_gap"]))
    elif inputs.earnings is not None:
        e = inputs.earnings
        lines = ["[E1] EARNINGS CALENDAR (yfinance; consensus = current analyst "
                 "estimates):",
                 f"next_earnings_date: {e['next_earnings_date']}"]
        for key in ("eps_consensus", "revenue_consensus"):
            if key in e:
                lines.append(f"{key}: " + json.dumps(e[key], sort_keys=True))
        if "dispersion" in e:
            disp = e["dispersion"]
            lines.append(
                f"dispersion (current FY EPS, {disp['analysts']} analysts): "
                f"low {disp['low']} / avg {disp['avg']} / high {disp['high']} "
                f"— spread {disp['spread']:.1%} of avg (an LLM input, "
                "not a gate)")
        sections.append(("E1", "\n".join(lines)))
    for i, (form, date, text) in enumerate(inputs.filings, start=1):
        sections.append((f"F{i}", f"[F{i}] FILING {form} {date}:\n{text}"))
    for i, (date, title, body) in enumerate(inputs.news, start=1):
        sections.append((f"N{i}", f"[N{i}] NEWS {date} — {title}:\n{body}"))
    if inputs.insiders:
        sections.append(("I1", insider_section(inputs.insiders)))
    if inputs.revisions is not None and "data_gap" in inputs.revisions:
        sections.append(
            ("R1", "[R1] ANALYST ESTIMATE REVISIONS: DATA GAP — "
             + inputs.revisions["data_gap"]))
    elif inputs.revisions is not None:
        sections.append((
            "R1",
            "[R1] ANALYST ESTIMATE REVISIONS: "
            + json.dumps(inputs.revisions, sort_keys=True),
        ))
    if inputs.transcript_digests:
        lines = ["[T1] EARNINGS CALL DIGESTS (model-derived summaries of the "
                 "stored call transcripts; provenance hashes journaled per "
                 "quarter — treat as secondary to primary filings):"]
        for td in inputs.transcript_digests:
            lines.append(
                f"--- {td['quarter']} (transcript sha256 "
                f"{td['transcript_sha256']}; digest prompt sha256 "
                f"{td['prompt_sha256']}; model {td['model_alias']}):\n"
                f"{td['digest']}")
        sections.append(("T1", "\n".join(lines)))

    text = f"# DOSSIER {inputs.ticker} {inputs.as_of}\n\n" + "\n\n".join(
        block for _, block in sections
    )
    digest = hashlib.sha256(text.encode()).hexdigest()
    logger.debug("dossier %s %s: %d sections, sha256 %s",
                 inputs.ticker, inputs.as_of, len(sections), digest[:12])
    return Dossier(
        ticker=inputs.ticker,
        as_of=inputs.as_of,
        text=text,
        doc_ids=tuple(doc_id for doc_id, _ in sections),
        sha256=digest,
    )

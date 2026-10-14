#!/usr/bin/env python3
"""Compile thesis dossiers for screen survivors (thesis-engine unit 5).

Reads the weekly screen's --json output, fetches each name's public record
through the unit-4 wrappers, renders one hashed dossier file per name, and
writes a manifest the workflow + record step consume. Fail-loud per name;
one name's data error skips that name WITH a logged reason, never the sweep.

Usage:
    .venv/bin/python scripts/thesis_dossiers.py --screen data/screen/2026-07-07.json \
        [--tickers MU,DELL,GEV] [--out-dir data/dossiers] [--verbose]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code" / "src"))

from kairos.data import edgar, estimates, finra, transcripts
from kairos.data.polygon import fetch_grouped_daily, fetch_ticker_news, news_context
from kairos.signals import rs, story_age
from kairos.thesis import dossier

logger = logging.getLogger("thesis_dossiers")

# Bars history (dossier-data U4): ONE grouped-daily pass per as_of feeds all
# three new lines — story-age field history, [Q1] P/S closes, RS legs.
# 756 P/S points (3yr) + 253-session rank warmup; pad covers weekday holidays.
_PS_WINDOW = 756
_STORY_WINDOW = 504      # evaluation sessions the [P1] story-age line judges
_RANK_WARMUP = 253
_BARS_SESSIONS = _PS_WINDOW + _RANK_WARMUP
_SESSION_PAD = 60
# systemic-gap guard: fewer real sessions than warmup + story window means
# the feed/cache is broken, not a data gap — fail loud, never all-None
_MIN_SESSIONS = _RANK_WARMUP + _STORY_WINDOW

_FILING_FORMS = ("10-K", "10-Q", "8-K")
_FILING_LIMIT = 6
_FILING_EXCERPT_CHARS = {"10-K": 15000, "10-Q": 8000, "8-K": 4000}
_NEWS_LIMIT = 10        # relevant articles kept per dossier
_NEWS_FETCH_LIMIT = 30  # fetched before the relevance filter (mention-matching
                        # pollutes list_ticker_news: 9/10 MU items off-topic)


_HEALTH_SERIES = {
    "revenue": edgar.REVENUE_TAGS,
    "net_income": edgar.NET_INCOME_TAGS,
    "operating_cash_flow": edgar.OPERATING_CASH_FLOW_TAGS,
    "shares": edgar.SHARES_TAGS,
    "gross_profit": edgar.GROSS_PROFIT_TAGS,
    "operating_income": edgar.OPERATING_INCOME_TAGS,
    "capex": edgar.CAPEX_TAGS,
    "total_assets": edgar.TOTAL_ASSETS_TAGS,
    "stockholders_equity": edgar.EQUITY_TAGS,
    "cash": edgar.CASH_TAGS,
    "long_term_debt": edgar.LT_DEBT_TAGS,
}


def bars_history(as_of: str, targets: set[str]) -> tuple[dict, dict]:
    """One grouped-daily pass ending at as_of: the story-age percentile
    history (full-field pipeline) plus each target's (date, close) series —
    one data source for all three dossier-data lines, PIT by construction
    (every fetched date <= as_of)."""
    import datetime as dt

    d = dt.date.fromisoformat(as_of)
    candidates: list[str] = []
    while len(candidates) < _BARS_SESSIONS + _SESSION_PAD:
        if d.weekday() < 5:
            candidates.append(d.isoformat())
        d -= dt.timedelta(days=1)
    candidates.reverse()

    closes_by_target: dict[str, list[tuple[str, float]]] = {t: [] for t in targets}
    session_count = 0

    def _sessions():
        nonlocal session_count
        for day in candidates:
            bars = fetch_grouped_daily(day)
            if not bars:
                continue  # holiday
            session_count += 1
            if session_count % 100 == 0:
                logger.info("bars_history: %d sessions through %s",
                            session_count, day)
            m = {b.ticker: (b.close, b.volume) for b in bars}
            for t in targets:
                if t in m:
                    closes_by_target[t].append((day, m[t][0]))
            yield (day, m)

    hist = story_age.percentile_history(_sessions(), targets=targets)
    if session_count < _MIN_SESSIONS:
        raise SystemExit(
            f"bars_history: only {session_count} sessions fetched "
            f"(< {_MIN_SESSIONS}) — grouped-daily feed/cache gap, aborting")
    return hist, closes_by_target


def build_financials(ticker: str, *, closes: list | None = None,
                     as_of: str | None = None) -> dict:
    """[Q1] inputs: annual series (last 5), quarterly revenue (last 8),
    market cap, and — when a close series is supplied — the P/S
    vs-own-history percentile (full unsliced vintage series). Missing tags
    omit lines (omit-never-fake). Every companyfacts read is bounded
    filed<=as_of (as-filed vintage, A2); market cap = last close x latest
    vintage shares (the stale-sharecount-market-cap audit fix — the live
    provider profile is gone from this path, live compile included)."""
    facts = edgar.fetch_companyfacts(ticker)
    series: dict[str, list] = {}
    full: dict[str, list] = {}
    for name, tags in _HEALTH_SERIES.items():
        try:
            full[name] = edgar.annual_series(facts, tags, filed_lte=as_of)
            series[name] = full[name][-5:]
        except edgar.MissingFactError:
            logger.debug("%s: no %s tags — line omitted", ticker, name)
    try:
        q_rev = edgar.quarterly_series(facts, edgar.REVENUE_TAGS,
                                       filed_lte=as_of)[-8:]
    except edgar.MissingFactError:
        q_rev = None
    shares_s = full.get("shares")
    mcap = (closes[-1][1] * shares_s[-1][1]
            if closes and shares_s else None)
    if mcap is None:
        logger.warning("%s: market cap omitted (no %s)", ticker,
                       "close series" if not closes else "shares series")
    out = dossier.financial_summary(series=series, quarterly_revenue=q_rev,
                                    market_cap=mcap)
    if not closes or not as_of:
        logger.warning("%s: P/S history line omitted (no close series "
                       "supplied)", ticker)
    else:
        shares_s, revenue_s = full.get("shares"), full.get("revenue")
        if shares_s and revenue_s:
            ph = dossier.ps_history_percentile(
                closes=closes[-_PS_WINDOW:], shares_series=shares_s,
                revenue_series=revenue_s, as_of=as_of)
            if ph is None:
                logger.warning(
                    "%s: P/S history line omitted (<252 computable points "
                    "from %d bars)", ticker, len(closes))
            else:
                out["ps_history"] = ph
        else:
            logger.warning("%s: P/S history line omitted (missing %s series)",
                           ticker,
                           "shares" if not shares_s else "revenue")
    return out


def compile_inputs(ticker: str, survivor: dict, as_of: str, *,
                   pct_history: list | None = None,
                   closes: list | None = None,
                   rewind: bool = False) -> dossier.DossierInputs:
    """Every dated source is bounded <= as_of (A1). `rewind=True` replaces
    the live-only [E1]/[R1] yfinance blocks with citable data-gap lines and
    calls NOTHING in kairos.data.estimates — test_rewind_compile.py's
    raise-on-call fakes enforce that invariant against future edits."""
    subs = edgar.fetch_submissions(ticker)
    filings = []
    for f in edgar.recent_filings(subs, forms=_FILING_FORMS,
                                  limit=_FILING_LIMIT, filed_lte=as_of):
        cap = _FILING_EXCERPT_CHARS.get(f.form, 4000)
        if f.form in ("10-K", "10-Q"):
            excerpt = edgar.mdna_excerpt(edgar.fetch_filing_text(f.url),
                                         cap=cap, form=f.form)
        else:  # 8-K: the content is the EX-99 exhibit, the primary doc is a wrapper
            doc = edgar.ex99_document(edgar.fetch_filing_index(f))
            if doc:
                logger.info("%s 8-K %s exhibit=EX-99 doc=%s", ticker, f.filed, doc)
                excerpt = edgar.fetch_filing_text(edgar.document_url(f, doc))[:cap]
            else:
                logger.info("%s 8-K %s exhibit=none, primary doc kept",
                            ticker, f.filed)
                excerpt = edgar.fetch_filing_text(f.url)[:cap]
        filings.append((f.form, f.filed, excerpt))

    news = []
    for n in fetch_ticker_news(ticker, limit=_NEWS_FETCH_LIMIT,
                               published_lte=as_of):
        entry = news_context(n, ticker)
        if entry is None:
            logger.debug("%s: news dropped (not about ticker): %s", ticker, n.title)
            continue
        news.append(entry)
        if len(news) == _NEWS_LIMIT:
            break

    try:
        insiders = edgar.fetch_form4_rows(ticker, filed_lte=as_of)
        if not insiders:
            logger.warning("%s: no Form 4 filings — [I1] omitted", ticker)
    except Exception as e:
        logger.warning("%s: Form 4 fetch failed (%s) — [I1] omitted", ticker, e)
        insiders = []

    if rewind:
        earnings = {"data_gap":
                    "no point-in-time estimates vintage exists (rewind)"}
        revisions = {"data_gap":
                     "no point-in-time revisions vintage exists (rewind)"}
    else:
        try:
            earnings = estimates.next_earnings(ticker, as_of=as_of)
        except estimates.MissingEstimatesError as e:
            logger.warning("%s: earnings calendar unavailable (%s) — [E1] "
                           "omitted", ticker, e)
            earnings = None
        if earnings is not None:
            try:
                earnings["dispersion"] = estimates.earnings_dispersion(ticker)
            except estimates.MissingEstimatesError as e:
                logger.warning("%s: dispersion unavailable (%s) — line omitted",
                               ticker, e)
        try:
            snap = estimates.revision_snapshot(ticker)
            revisions = {"net_up_30d": snap.net_up_30d,
                         "trend_delta_90d": snap.trend_delta_90d,
                         "positive": snap.positive}
        except estimates.MissingEstimatesError as e:
            logger.warning("%s: revisions unavailable (%s) — degraded dossier",
                           ticker, e)
            revisions = None

    digests = transcripts.load_digests(ticker, as_of=as_of)
    if not digests:
        logger.info("%s: no transcript digests stored — [T1] omitted", ticker)

    financials = build_financials(ticker, closes=closes, as_of=as_of)

    sa = story_age.scan(pct_history[-_STORY_WINDOW:]) if pct_history else None
    if sa is None:
        logger.warning("%s: story-age line omitted (%s)", ticker,
                       "no bars history supplied" if not pct_history
                       else "no RS>=90 attainment / never rankable in window")

    legs = rs.price_legs([c for _, c in closes]) if closes else None
    if legs is None:
        logger.warning("%s: RS-decomposition line omitted (%d closes < 253)",
                       ticker, len(closes) if closes else 0)
    try:
        si_rows = finra.fetch_short_interest(
            ticker, as_of=_dt.date.fromisoformat(as_of))
        shares = financials["series"].get("shares")
        short_interest = ({"rows": si_rows,
                           "shares_outstanding": shares[-1][1] if shares else None}
                          if si_rows else None)
        if short_interest is None:
            logger.warning("%s: FINRA returned no settlements — [S1] omitted",
                           ticker)
    except Exception as e:
        logger.warning("%s: short interest unavailable (%s) — [S1] omitted",
                       ticker, e)
        short_interest = None

    return dossier.DossierInputs(
        ticker=ticker,
        as_of=as_of,
        price=survivor["price"],
        rs=survivor["rs"],
        forensics=survivor["forensics"],
        filings=filings,
        news=news,
        insiders=insiders,
        revisions=revisions,
        financials=financials,
        technicals=survivor.get("technicals"),
        earnings=earnings,
        transcript_digests=digests or None,
        short_interest=short_interest,
        story_age=sa,
        rs_decomposition=legs,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", required=True, help="weekly_screen --json output")
    ap.add_argument("--tickers", default=None,
                    help="comma-separated subset (default: all survivors)")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--rewind", action="store_true",
                    help="PIT rewind compile: [E1]/[R1] become data-gap "
                         "lines, no live-only reads; dossiers land under "
                         "rewind-<as_of>/")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        stream=sys.stderr, format="%(name)s %(levelname)s %(message)s")

    screen = json.loads(Path(args.screen).read_text())
    as_of = screen["as_of"]
    survivors = {s["ticker"]: s for s in screen["survivors"]}
    wanted = (args.tickers.split(",") if args.tickers else list(survivors))
    missing = [t for t in wanted if t not in survivors]
    if missing:
        raise SystemExit(f"not in survivor list: {missing}")

    dirname = f"rewind-{as_of}" if args.rewind else as_of
    out_dir = Path(args.out_dir or
                   Path(__file__).resolve().parent.parent / "data" / "dossiers") / dirname
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("bars history: one grouped-daily pass for %d targets", len(wanted))
    pct_hist, closes_by_target = bars_history(as_of, set(wanted))

    manifest: list[dict] = []
    failed: list[str] = []
    for t in wanted:
        try:
            d = dossier.build(compile_inputs(
                t, survivors[t], as_of,
                pct_history=pct_hist.get(t),
                closes=closes_by_target.get(t),
                rewind=args.rewind))
        except Exception as e:
            logger.error("%s: dossier failed: %s", t, e)
            failed.append(t)
            continue
        path = out_dir / f"{t}.md"
        path.write_text(d.text)
        manifest.append({"ticker": t, "as_of": as_of, "dossierPath": str(path),
                         "sha256": d.sha256, "doc_ids": list(d.doc_ids),
                         "forensics": survivors[t]["forensics"],
                         # premove-cohort thread: screen JSON -> manifest ->
                         # memo.from_workflow (absent key reads rs90 there)
                         "cohort": screen.get("cohort", "rs90")})
        print(f"{t}: {len(d.doc_ids)} docs, {len(d.text)} chars, sha {d.sha256[:12]}")

    # MERGE, never overwrite. A --tickers run compiles a subset, and an
    # overwriting write drops every name the run did not touch: a 163-dossier
    # directory once fell to a 3-entry manifest on a 10-name retry, and
    # panel_prepare reads doc ids from the manifest, so the other 160 names
    # silently vanish from the funnel rather than failing loud.
    manifest_path = out_dir / "manifest.json"
    merged: dict[str, dict] = {}
    if manifest_path.exists():
        merged = {r["ticker"]: r for r in json.loads(manifest_path.read_text())}
    merged.update({r["ticker"]: r for r in manifest})
    rows = [merged[t] for t in sorted(merged)]
    manifest_path.write_text(json.dumps(rows, indent=1))
    print(f"\nmanifest: {manifest_path} ({len(manifest)} written, {len(rows)} total)")
    if failed:
        print(f"FAILED (rerun these, do not skip silently): {failed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

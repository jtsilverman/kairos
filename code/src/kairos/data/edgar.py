"""SEC EDGAR companyfacts wrapper (thesis-engine unit 2): annual XBRL fact
series for the screen's red-flag rules (revenue, net income, operating cash
flow, receivables, shares).

Live probe 2026-07-08 (ZETA CIK 1851003): revenue lives under the ASC-606 tag,
not ``Revenues`` -- extraction takes an ordered tag-fallback tuple and fails
loud when nothing matches, because a silently-missing fact would pass the
red-flag gates open (the NaN>x fail-open trap, applied to fundamentals).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import sqlite3
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

def _ua() -> dict[str, str]:
    """SEC EDGAR rejects an anonymous User-Agent and asks for a contact address.

    Read lazily: config imports kairos.data.polygon, so a module-level import here
    would close a cycle through this package's __init__.
    """
    from kairos import config  # noqa: PLC0415
    return {"User-Agent": config.CONTACT}
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

REVENUE_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
)
# Order breaks recency ties (first listed wins): attributable-to-common
# before ProfitLoss (which includes noncontrolling interests). CAT stopped
# tagging NetIncomeLoss after FY2010 (live probe 2026-07-11) — the
# single-tag tuple fed 2010 NI into the dossier's [Q1] net_margin.
NET_INCOME_TAGS = (
    "NetIncomeLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "ProfitLoss",
)
OPERATING_CASH_FLOW_TAGS = ("NetCashProvidedByUsedInOperatingActivities",)
RECEIVABLES_TAGS = ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent")
SHARES_TAGS = (
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "CommonStockSharesOutstanding",
)


class MissingFactError(Exception):
    """No fallback tag matched in the filer's us-gaap facts."""


def annual_series(facts: dict, tags: tuple[str, ...], *,
                  filed_lte: str | None = None) -> list[tuple[str, float]]:
    """Ordered [(period_end, value)] of annual (10-K FY) rows, taken from the
    matching tag whose LATEST annual row is most recent. Filers migrate tags
    across their history (MGNI: "Revenues" pre-2020, ASC-606 after) -- a
    first-listed-tag rule silently returns years-stale facts. `filed_lte`
    (ISO date) serves the AS-FILED vintage for a rewind: rows filed after
    the bound vanish, and among duplicate period-ends the latest-filed row
    within the bound wins (a restatement filed later is invisible until its
    filing date). Without the bound, duplicate period-ends keep the
    latest-filed (last-listed when no filed date) row."""
    gaap = facts["facts"].get("us-gaap", {})
    best: list[tuple[str, float]] = []
    best_tag = None
    for tag in tags:
        if tag not in gaap:
            continue
        rows = next(iter(gaap[tag]["units"].values()))
        by_end: dict[str, tuple[str, float]] = {}
        for row in rows:
            if row.get("form") != "10-K" or row.get("fp") != "FY":
                continue
            if filed_lte is not None and row.get("filed", "") > filed_lte:
                continue
            # 10-K filings also carry quarter-period facts under form=10-K
            # fp=FY (live: DELL, +374% quarter-vs-year revenue growth). A
            # duration concept must span ~a year; instant concepts (shares
            # outstanding) have no "start" and pass through.
            start = row.get("start")
            if start is not None:
                days = (_dt.date.fromisoformat(row["end"])
                        - _dt.date.fromisoformat(start)).days
                if days < 300:
                    continue
            filed = row.get("filed", "")
            if row["end"] not in by_end or filed >= by_end[row["end"]][0]:
                by_end[row["end"]] = (filed, float(row["val"]))
        series = sorted((end, val) for end, (_, val) in by_end.items())
        if series and (not best or series[-1][0] > best[-1][0]):
            best, best_tag = series, tag
    if not best:
        raise MissingFactError(f"none of {tags} present in companyfacts")
    logger.debug("annual_series: selected tag %s (latest %s)", best_tag, best[-1][0])
    return best


def quarterly_series(facts: dict, tags: tuple[str, ...], *,
                     filed_lte: str | None = None) -> list[tuple[str, float]]:
    """Ordered [(period_end, value)] of QUARTER-duration 10-Q rows, same
    recency-based tag selection and `filed_lte` as-filed-vintage rule as
    annual_series. YTD rows inside 10-Qs (6/9-month durations) are excluded
    — only ~one-quarter periods qualify, so the series shows sequential
    trajectory (the acceleration signal)."""
    gaap = facts["facts"].get("us-gaap", {})
    best: list[tuple[str, float]] = []
    for tag in tags:
        if tag not in gaap:
            continue
        rows = next(iter(gaap[tag]["units"].values()))
        by_end: dict[str, tuple[str, float]] = {}
        for row in rows:
            if row.get("form") != "10-Q":
                continue
            if filed_lte is not None and row.get("filed", "") > filed_lte:
                continue
            start = row.get("start")
            if start is None:
                continue
            days = (_dt.date.fromisoformat(row["end"])
                    - _dt.date.fromisoformat(start)).days
            if not 60 <= days <= 120:
                continue
            filed = row.get("filed", "")
            if row["end"] not in by_end or filed >= by_end[row["end"]][0]:
                by_end[row["end"]] = (filed, float(row["val"]))
        series = sorted((end, val) for end, (_, val) in by_end.items())
        if series and (not best or series[-1][0] > best[-1][0]):
            best = series
    if not best:
        raise MissingFactError(f"none of {tags} present as 10-Q quarter rows")
    return best


# Financial-history tags (dossier [Q1] section). Optional per filer: a missing
# tag omits its line, never fakes a value.
GROSS_PROFIT_TAGS = ("GrossProfit",)
OPERATING_INCOME_TAGS = ("OperatingIncomeLoss",)
CAPEX_TAGS = ("PaymentsToAcquirePropertyPlantAndEquipment",)
RESEARCH_TAGS = ("ResearchAndDevelopmentExpense",
                 "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost")
INTEREST_EXPENSE_TAGS = ("InterestExpense", "InterestExpenseNonoperating",
                         "InterestIncomeExpenseNet")
TOTAL_ASSETS_TAGS = ("Assets",)
EQUITY_TAGS = ("StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
CASH_TAGS = ("CashAndCashEquivalentsAtCarryingValue",)
LT_DEBT_TAGS = ("LongTermDebtNoncurrent", "LongTermDebt")


# Module-relative, never working-directory-relative. A literal relative path
# writes a SECOND, stale cache: two such Polygon strays (223 MB and 7.7 MB)
# were deleted 2026-08-17 after a session quoted coverage off the wrong file.
DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[3] / "data" / "edgar-cache.sqlite"

_conn: sqlite3.Connection | None = None
_conn_path: Path | None = None
_stats = {"hits": 0, "misses": 0}


def _ensure_cache() -> sqlite3.Connection:
    """One connection per cache file, reopened when DEFAULT_CACHE_PATH moves."""
    global _conn, _conn_path
    if _conn is not None and _conn_path == DEFAULT_CACHE_PATH:
        return _conn
    if _conn is not None:
        _conn.close()
    DEFAULT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(DEFAULT_CACHE_PATH))
    _conn.execute(
        """
        CREATE TABLE IF NOT EXISTS edgar_cache (
            url        TEXT PRIMARY KEY,
            body       BLOB NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )
    _conn.commit()
    _conn_path = DEFAULT_CACHE_PATH
    return _conn


def close_cache() -> None:
    """Drop the connection. The next fetch reopens against the same file."""
    global _conn, _conn_path
    if _conn is not None:
        _conn.close()
    _conn, _conn_path = None, None


def cache_stats() -> dict[str, int]:
    """Hits and misses since the last reset. CHECK 1 asserts zero misses on a
    warm cascade re-run; without a counter an all-cached run is
    indistinguishable from one that silently refetched."""
    return dict(_stats)


def reset_cache_stats() -> None:
    _stats["hits"] = 0
    _stats["misses"] = 0


def _network_get(url: str) -> bytes:
    """The only place this module touches the network. Injectable in tests."""
    req = urllib.request.Request(url, headers=_ua())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _get_bytes(url: str) -> bytes:
    """Every EDGAR fetch routes through here: companyfacts, submissions, the
    filing index, Form 4 XML and filing text. EDGAR was uncached across
    processes, so a cascade re-run repaid tens of thousands of requests."""
    conn = _ensure_cache()
    row = conn.execute("SELECT body FROM edgar_cache WHERE url = ?", (url,)).fetchone()
    if row is not None:
        _stats["hits"] += 1
        return row[0]
    _stats["misses"] += 1
    body = _network_get(url)
    conn.execute(
        "INSERT OR REPLACE INTO edgar_cache (url, body, fetched_at) VALUES (?, ?, ?)",
        (url, body, _dt.datetime.now(_dt.timezone.utc).isoformat()),
    )
    conn.commit()
    return body


def _get_json(url: str) -> dict:
    return json.loads(_get_bytes(url).decode("utf-8"))


_cik_cache: dict[str, int] | None = None


def cik_for(ticker: str) -> int:
    """Ticker -> CIK via SEC's company_tickers.json (cached in-process)."""
    global _cik_cache
    if _cik_cache is None:
        raw = _get_json(_TICKERS_URL)
        _cik_cache = {row["ticker"].upper(): int(row["cik_str"]) for row in raw.values()}
        logger.debug("cik_for: loaded %d ticker mappings", len(_cik_cache))
    try:
        return _cik_cache[ticker.upper()]
    except KeyError:
        raise MissingFactError(f"no CIK for ticker {ticker!r}") from None


def fetch_companyfacts(ticker: str) -> dict:
    """Full companyfacts JSON for a ticker (annual_series consumes it)."""
    return _get_json(_FACTS_URL.format(cik=cik_for(ticker)))


_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"


@dataclass(frozen=True)
class Filing:
    form: str
    filed: str      # ISO date
    url: str        # primary document in the EDGAR archive
    cik: int        # accession directory coordinates (exhibit fetches)
    accession: str  # no-dash form


def recent_filings(submissions: dict, *, forms: tuple[str, ...], limit: int,
                   filed_lte: str | None = None) -> list[Filing]:
    """Newest-first primary-document filings of the requested forms, from a
    submissions-index JSON (data.sec.gov/submissions). `filed_lte` (ISO date)
    drops filings filed after a rewind as-of date BEFORE the limit applies,
    so a point-in-time compile sees the filings that existed then."""
    recent = submissions["filings"]["recent"]
    cik = int(submissions["cik"])
    out: list[Filing] = []
    for accession, form, filed, doc in zip(
        recent["accessionNumber"], recent["form"],
        recent["filingDate"], recent["primaryDocument"],
    ):
        if form not in forms:
            continue
        if filed_lte is not None and filed > filed_lte:
            continue
        acc = accession.replace("-", "")
        out.append(Filing(form=form, filed=filed, url=_ARCHIVE_URL.format(
            cik=cik, accession=acc, doc=doc), cik=cik, accession=acc))
        if len(out) == limit:
            break
    logger.debug("recent_filings: %d of forms %s", len(out), forms)
    return out


def fetch_filing_index(filing: Filing) -> dict:
    """index.json of a filing's accession directory (lists every document
    in the filing, exhibits included)."""
    return _get_json(_ARCHIVE_URL.format(
        cik=filing.cik, accession=filing.accession, doc="index.json"))


def ex99_document(index: dict) -> str | None:
    """First EX-99 exhibit filename in an accession index.json (filename
    heuristic: EDGAR filers name exhibit files ex99/ex-99*; 99.1 sorts before
    99.2). None when the filing carries no EX-99 — the primary document is
    then the real content, not a degraded fallback."""
    import re

    names = sorted(item["name"] for item in index["directory"]["item"]
                   if re.search(r"ex-?99", item["name"], re.IGNORECASE))
    return names[0] if names else None


def document_url(filing: Filing, doc: str) -> str:
    """URL of any document inside a filing's accession directory."""
    return _ARCHIVE_URL.format(cik=filing.cik, accession=filing.accession, doc=doc)


def strip_filing_html(raw: str) -> str:
    """Tag-stripped, whitespace-collapsed filing text. The inline-XBRL
    <ix:header> block (hidden metadata, thousands of chars of context ids in
    modern filings — live: MU 10-Q) is removed BEFORE tag-stripping so it
    cannot eat a downstream excerpt cap."""
    import html as _html
    import re

    raw = re.sub(r"<ix:header.*?</ix:header>", " ", raw,
                 flags=re.DOTALL | re.IGNORECASE)
    text = _html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()


def mdna_excerpt(text: str, *, cap: int, form: str) -> str:
    """Excerpt of stripped 10-K/10-Q text starting at the REAL MD&A section
    heading. Form-aware: a 10-Q's MD&A is Item 2, a 10-K's is Item 7 —
    matching both invites anchoring on a cross-reference to the OTHER form
    ("...Item 7 ... of our Annual Report on Form 10-K", live MU 10-Q). Among
    same-item matches the LAST wins: the TOC entry (and any FLS mention) sits
    at the document front. No match falls back to the document front."""
    import re

    item = "7" if form == "10-K" else "2"
    matches = list(re.finditer(
        rf"Item\s+{item}\.?\s+Management.s\s+Discussion\s+and\s+Analysis",
        text, re.IGNORECASE))
    start = matches[-1].start() if matches else 0
    logger.debug("mdna_excerpt: form=%s %d heading matches, anchor at %d",
                 form, len(matches), start)
    return text[start:start + cap]


class Form4ParseError(Exception):
    """A Form 4 transaction block is missing required fields — fail loud,
    never skip-silent (a silently-dropped row would read as no activity)."""


def form4_urls(submissions: dict, *, limit: int,
               filed_lte: str | None = None) -> list[str]:
    """Newest-first raw-XML URLs of form-4 filings from a submissions index.
    `filed_lte` (ISO date) drops filings filed after a rewind as-of date
    before the limit applies. Submissions serve the primaryDocument behind
    the xslF345X06/ viewer prefix; the raw XML lives at the path WITHOUT it
    (live-probed on MU)."""
    recent = submissions["filings"]["recent"]
    cik = int(submissions["cik"])
    out: list[str] = []
    for accession, form, filed, doc in zip(
        recent["accessionNumber"], recent["form"], recent["filingDate"],
        recent["primaryDocument"],
    ):
        if form != "4":
            continue
        if filed_lte is not None and filed > filed_lte:
            continue
        doc = doc.split("/")[-1]
        out.append(_ARCHIVE_URL.format(
            cik=cik, accession=accession.replace("-", ""), doc=doc))
        if len(out) == limit:
            break
    logger.debug("form4_urls: %d filings", len(out))
    return out


def _xml_value(el, path: str) -> str | None:
    node = el.find(path)
    if node is None or node.text is None or not node.text.strip():
        return None
    return node.text.strip()


def form4_rows(xml_text: str) -> list[dict]:
    """One Form 4 XML -> transaction rows {date, insider, role, code, shares,
    price, is_10b5_1}. Non-derivative table only (the row shape and P/S/F/M/A/G
    code enum live there). is_10b5_1 = the post-April-2023 <aff10b5One> plan
    checkbox; absent tag (older filings) = False. Price may legitimately be
    empty (awards) -> None; a missing code/shares/date raises."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)
    insider = _xml_value(root, "./reportingOwner/reportingOwnerId/rptOwnerName")
    if insider is None:
        raise Form4ParseError("no reportingOwner name")
    rel = root.find("./reportingOwner/reportingOwnerRelationship")
    # never None: a Python None would leak into LLM-facing text as "(None)"
    role = "Other"
    if rel is not None:
        if _xml_value(rel, "isOfficer") == "true":
            role = _xml_value(rel, "officerTitle") or "Officer"
        elif _xml_value(rel, "isDirector") == "true":
            role = "Director"
        elif _xml_value(rel, "isTenPercentOwner") == "true":
            role = "10% owner"
        elif _xml_value(rel, "otherText"):
            role = _xml_value(rel, "otherText")
    is_plan = _xml_value(root, "aff10b5One") == "true"

    rows: list[dict] = []
    for txn in root.iterfind(".//nonDerivativeTransaction"):
        date = _xml_value(txn, "./transactionDate/value")
        code = _xml_value(txn, "./transactionCoding/transactionCode")
        shares = _xml_value(txn, "./transactionAmounts/transactionShares/value")
        if date is None or code is None or shares is None:
            raise Form4ParseError(
                f"transaction missing date/code/shares (insider {insider})")
        price = _xml_value(
            txn, "./transactionAmounts/transactionPricePerShare/value")
        rows.append({"date": date, "insider": insider, "role": role,
                     "code": code, "shares": float(shares),
                     "price": float(price) if price is not None else None,
                     "is_10b5_1": is_plan})
    logger.debug("form4_rows: %s — %d transactions (plan=%s)",
                 insider, len(rows), is_plan)
    return rows


def fetch_form4_rows(ticker: str, *, limit: int = 20,
                     filed_lte: str | None = None) -> list[dict]:
    """Live Form 4 rows for a ticker: last `limit` form-4 filings, all
    transactions, newest-filing-first. `filed_lte` bounds the filings
    point-in-time (rewind compile) before the limit applies."""
    urls = form4_urls(fetch_submissions(ticker), limit=limit,
                      filed_lte=filed_lte)
    rows: list[dict] = []
    for url in urls:
        rows.extend(form4_rows(_get_bytes(url).decode("utf-8", errors="replace")))
    return rows


def fetch_submissions(ticker: str) -> dict:
    """Submissions index JSON for a ticker (recent_filings consumes it)."""
    return _get_json(_SUBMISSIONS_URL.format(cik=cik_for(ticker)))


def fetch_filing_text(url: str) -> str:
    """Primary-document text for a Filing.url."""
    return strip_filing_html(_get_bytes(url).decode("utf-8", errors="replace"))

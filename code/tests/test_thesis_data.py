"""thesis-engine unit 4 RED: thesis-input data wrappers.

edgar: submissions index -> recent filings (form filter, archive URLs) +
HTML-to-text strip. polygon: ticker news (cached, rate-limited, mock-DI like
the other polygon tests).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kairos.data import edgar, estimates, polygon


def test_recent_filings_filters_forms_and_builds_urls():
    submissions = {
        "cik": 1851003,
        "filings": {"recent": {
            "accessionNumber": ["0001193125-26-272699", "0001193125-26-199156",
                                "0001193125-26-197172"],
            "form": ["8-K", "10-Q", "4"],
            "filingDate": ["2026-06-16", "2026-05-01", "2026-04-30"],
            "primaryDocument": ["zeta-20260616.htm", "zeta-20260331.htm",
                                "form4.xml"],
        }},
    }
    filings = edgar.recent_filings(submissions, forms=("10-K", "10-Q"), limit=5)
    assert filings == [edgar.Filing(
        form="10-Q",
        filed="2026-05-01",
        url="https://www.sec.gov/Archives/edgar/data/1851003/000119312526199156/zeta-20260331.htm",
        cik=1851003,
        accession="000119312526199156",
    )]


def test_recent_filings_respects_limit():
    submissions = {
        "cik": 7,
        "filings": {"recent": {
            "accessionNumber": [f"0000000000-26-{i:06d}" for i in range(4)],
            "form": ["8-K"] * 4,
            "filingDate": [f"2026-06-{10 + i:02d}" for i in range(4)],
            "primaryDocument": [f"doc{i}.htm" for i in range(4)],
        }},
    }
    assert len(edgar.recent_filings(submissions, forms=("8-K",), limit=2)) == 2


def test_recent_filings_carries_cik_and_accession():
    # U2: the EX-99 exhibit fetch needs the accession dir, which recent_filings
    # previously consumed building the primary-doc URL and discarded
    submissions = {
        "cik": 723125,
        "filings": {"recent": {
            "accessionNumber": ["0000723125-26-000123"],
            "form": ["8-K"],
            "filingDate": ["2026-06-24"],
            "primaryDocument": ["mu-8k_20260624.htm"],
        }},
    }
    (f,) = edgar.recent_filings(submissions, forms=("8-K",), limit=1)
    assert f.cik == 723125
    assert f.accession == "000072312526000123"


_INDEX_JSON = {"directory": {"item": [
    {"name": "0000723125-26-000123-index.htm", "size": "1234"},
    {"name": "mu-8k_20260624.htm", "size": "20000"},
    {"name": "mu-ex99_2.htm", "size": "90000"},
    {"name": "mu-ex99_1.htm", "size": "80000"},
    {"name": "R1.htm", "size": "500"},
]}}


def test_ex99_document_picks_first_ex99_exhibit():
    assert edgar.ex99_document(_INDEX_JSON) == "mu-ex99_1.htm"


def test_ex99_document_none_when_no_exhibit():
    index = {"directory": {"item": [{"name": "gov-8k.htm", "size": "9000"}]}}
    assert edgar.ex99_document(index) is None


def test_document_url_builds_from_filing_accession():
    f = edgar.Filing(form="8-K", filed="2026-06-24",
                     url="https://www.sec.gov/Archives/edgar/data/723125/000072312526000123/mu-8k_20260624.htm",
                     cik=723125, accession="000072312526000123")
    assert edgar.document_url(f, "mu-ex99_1.htm") == (
        "https://www.sec.gov/Archives/edgar/data/723125/000072312526000123/mu-ex99_1.htm")


def test_strip_filing_html():
    raw = "<html><body><p>Revenue&nbsp;grew   <b>25%</b></p><table><tr><td>x</td></tr></table></body></html>"
    assert edgar.strip_filing_html(raw) == "Revenue grew 25% x"


def test_strip_filing_html_drops_inline_xbrl_header():
    # live (MU 10-Q 2026-06-25): the hidden <ix:header> metadata block is
    # thousands of chars of context ids; tag-stripping alone leaves it as
    # leading junk that eats the whole dossier excerpt cap
    raw = ("<html><body><div style=\"display:none\"><ix:header>"
           "<ix:hidden>mu-20260528 0000723125 us-gaap:CommonStockMember"
           " 2025-02-28</ix:hidden></ix:header></div>"
           "<p>Item 2. MD&amp;A: Revenue grew.</p></body></html>")
    assert edgar.strip_filing_html(raw) == "Item 2. MD&A: Revenue grew."


_TENQ_STRIPPED = (
    "UNITED STATES SECURITIES AND EXCHANGE COMMISSION FORM 10-Q (Mark One) "
    "QUARTERLY REPORT Micron Technology, Inc. TABLE OF CONTENTS "
    "Item 1. Financial Statements 3 "
    "Item 2. Management's Discussion and Analysis of Financial Condition and "
    "Results of Operations 24 "
    "Item 3. Quantitative and Qualitative Disclosures About Market Risk 39 "
    "FORWARD-LOOKING STATEMENTS please see the sections entitled Risk Factors "
    "and Management's Discussion and Analysis of Financial Condition and "
    "Results of Operations elsewhere in this report. "
    "PART I. FINANCIAL INFORMATION Item 1. Financial Statements "
    "CONSOLIDATED STATEMENTS OF OPERATIONS Revenue 9,300 8,709 "
    "Item 2. Management's Discussion and Analysis of Financial Condition and "
    "Results of Operations OVERVIEW We are an industry leader in memory. "
    "Total revenue increased 42% driven by HBM demand and pricing."
)


def test_mdna_excerpt_anchors_on_real_section_not_toc_or_fls():
    # live bug (audit 2026-07-08): front-of-doc excerpts returned 100%
    # cover-page + FLS boilerplate; the phrase appears three times (TOC,
    # FLS cross-reference, real heading) and the anchor must pick the LAST
    excerpt = edgar.mdna_excerpt(_TENQ_STRIPPED, cap=200, form="10-Q")
    assert excerpt.startswith("Item 2. Management's Discussion")
    assert "OVERVIEW We are an industry leader" in excerpt
    assert "Mark One" not in excerpt
    assert "TABLE OF CONTENTS" not in excerpt


def test_mdna_excerpt_is_form_aware_and_smart_quote_tolerant():
    # live (MU 10-Q recompile, U8): the doc's LAST MD&A-phrase match was a
    # cross-reference to the ANNUAL report ("Item 7. Management's ... of our
    # Annual Report on Form 10-K") sitting past the real ITEM 2 heading, and
    # real filings use the smart quote + ALL-CAPS heading
    text = ("TABLE OF CONTENTS Item 2. Management’s Discussion and "
            "Analysis 24 ... "
            "ITEM 2. MANAGEMENT’S DISCUSSION AND ANALYSIS OF FINANCIAL "
            "CONDITION AND RESULTS OF OPERATIONS We delivered record revenue. "
            "... see Item 7. Management’s Discussion and Analysis of our "
            "Annual Report on Form 10-K for critical accounting estimates.")
    excerpt = edgar.mdna_excerpt(text, cap=160, form="10-Q")
    assert excerpt.startswith("ITEM 2. MANAGEMENT")
    assert "record revenue" in excerpt
    # a 10-K targets Item 7, ignoring Item 2 mentions
    tenk = ("Item 7. Management’s Discussion and Analysis 55 ... "
            "ITEM 7. MANAGEMENT’S DISCUSSION AND ANALYSIS OF FINANCIAL "
            "CONDITION AND RESULTS OF OPERATIONS Fiscal 2025 revenue grew.")
    assert edgar.mdna_excerpt(tenk, cap=120, form="10-K").startswith(
        "ITEM 7. MANAGEMENT")


def test_mdna_excerpt_falls_back_to_front_when_absent():
    text = "FORM 8-K CURRENT REPORT Item 2.02 Results of Operations. " * 10
    assert edgar.mdna_excerpt(text, cap=80, form="10-Q") == text[:80]


def test_fetch_ticker_news_maps_and_caches(tmp_path: Path):
    calls = []

    class FakeClient:
        def list_ticker_news(self, ticker, limit):
            calls.append(ticker)
            # the real SDK iterator PAGINATES past limit (live: limit=5
            # returned 185 items) -- the wrapper must truncate
            return iter([SimpleNamespace(
                title="ZETA partners with Palantir" if i == 0 else f"extra {i}",
                published_utc="2026-06-23T15:00:00Z",
                article_url="https://example.com/a",
                description="Zeta rebuilds data cloud on Foundry",
            ) for i in range(25)])

    kwargs = dict(
        cache_path=tmp_path / "cache.sqlite",
        client=FakeClient(),
        limiter=polygon.RateLimiter(max_calls=1000, per_seconds=0.001),
    )
    items = polygon.fetch_ticker_news("ZETA", limit=10, **kwargs)
    assert len(items) == 10  # truncated despite the paginating iterator
    assert items[0] == polygon.NewsItem(
        title="ZETA partners with Palantir",
        published_utc="2026-06-23T15:00:00Z",
        url="https://example.com/a",
        description="Zeta rebuilds data cloud on Foundry",
    )
    again = polygon.fetch_ticker_news("ZETA", limit=10, **kwargs)
    assert again == items and calls == ["ZETA"]  # second read from cache


def test_newsitem_legacy_cache_row_loads_without_insights():
    # rows cached before the insights fields existed must still load
    # (NewsItem(**row) read path; frozen dataclass without defaults raises)
    row = {"title": "t", "published_utc": "2026-01-01T00:00:00Z",
           "url": "https://example.com", "description": "d"}
    item = polygon.NewsItem(**row)
    assert item.insights == []


def test_fetch_ticker_news_maps_insights_and_bumps_cache_key(tmp_path: Path):
    import json as _json
    import sqlite3

    class FakeClient:
        def list_ticker_news(self, ticker, limit):
            return iter([SimpleNamespace(
                title="Memory prices surge",
                published_utc="2026-07-01T00:00:00Z",
                article_url="https://example.com/mu",
                description="HBM supply tight",
                insights=[SimpleNamespace(
                    ticker="MU", sentiment="positive",
                    sentiment_reasoning="Micron benefits from HBM pricing"),
                    SimpleNamespace(
                    ticker="NVDA", sentiment="neutral",
                    sentiment_reasoning="mentioned in passing")],
            )])

    cache = tmp_path / "cache.sqlite"
    # poison the PRE-insights cache key: same ticker+limit, old args shape --
    # the wrapper must NOT serve this row (its items carry no insights)
    conn = polygon._ensure_cache(cache)
    polygon._cache_put(
        conn, "fetch_ticker_news",
        _json.dumps({"limit": 1, "ticker": "MU"}, sort_keys=True),
        _json.dumps([{"title": "stale", "published_utc": "x",
                      "url": "u", "description": "old row"}]))
    conn.close()

    items = polygon.fetch_ticker_news(
        "MU", limit=1, cache_path=cache, client=FakeClient(),
        limiter=polygon.RateLimiter(max_calls=1000, per_seconds=0.001))
    assert items[0].title == "Memory prices surge"  # stale key bypassed
    assert items[0].insights == [
        {"ticker": "MU", "sentiment": "positive",
         "sentiment_reasoning": "Micron benefits from HBM pricing"},
        {"ticker": "NVDA", "sentiment": "neutral",
         "sentiment_reasoning": "mentioned in passing"},
    ]


def test_ticker_insight_returns_matching_insight_or_none():
    item = polygon.NewsItem(
        title="t", published_utc="p", url="u", description="d",
        insights=[{"ticker": "MU", "sentiment": "positive",
                   "sentiment_reasoning": "HBM tailwind"}])
    assert polygon.ticker_insight(item, "MU") == {
        "ticker": "MU", "sentiment": "positive",
        "sentiment_reasoning": "HBM tailwind"}
    assert polygon.ticker_insight(item, "GEV") is None
    bare = polygon.NewsItem(title="t", published_utc="p", url="u",
                            description="d")
    assert polygon.ticker_insight(bare, "MU") is None


def test_earnings_from_calendar_returns_iso_date_and_bands():
    import datetime as dt
    cal = {"Dividend Date": dt.date(2026, 7, 20),
           "Earnings Date": [dt.date(2026, 9, 23)],
           "Earnings High": 37.44, "Earnings Low": 28.04,
           "Earnings Average": 31.28511,
           "Revenue High": 59805000000, "Revenue Low": 46911000000,
           "Revenue Average": 50756885130}
    out = estimates.earnings_from_calendar(cal)
    assert out == {"next_earnings_date": "2026-09-23",
                   "eps_consensus": {"low": 28.04, "avg": 31.28511, "high": 37.44},
                   "revenue_consensus": {"low": 46911000000,
                                         "avg": 50756885130,
                                         "high": 59805000000}}


def test_earnings_from_calendar_date_only_when_no_consensus():
    import datetime as dt
    out = estimates.earnings_from_calendar(
        {"Earnings Date": [dt.date(2026, 8, 5), dt.date(2026, 8, 10)]})
    assert out == {"next_earnings_date": "2026-08-05"}  # omit-never-fake bands


def test_earnings_from_calendar_fails_loud_without_date():
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.earnings_from_calendar({})
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.earnings_from_calendar({"Earnings Date": []})


def test_earnings_from_calendar_rejects_stale_date_vs_as_of():
    # stale-e1-next-earnings-date ledger shape (BLZE 2026-05-04, PENG
    # 2026-07-07): yfinance calendar returns an already-reported date;
    # a date <= as_of must raise so [E1] omits, never prints a past date
    import datetime as dt
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.earnings_from_calendar(
            {"Earnings Date": [dt.date(2026, 7, 7)]}, as_of="2026-07-10")


def test_earnings_from_calendar_same_day_as_of_is_stale():
    import datetime as dt
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.earnings_from_calendar(
            {"Earnings Date": [dt.date(2026, 7, 10)]}, as_of="2026-07-10")


def test_earnings_from_calendar_drops_stale_keeps_future_date():
    import datetime as dt
    out = estimates.earnings_from_calendar(
        {"Earnings Date": [dt.date(2026, 7, 7), dt.date(2026, 10, 1)]},
        as_of="2026-07-10")
    assert out == {"next_earnings_date": "2026-10-01"}


def test_earnings_from_calendar_no_as_of_keeps_legacy_behavior():
    import datetime as dt
    out = estimates.earnings_from_calendar(
        {"Earnings Date": [dt.date(2026, 7, 7)]})
    assert out == {"next_earnings_date": "2026-07-07"}




def test_fetch_ticker_news_truncates_poisoned_cache_row(tmp_path: Path):
    # oversized cached payloads must be clamped on read (the pre-truncation
    # wrapper poisoned v1 keys; the guard stays on the live v3 key)
    import json as _json

    cache = tmp_path / "cache.sqlite"
    conn = polygon._ensure_cache(cache)
    args = _json.dumps({"limit": 10, "published_lte": None, "ticker": "ZETA",
                        "v": 3}, sort_keys=True)
    oversized = [{"title": f"t{i}", "published_utc": "2026-06-23T15:00:00Z",
                  "url": "https://example.com", "description": ""} for i in range(185)]
    polygon._cache_put(conn, "fetch_ticker_news", args, _json.dumps(oversized))
    conn.close()

    class NeverCalled:
        def list_ticker_news(self, ticker, limit):
            raise AssertionError("must serve from cache")

    items = polygon.fetch_ticker_news(
        "ZETA", limit=10, cache_path=cache, client=NeverCalled(),
        limiter=polygon.RateLimiter(max_calls=1000, per_seconds=0.001),
    )
    assert len(items) == 10 and items[0].title == "t0"


# --- Form 4 direct (dossier-v4 unit 1): parse + URL derivation ---

# Trimmed to the live-probed MU accession 0001632063-26-000003 shape
# (officer, aff10b5One=true, multiple nonDerivativeTransaction blocks).
_FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
    <periodOfReport>2026-07-01</periodOfReport>
    <issuer><issuerTradingSymbol>MU</issuerTradingSymbol></issuer>
    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>0001632063</rptOwnerCik>
            <rptOwnerName>ARNZEN APRIL S</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>false</isDirector>
            <isOfficer>true</isOfficer>
            <isTenPercentOwner>false</isTenPercentOwner>
            <officerTitle>EVP and Chief People Officer</officerTitle>
        </reportingOwnerRelationship>
    </reportingOwner>
    <aff10b5One>true</aff10b5One>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-07-01</value></transactionDate>
            <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>4279.00</value></transactionShares>
                <transactionPricePerShare><value>1077.05</value></transactionPricePerShare>
            </transactionAmounts>
        </nonDerivativeTransaction>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-07-01</value></transactionDate>
            <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>1247.00</value></transactionShares>
                <transactionPricePerShare><value>1078.47</value></transactionPricePerShare>
            </transactionAmounts>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
</ownershipDocument>"""


def test_form4_rows_maps_owner_role_plan_flag_and_all_transactions():
    rows = edgar.form4_rows(_FORM4_XML)
    assert rows == [
        {"date": "2026-07-01", "insider": "ARNZEN APRIL S",
         "role": "EVP and Chief People Officer", "code": "S",
         "shares": 4279.0, "price": 1077.05, "is_10b5_1": True},
        {"date": "2026-07-01", "insider": "ARNZEN APRIL S",
         "role": "EVP and Chief People Officer", "code": "S",
         "shares": 1247.0, "price": 1078.47, "is_10b5_1": True},
    ]


def test_form4_rows_absent_aff_flag_means_not_plan_and_director_role():
    # pre-April-2023 filings have no aff10b5One tag at all; a director
    # (isOfficer false) takes the "Director" role; buys are code P; an
    # award (code A) legitimately has no price -> None, not fail-loud
    xml = """<?xml version="1.0"?>
<ownershipDocument>
    <reportingOwner>
        <reportingOwnerId><rptOwnerName>SMITH JANE</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>true</isDirector>
            <isOfficer>false</isOfficer>
        </reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>2023-02-10</value></transactionDate>
            <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>1000</value></transactionShares>
                <transactionPricePerShare><value>54.20</value></transactionPricePerShare>
            </transactionAmounts>
        </nonDerivativeTransaction>
        <nonDerivativeTransaction>
            <transactionDate><value>2023-02-10</value></transactionDate>
            <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>500</value></transactionShares>
                <transactionPricePerShare></transactionPricePerShare>
            </transactionAmounts>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
</ownershipDocument>"""
    rows = edgar.form4_rows(xml)
    assert rows == [
        {"date": "2023-02-10", "insider": "SMITH JANE", "role": "Director",
         "code": "P", "shares": 1000.0, "price": 54.20, "is_10b5_1": False},
        {"date": "2023-02-10", "insider": "SMITH JANE", "role": "Director",
         "code": "A", "shares": 500.0, "price": None, "is_10b5_1": False},
    ]


def test_form4_rows_fails_loud_on_unrecognized_transaction_shape():
    # a transaction missing its code/shares must raise, never skip-silent
    xml = """<?xml version="1.0"?>
<ownershipDocument>
    <reportingOwner>
        <reportingOwnerId><rptOwnerName>SMITH JANE</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><isDirector>true</isDirector></reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>2023-02-10</value></transactionDate>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
</ownershipDocument>"""
    with pytest.raises(edgar.Form4ParseError):
        edgar.form4_rows(xml)


def test_form4_urls_filters_form_4_and_strips_xsl_prefix():
    # submissions serve form-4 primaryDocument as xslF345X06/primarydocument.xml;
    # the raw XML lives at the path WITHOUT the viewer prefix (live-probed)
    submissions = {
        "cik": 723125,
        "filings": {"recent": {
            "accessionNumber": ["0001632063-26-000003", "0001193125-26-199156"],
            "form": ["4", "10-Q"],
            "filingDate": ["2026-07-06", "2026-05-01"],
            "primaryDocument": ["xslF345X06/primarydocument.xml",
                                "mu-20260528.htm"],
        }},
    }
    assert edgar.form4_urls(submissions, limit=5) == [
        "https://www.sec.gov/Archives/edgar/data/723125/000163206326000003/primarydocument.xml"
    ]


# --- FINRA consolidated short interest (dossier-v4 unit 3) ---

# Field names pinned to the live-probed response (MU, 2026-07-10 probe;
# Accept: application/json). NEVER equityShortInterest — that dataset is
# OTC-only (MU = 204 empty).
_FINRA_PAYLOAD = [
    {"settlementDate": "2026-05-29", "currentShortPositionQuantity": 37549121,
     "previousShortPositionQuantity": 35235443, "daysToCoverQuantity": 1,
     "changePercent": 6.57, "averageDailyVolumeQuantity": 55527691,
     "symbolCode": "MU", "revisionFlag": None},
    {"settlementDate": "2026-06-15", "currentShortPositionQuantity": 41592382,
     "previousShortPositionQuantity": 37549121, "daysToCoverQuantity": 1,
     "changePercent": 10.77, "averageDailyVolumeQuantity": 53187253,
     "symbolCode": "MU", "revisionFlag": None},
]


def test_finra_short_interest_rows_maps_and_sorts_by_settlement():
    from kairos.data import finra
    rows = finra.short_interest_rows(list(reversed(_FINRA_PAYLOAD)))
    assert rows == [
        {"settlement_date": "2026-05-29", "short_shares": 37549121,
         "days_to_cover": 1.0, "change_pct": 6.57},
        {"settlement_date": "2026-06-15", "short_shares": 41592382,
         "days_to_cover": 1.0, "change_pct": 10.77},
    ]


def test_finra_short_interest_rows_fails_loud_on_error_payload():
    # FINRA returns a dict (statusCode/message), not a list, on a bad request
    from kairos.data import finra
    with pytest.raises(finra.FinraError):
        finra.short_interest_rows(
            {"statusCode": 400, "message": "Bad Request"})


def test_finra_short_interest_rows_fails_loud_on_missing_field():
    from kairos.data import finra
    with pytest.raises(finra.FinraError):
        finra.short_interest_rows([{"settlementDate": "2026-06-15"}])


# --- [E1] estimate dispersion (dossier-v4 unit 5) ---

def _est_frame(rows):
    import pandas as pd
    return pd.DataFrame(rows).set_index("period")


def test_dispersion_from_estimate_frame_hand_computed():
    frame = _est_frame([
        {"period": "0q", "avg": 2.0, "low": 1.5, "high": 2.5,
         "numberOfAnalysts": 10},
        {"period": "0y", "avg": 10.0, "low": 8.0, "high": 12.0,
         "numberOfAnalysts": 25},
    ])
    out = estimates.dispersion_from_estimate_frame(frame)
    # hand-computed: (12.0 - 8.0) / |10.0| = 0.40 — independent literal,
    # never derived from the implementation's own arithmetic
    assert out == {"low": 8.0, "high": 12.0, "avg": 10.0,
                   "spread": 0.4, "analysts": 25}


def test_dispersion_fails_loud_on_empty_or_missing_year_row():
    import pandas as pd
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.dispersion_from_estimate_frame(pd.DataFrame())
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.dispersion_from_estimate_frame(_est_frame(
            [{"period": "0q", "avg": 2.0, "low": 1.5, "high": 2.5,
              "numberOfAnalysts": 10}]))


def test_dispersion_fails_loud_on_nan_bands_or_zero_avg():
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.dispersion_from_estimate_frame(_est_frame(
            [{"period": "0y", "avg": 10.0, "low": float("nan"), "high": 12.0,
              "numberOfAnalysts": 25}]))
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.dispersion_from_estimate_frame(_est_frame(
            [{"period": "0y", "avg": 0.0, "low": -1.0, "high": 1.0,
              "numberOfAnalysts": 25}]))


# --- news de-sentiment (dossier-v4 unit 6) ---

def test_news_context_keeps_reasoning_prose_drops_sentiment_label():
    item = polygon.NewsItem(
        title="Micron guides above consensus",
        published_utc="2026-07-01T12:30:00Z", url="u",
        description="DRAM pricing strength continues.",
        insights=[{"ticker": "MU", "sentiment": "positive",
                   "sentiment_reasoning": "Micron benefits from HBM pricing"}])
    out = polygon.news_context(item, "MU")
    assert out == ("2026-07-01", "Micron guides above consensus",
                   "DRAM pricing strength continues.\n"
                   "context (MU): Micron benefits from HBM pricing")
    _, _, body = out
    # retired markers: the directional label and its render prefix are GONE
    # (fixture prose contains neither string, so these are marker checks,
    # not substring-negation on prose)
    assert "sentiment (" not in body
    assert "positive" not in body


def test_news_context_none_when_not_about_ticker():
    # relevance filter untouched: no matching insight -> item dropped
    item = polygon.NewsItem(
        title="t", published_utc="2026-07-01T12:30:00Z", url="u",
        description="d",
        insights=[{"ticker": "NVDA", "sentiment": "neutral",
                   "sentiment_reasoning": "mentioned in passing"}])
    assert polygon.news_context(item, "MU") is None


def test_form4_rows_other_filer_gets_named_role_not_none():
    # isOther filers (trusts, contractual Section 16) must not leak a
    # Python None into LLM-facing dossier text as "(None)"
    xml = """<?xml version="1.0"?><ownershipDocument>
<reportingOwner><reportingOwnerId><rptOwnerName>TRUST XYZ</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><isOther>true</isOther><otherText>Trustee</otherText></reportingOwnerRelationship></reportingOwner>
<nonDerivativeTable><nonDerivativeTransaction>
<transactionDate><value>2026-07-01</value></transactionDate>
<transactionCoding><transactionCode>S</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>500</value></transactionShares>
<transactionPricePerShare><value>30.0</value></transactionPricePerShare></transactionAmounts>
</nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""
    assert edgar.form4_rows(xml)[0]["role"] == "Trustee"
    no_text = xml.replace("<otherText>Trustee</otherText>", "")
    assert edgar.form4_rows(no_text)[0]["role"] == "Other"


def test_dispersion_fails_loud_on_nan_analyst_count():
    # must raise MissingEstimatesError (runner degrades to line-omitted),
    # never a bare ValueError that aborts the whole ticker's dossier
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.dispersion_from_estimate_frame(_est_frame(
            [{"period": "0y", "avg": 10.0, "low": 8.0, "high": 12.0,
              "numberOfAnalysts": float("nan")}]))


# --- thesis-rewind-eval CONTRACT assertion 1: PIT news fetch ---


def test_a1_fetch_ticker_news_published_lte_bounds_the_fetch(tmp_path: Path):
    seen_kwargs = {}

    class FakeClient:
        def list_ticker_news(self, ticker, limit, **kw):
            seen_kwargs.update(kw)
            return iter([SimpleNamespace(
                title=f"article {d}",
                published_utc=f"{d}T15:00:00Z",
                article_url="https://example.com/a",
                description="body",
            ) for d in ("2026-01-28", "2026-02-02", "2026-02-03")])

    items = polygon.fetch_ticker_news(
        "ZETA", limit=10, published_lte="2026-02-02",
        cache_path=tmp_path / "cache.sqlite",
        client=FakeClient(),
        limiter=polygon.RateLimiter(max_calls=1000, per_seconds=0.001),
    )
    # the bound reaches the API (server-side window)...
    assert seen_kwargs.get("published_utc_lte") == "2026-02-02"
    # ...and is enforced on the returned rows regardless (defense in depth:
    # a cached or misbehaving payload must not leak post-as-of articles)
    assert [i.published_utc[:10] for i in items] == ["2026-01-28", "2026-02-02"]


def test_a1_news_cache_key_isolates_published_lte(tmp_path: Path):
    calls = []

    class FakeClient:
        def list_ticker_news(self, ticker, limit, **kw):
            calls.append(kw.get("published_utc_lte"))
            return iter([SimpleNamespace(
                title="t", published_utc="2026-01-15T09:00:00Z",
                article_url="https://example.com/a", description="",
            )])

    kwargs = dict(cache_path=tmp_path / "cache.sqlite", client=FakeClient(),
                  limiter=polygon.RateLimiter(max_calls=1000, per_seconds=0.001))
    polygon.fetch_ticker_news("ZETA", limit=5, **kwargs)                       # unbounded -> cached
    polygon.fetch_ticker_news("ZETA", limit=5, published_lte="2026-02-02", **kwargs)
    # the bounded call must MISS the unbounded row and hit the API itself
    assert calls == [None, "2026-02-02"]


def test_a1_recent_filings_filed_lte_drops_post_asof_filings():
    submissions = {
        "cik": 7,
        "filings": {"recent": {
            "accessionNumber": [f"0000000000-26-{i:06d}" for i in range(3)],
            "form": ["10-Q", "8-K", "10-K"],
            "filingDate": ["2026-05-01", "2026-02-02", "2026-01-15"],
            "primaryDocument": [f"doc{i}.htm" for i in range(3)],
        }},
    }
    filings = edgar.recent_filings(
        submissions, forms=("10-K", "10-Q", "8-K"), limit=5,
        filed_lte="2026-02-02")
    # the 2026-05-01 10-Q postdates as_of and must vanish; the boundary-date
    # 8-K (filed == as_of) stays
    assert [(f.form, f.filed) for f in filings] == [
        ("8-K", "2026-02-02"), ("10-K", "2026-01-15")]


def test_a1_form4_urls_filed_lte_drops_post_asof_filings():
    submissions = {
        "cik": 7,
        "filings": {"recent": {
            "accessionNumber": [f"0000000000-26-{i:06d}" for i in range(3)],
            "form": ["4", "4", "4"],
            "filingDate": ["2026-04-20", "2026-02-02", "2026-01-10"],
            "primaryDocument": ["xslF345X06/a.xml", "xslF345X06/b.xml",
                                "xslF345X06/c.xml"],
        }},
    }
    urls = edgar.form4_urls(submissions, limit=5, filed_lte="2026-02-02")
    # the April filing postdates as_of; boundary-date filing stays
    assert [u.rsplit("/", 1)[1] for u in urls] == ["b.xml", "c.xml"]


def test_a2_annual_series_filed_lte_serves_the_as_filed_vintage():
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"form": "10-K", "fp": "FY", "start": "2024-01-01",
         "end": "2024-12-31", "val": 100.0, "filed": "2025-02-20"},
        # FY2025 period ENDS before a Feb-2026 as_of but was FILED after it
        {"form": "10-K", "fp": "FY", "start": "2025-01-01",
         "end": "2025-12-31", "val": 150.0, "filed": "2026-02-25"},
        # restatement of FY2024, filed mid-2026: invisible to the rewind
        {"form": "10-K", "fp": "FY", "start": "2024-01-01",
         "end": "2024-12-31", "val": 99.0, "filed": "2026-06-01"},
    ]}}}}}
    # 2026-02-02 rewind: FY2025 not yet filed, restated FY2024 not yet filed
    assert edgar.annual_series(facts, ("Revenues",),
                               filed_lte="2026-02-02") == [
        ("2024-12-31", 100.0)]
    # post-restatement as_of: latest-filed row within the bound wins
    assert edgar.annual_series(facts, ("Revenues",),
                               filed_lte="2026-07-01") == [
        ("2024-12-31", 99.0), ("2025-12-31", 150.0)]


def test_a1_fetch_form4_rows_filed_lte_fetches_only_preasof_filings(monkeypatch):
    submissions = {
        "cik": 7,
        "filings": {"recent": {
            "accessionNumber": ["0000000000-26-000001", "0000000000-26-000002"],
            "form": ["4", "4"],
            "filingDate": ["2026-04-20", "2026-01-10"],
            "primaryDocument": ["xslF345X06/late.xml", "xslF345X06/early.xml"],
        }},
    }
    monkeypatch.setattr(edgar, "fetch_submissions", lambda t: submissions)
    fetched = []

    class FakeResp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return _FORM4_XML.encode()

    def fake_urlopen(req, timeout=None):
        fetched.append(req.full_url.rsplit("/", 1)[1])
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    rows = edgar.fetch_form4_rows("ZETA", filed_lte="2026-02-02")
    assert fetched == ["early.xml"]     # the April filing is never fetched
    assert rows                          # the pre-as-of filing parsed


def test_a3_grouped_daily_miss_counter_counts_cold_fetches(tmp_path: Path):
    class FakeClient:
        def get_grouped_daily_aggs(self, date, adjusted=True):
            return [SimpleNamespace(ticker="SPY", open=1.0, high=1.0, low=1.0,
                                    close=1.0, volume=100, vwap=1.0,
                                    transactions=1, timestamp=0,
                                    otc=None)]

    kwargs = dict(cache_path=tmp_path / "c.sqlite", client=FakeClient(),
                  limiter=polygon.RateLimiter(max_calls=1000, per_seconds=0.001))
    polygon.reset_miss_count()
    polygon.fetch_grouped_daily("2026-02-02", **kwargs)     # cold -> miss
    assert polygon.miss_count() == 1
    polygon.fetch_grouped_daily("2026-02-02", **kwargs)     # warm -> no miss
    assert polygon.miss_count() == 1
    polygon.reset_miss_count()
    assert polygon.miss_count() == 0

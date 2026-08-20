"""thesis-engine dossier enrichment RED: quarterly series from 10-Q rows +
the [Q1] financial-history section (code-computed, None-tolerant).

Analysts on the first live run repeatedly noted 'no income-statement line
items in the excerpts' while the EDGAR series sat in cache — the dossier
now carries them. Missing tags omit lines, never fake values.
"""

from __future__ import annotations

import pytest

from kairos.data import edgar
from kairos.thesis import dossier


def _facts(gaap: dict) -> dict:
    return {"cik": 1, "entityName": "T", "facts": {"us-gaap": gaap}}


def _tag(rows: list[dict]) -> dict:
    return {"units": {"USD": rows}}


def test_quarterly_series_takes_quarter_duration_10q_rows():
    facts = _facts({
        "Revenues": _tag([
            {"start": "2025-01-01", "end": "2025-03-31", "val": 100.0,
             "form": "10-Q", "fp": "Q1"},
            {"start": "2025-04-01", "end": "2025-06-30", "val": 110.0,
             "form": "10-Q", "fp": "Q2"},
            # annual row inside a 10-K: excluded (not a quarter)
            {"start": "2024-01-01", "end": "2024-12-31", "val": 380.0,
             "form": "10-K", "fp": "FY"},
            # 9-month YTD row inside a 10-Q: excluded (not ~a quarter)
            {"start": "2025-01-01", "end": "2025-09-30", "val": 340.0,
             "form": "10-Q", "fp": "Q3"},
        ]),
    })
    assert edgar.quarterly_series(facts, ("Revenues",)) == [
        ("2025-03-31", 100.0), ("2025-06-30", 110.0),
    ]


def test_quarterly_series_raises_when_no_tag_matches():
    with pytest.raises(edgar.MissingFactError):
        edgar.quarterly_series(_facts({}), ("Revenues",))


def test_financial_summary_derives_fcf_margins_and_ps():
    summary = dossier.financial_summary(
        series={
            "revenue": [("2024-12-31", 1000.0), ("2025-12-31", 1200.0)],
            "net_income": [("2024-12-31", 100.0), ("2025-12-31", 180.0)],
            "operating_cash_flow": [("2024-12-31", 150.0), ("2025-12-31", 240.0)],
            "gross_profit": [("2025-12-31", 600.0)],
            "operating_income": [("2025-12-31", 220.0)],
            "capex": [("2025-12-31", 90.0)],
            "total_assets": [("2025-12-31", 2000.0)],
            "stockholders_equity": [("2025-12-31", 900.0)],
            "cash": [("2025-12-31", 300.0)],
            "long_term_debt": [("2025-12-31", 400.0)],
            "shares": [("2024-12-31", 100.0), ("2025-12-31", 101.0)],
        },
        quarterly_revenue=[("2025-06-30", 280.0), ("2025-09-30", 300.0),
                           ("2025-12-31", 330.0)],
        market_cap=6_000.0,
    )
    assert summary["derived"]["free_cash_flow"] == pytest.approx(150.0)  # 240-90
    assert summary["derived"]["gross_margin"] == pytest.approx(0.50)     # 600/1200
    assert summary["derived"]["operating_margin"] == pytest.approx(600/1200*0 + 220/1200)
    assert summary["derived"]["net_margin"] == pytest.approx(0.15)       # 180/1200
    assert summary["derived"]["ps_ratio"] == pytest.approx(5.0)          # 6000/1200
    assert summary["derived"]["debt_to_equity"] == pytest.approx(400/900)
    assert summary["quarterly_revenue"][-1] == ("2025-12-31", 330.0)


def test_financial_summary_omits_underived_metrics_never_fakes():
    summary = dossier.financial_summary(
        series={"revenue": [("2025-12-31", 1200.0)],
                "net_income": [("2025-12-31", 180.0)],
                "operating_cash_flow": [("2025-12-31", 240.0)]},
        quarterly_revenue=None,
        market_cap=None,
    )
    d = summary["derived"]
    assert "free_cash_flow" not in d       # no capex -> omitted
    assert "ps_ratio" not in d             # no mcap -> omitted
    assert "gross_margin" not in d
    assert d["net_margin"] == pytest.approx(0.15)
    assert summary["quarterly_revenue"] is None


def test_dossier_renders_q1_financials_section():
    d = dossier.build(dossier.DossierInputs(
        ticker="MU", as_of="2026-07-07", price=938.38, rs=99.4,
        forensics={"ar_growth": 0.32, "revenue_growth": 0.49,
                   "ni_exceeds_ocf_years": 0, "dilution_rate": 0.01},
        filings=[("10-K", "2025-10-03", "text")],
        news=[], insiders=[], revisions=None,
        financials={"series": {"revenue": [("2025-12-31", 1200.0)]},
                    "quarterly_revenue": [("2025-06-30", 280.0)],
                    "derived": {"net_margin": 0.15},
                    "market_cap": 6000.0},
    ))
    assert "Q1" in d.doc_ids
    assert "[Q1] FINANCIAL HISTORY" in d.text
    assert "net_margin" in d.text and "1200.0" in d.text


def test_dossier_omits_q1_when_financials_absent():
    d = dossier.build(dossier.DossierInputs(
        ticker="MU", as_of="2026-07-07", price=938.38, rs=99.4,
        forensics={}, filings=[], news=[], insiders=[], revisions=None,
        financials=None,
    ))
    assert "Q1" not in d.doc_ids


def test_dossier_renders_stock_health_in_p1():
    d = dossier.build(dossier.DossierInputs(
        ticker="MU", as_of="2026-07-07", price=938.38, rs=99.4,
        forensics={}, filings=[], news=[], insiders=[], revisions=None,
        technicals={"high_52wk": 1210.0, "pct_off_high": -0.224,
                    "ma50": 905.2, "ma200": 610.4,
                    "dollar_vol_20d_median": 2.1e9},
    ))
    assert "Stock health:" in d.text and "pct_off_high" in d.text
    assert "-0.224" in d.text


def test_financial_summary_gates_cross_series_ratios_on_matching_vintage():
    """RED: a ratio whose operands come from different fiscal years is an
    artifact, not a metric (ATEX: gross_profit series ends FY2019, revenue
    FY2026 -> gross_margin -0.1157 printed; ledger shape
    stale-derived-ratio-coverage). Omit-never-fake extends to vintage."""
    summary = dossier.financial_summary(
        series={
            "revenue": [("2025-12-31", 1200.0)],
            "gross_profit": [("2019-12-31", 600.0)],       # stale series
            "operating_income": [("2025-12-31", 220.0)],   # matched
            "net_income": [("2025-12-31", 180.0)],
            "operating_cash_flow": [("2025-12-31", 240.0)],
            "capex": [("2019-12-31", 90.0)],               # stale vs ocf
            "stockholders_equity": [("2025-12-31", 900.0)],
            "long_term_debt": [("2019-12-31", 400.0)],     # stale vs equity
        },
        quarterly_revenue=None,
        market_cap=6_000.0,
    )
    d = summary["derived"]
    assert "gross_margin" not in d          # 2019/2025 artifact -> omitted
    assert "free_cash_flow" not in d        # ocf/capex vintage mismatch
    assert "debt_to_equity" not in d        # equity/debt vintage mismatch
    assert d["operating_margin"] == pytest.approx(220 / 1200)  # matched stays
    assert d["net_margin"] == pytest.approx(0.15)
    assert d["ps_ratio"] == pytest.approx(5.0)  # mcap is spot, revenue latest

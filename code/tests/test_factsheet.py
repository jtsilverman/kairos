"""The stage-2 fact sheet: what a triage agent reads instead of its memory.

A model handed a bare ticker rates its own familiarity with the company,
which is a size filter wearing a quality costume (the recorded failure in
wiki/concepts/rule-out-screen-design.md). The fact sheet carries the
fundamentals and deliberately omits market cap, price and price strength, so
a score that still tracks size is name recognition and nothing else.
"""

from __future__ import annotations

from kairos import factsheet as fs

_SERIES = {
    "revenue": [("2023-12-31", 400.0), ("2024-12-31", 500.0),
                ("2025-12-31", 625.0)],
    "net_income": [("2023-12-31", 32.0), ("2024-12-31", 50.0),
                   ("2025-12-31", 75.0)],
    "operating_cash_flow": [("2024-12-31", 80.0), ("2025-12-31", 100.0)],
    "shares": [("2024-12-31", 200.0), ("2025-12-31", 200.0)],
    "gross_profit": [("2024-12-31", 250.0), ("2025-12-31", 375.0)],
}


def _sheet(**over):
    series = dict(_SERIES)
    series.update(over)
    return fs.build("AAAA", sic_description="Services-Prepackaged Software",
                    series=series)


def test_the_sheet_names_the_ticker_and_the_industry():
    sheet = _sheet()
    assert "AAAA" in sheet
    assert "Services-Prepackaged Software" in sheet


def test_each_annual_series_renders_newest_last():
    sheet = _sheet()
    assert "revenue" in sheet
    assert sheet.index("2023-12-31") < sheet.index("2025-12-31")


def test_year_over_year_growth_is_computed_for_the_latest_year():
    """625 over 500 is +25%, a power-of-two denominator, so exact."""
    assert "+25.0%" in _sheet()


def test_gross_margin_is_computed_where_both_series_exist():
    """375 of 625 is 60.0%."""
    assert "60.0%" in _sheet()


def test_a_missing_series_omits_its_line_and_never_invents_one():
    sheet = _sheet(gross_profit=[])
    assert "gross_profit" not in sheet
    assert "revenue" in sheet


def test_the_sheet_carries_no_market_cap_no_price_and_no_price_strength():
    """The correlation test is score against size. A sheet that states size
    cannot answer it."""
    sheet = _sheet().lower()
    for banned in ("market cap", "mcap", "price", "rs ", "strength"):
        assert banned not in sheet


def test_a_sheet_with_no_usable_series_at_all_is_refused():
    """An empty sheet would be scored on the ticker alone, which is the
    failure this module exists to prevent."""
    assert fs.build("AAAA", sic_description="x", series={}) is None


def test_the_cagr_spans_only_the_years_the_sheet_shows():
    """A sheet that prints 5 rows and quotes a CAGR over 11 years states a
    number the reader cannot check against anything in front of them."""
    long_revenue = [(f"20{y:02d}-12-31", 100.0 * 2 ** i)
                    for i, y in enumerate(range(15, 26))]
    sheet = fs.build("AAAA", sic_description="x",
                     series={"revenue": long_revenue})
    assert "REVENUE CAGR over 4y +100.0%" in sheet
    assert "over 10y" not in sheet


# --- leverage: a debt balance with no denominator cannot be read ---

_LEVERED = {
    "revenue": [("2024-12-31", 800.0), ("2025-12-31", 1000.0)],
    "operating_income": [("2024-12-31", 200.0), ("2025-12-31", 250.0)],
    "operating_cash_flow": [("2024-12-31", 400.0), ("2025-12-31", 500.0)],
    "long_term_debt": [("2024-12-31", 1000.0), ("2025-12-31", 2000.0)],
    "cash": [("2024-12-31", 250.0), ("2025-12-31", 250.0)],
    "interest_expense": [("2024-12-31", 40.0), ("2025-12-31", 50.0)],
}


def test_net_debt_to_operating_cash_flow_is_stated():
    """2000 debt less 250 cash over 500 OCF is 3.5x, a power-of-two
    denominator, so exact."""
    sheet = fs.build("AAAA", sic_description="x", series=_LEVERED)
    assert "NET DEBT / OPERATING CASH FLOW 3.5x" in sheet


def test_interest_coverage_is_stated():
    """250 operating income over 50 interest is 5.0x."""
    sheet = fs.build("AAAA", sic_description="x", series=_LEVERED)
    assert "INTEREST COVERAGE 5.0x" in sheet


def test_leverage_lines_are_omitted_when_the_inputs_are_missing():
    """A ratio invented from a missing denominator is worse than no ratio."""
    series = dict(_LEVERED)
    series["operating_cash_flow"] = []
    series["interest_expense"] = []
    sheet = fs.build("AAAA", sic_description="x", series=series)
    assert "NET DEBT / OPERATING CASH FLOW" not in sheet
    assert "INTEREST COVERAGE" not in sheet


def test_net_debt_is_negative_when_cash_exceeds_debt():
    series = dict(_LEVERED)
    series["cash"] = [("2025-12-31", 3000.0)]
    sheet = fs.build("AAAA", sic_description="x", series=series)
    assert "NET DEBT / OPERATING CASH FLOW -2.0x" in sheet


# --- three bugs the opus adjudicator found by reading the raw series ---

def test_interest_coverage_uses_the_magnitude_of_interest():
    """Filers tag interest expense either sign. ATRO stored -23.3M, so
    76.4/-23.3 printed -3.3x and two seats read it as failing to cover."""
    series = {
        "revenue": [("2025-12-31", 862.1)],
        "operating_income": [("2025-12-31", 76.4)],
        "interest_expense": [("2025-12-31", -23.3)],
    }
    sheet = fs.build("AAAA", sic_description="x", series=series)
    assert "INTEREST COVERAGE 3.3x" in sheet
    assert "-3.3x" not in sheet


def test_coverage_stays_negative_when_operating_income_is_negative():
    """A loss-making company genuinely cannot cover interest. Only the
    interest sign is normalised, never the earnings sign."""
    series = {
        "revenue": [("2025-12-31", 100.0)],
        "operating_income": [("2025-12-31", -50.0)],
        "interest_expense": [("2025-12-31", 25.0)],
    }
    assert "INTEREST COVERAGE -2.0x" in fs.build("AAAA", sic_description="x",
                                                 series=series)


def test_a_leverage_ratio_needs_its_inputs_from_the_same_period():
    """ARMK's debt series ends at 2019 with 0.0M, so the ratio printed
    -0.8x, net cash, for a company paying 364M of annual interest."""
    series = {
        "revenue": [("2025-12-31", 18506.3)],
        "operating_cash_flow": [("2025-12-31", 900.0)],
        "long_term_debt": [("2019-12-31", 0.0)],
        "cash": [("2025-12-31", 700.0)],
    }
    assert "NET DEBT / OPERATING CASH FLOW" not in fs.build(
        "AAAA", sic_description="x", series=series)


def test_a_margin_off_a_stale_row_carries_its_own_date():
    """ANF's gross margin came from 2024-02-03 and read as current."""
    series = {
        "revenue": [("2024-02-03", 4000.0), ("2026-01-31", 5266.3)],
        "gross_profit": [("2024-02-03", 2500.0)],
    }
    sheet = fs.build("AAAA", sic_description="x", series=series)
    assert "gross margin 62.5% as of 2024-02-03" in sheet
    assert "latest gross margin" not in sheet


def test_a_margin_on_the_latest_period_is_still_called_latest():
    series = {
        "revenue": [("2025-12-31", 1000.0)],
        "gross_profit": [("2025-12-31", 625.0)],
    }
    assert "latest gross margin 62.5%" in fs.build("AAAA", sic_description="x",
                                                   series=series)


def test_the_sheet_names_every_series_that_stopped_early():
    """A reader cannot spot a dead XBRL tag from the rows alone."""
    series = {
        "revenue": [("2025-12-31", 1000.0)],
        "long_term_debt": [("2013-12-31", 50.0)],
    }
    sheet = fs.build("AAAA", sic_description="x", series=series)
    assert "STALE SERIES" in sheet
    assert "long_term_debt last reported 2013-12-31" in sheet

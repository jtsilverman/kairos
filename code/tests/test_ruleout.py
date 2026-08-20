"""Rule-outs 5rev/6/7/8 of the screen of record (docs/ruleout-screen-2026-08.md).

Every expected value is hand-set from the fixture. Ratios use power-of-two
denominators so `==` is exact.
"""

from __future__ import annotations

import pytest

from kairos import ruleout as ro


# --- rule 6: businesses whose results are set by a price nobody there sets ---

@pytest.mark.parametrize("sic", [1000, 1311, 1389, 1400, 3312, 3350, 3399,
                                 3533, 4400, 4412, 4731, 4900, 4922, 4999,
                                 8062])
def test_exogenous_sectors_are_denied(sic):
    assert ro.is_exogenous_sector(sic) is True


@pytest.mark.parametrize("sic", [999, 1500, 2834, 3299, 3400, 3571, 4399,
                                 4500, 4730, 4732, 5000, 6021, 7372, 8061,
                                 8063])
def test_sectors_outside_the_deny_list_survive(sic):
    assert ro.is_exogenous_sector(sic) is False


def test_a_missing_sic_is_not_denied():
    """An unreadable SIC is not evidence of an exogenous business, and a
    rule-out must never fire on absent evidence."""
    assert ro.is_exogenous_sector(None) is False
    assert ro.is_exogenous_sector(0) is False


# --- rule 5, financial vs non-financial split ---

@pytest.mark.parametrize("sic,expected", [(6000, True), (6021, True),
                                          (6798, True), (6799, True),
                                          (5999, False), (6800, False),
                                          (None, False)])
def test_financial_classification_is_the_sic_6000_band(sic, expected):
    assert ro.is_financial(sic) is expected


def test_book_value_per_share_divides_equity_by_shares_on_matching_periods():
    equity = [("2024-12-31", 100.0), ("2025-12-31", 125.0)]
    shares = [("2024-12-31", 100.0), ("2025-12-31", 100.0)]
    assert ro.book_value_per_share(equity, shares) == [("2024-12-31", 1.0),
                                                       ("2025-12-31", 1.25)]


def test_book_value_per_share_drops_a_period_with_no_share_count():
    equity = [("2024-12-31", 100.0), ("2025-12-31", 125.0)]
    shares = [("2025-12-31", 100.0)]
    assert ro.book_value_per_share(equity, shares) == [("2025-12-31", 1.25)]


def test_a_financial_must_compound_earnings_and_book_value_together():
    assert ro.financial_compounding(0.25, 0.25) is True
    assert ro.financial_compounding(0.25, -0.0625) is False   # UNH shape
    assert ro.financial_compounding(-0.5, 0.25) is False      # MET shape


def test_a_financial_with_either_growth_unreadable_is_ruled_out():
    """Rule 5f requires both proofs. A missing one cannot be assumed passed."""
    assert ro.financial_compounding(None, 0.25) is False
    assert ro.financial_compounding(0.25, None) is False


def test_a_non_financial_collapses_only_on_a_deep_drop_with_no_investment():
    assert ro.nonfinancial_collapsing(-0.5, None, None) is True
    assert ro.nonfinancial_collapsing(-0.5, 0.25, None) is False   # capex rescues
    assert ro.nonfinancial_collapsing(-0.5, None, 0.25) is False   # r&d rescues
    assert ro.nonfinancial_collapsing(-0.125, None, None) is False  # inside -25%


def test_a_non_financial_with_unreadable_earnings_is_not_collapsing():
    assert ro.nonfinancial_collapsing(None, None, None) is False


# --- rule 7: a growth rate off a tiny base is arithmetic noise ---

def test_revenue_growth_off_a_base_under_twenty_million_is_noise():
    assert ro.revenue_base_ok([("2024-12-31", 3_600_000.0),
                               ("2025-12-31", 840_000_000.0)]) is False
    assert ro.revenue_base_ok([("2024-12-31", 20_000_000.0),
                               ("2025-12-31", 25_000_000.0)]) is True


def test_a_single_year_of_revenue_has_no_prior_base_to_judge():
    assert ro.revenue_base_ok([("2025-12-31", 500_000_000.0)]) is False


# --- rule 8: one ticker per filer ---

def test_a_filer_keeps_only_its_first_ticker():
    rows = [("GOOGL", 1652044), ("NVDA", 1045810), ("GOOG", 1652044)]
    assert ro.first_per_filer(rows) == ["GOOGL", "NVDA"]


def test_a_ticker_with_no_readable_filer_is_kept():
    """Dropping a name for an unreadable CIK would rule out on absent
    evidence; the duplicate rule needs proof two tickers share a filer."""
    rows = [("AAAA", None), ("BBBB", None)]
    assert ro.first_per_filer(rows) == ["AAAA", "BBBB"]

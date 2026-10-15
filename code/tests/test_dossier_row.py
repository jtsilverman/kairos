"""prompt-tuning unit 8: the survivor row the dossier compiler can read.

Two screens emitted two shapes. `ruleout_screen.py` wrote
`{ticker, cik, sic, rs, rev_growth, mcap_b}`; `thesis_dossiers.py` reads
`survivor["price"]`, `["rs"]` and `["forensics"]`, which is what
`weekly_screen.py` emits. Nothing bridged them, so a real compile failed 25
of 25 on `KeyError: 'price'`.

The bridge lives here rather than in `ruleout_screen.py` because that script
runs its whole screen at import time, so a test cannot reach a function
inside it without executing the screen.
"""

from __future__ import annotations

import pytest

from kairos import screen


def _bars() -> screen.BarsSummary:
    # 260 sessions so the 252-session lookbacks are full.
    closes = [100.0] * 200 + [120.0] * 60
    return screen.BarsSummary(
        price=125.0,
        dollar_vol_20d_median=5_000_000.0,
        closes=closes,
        highs=[150.0] * 260,
        lows=[80.0] * 260,
    )


def _fundamentals() -> dict:
    return {
        "revenue": [("2024-12-31", 100.0), ("2025-12-31", 200.0)],
        "receivables": [("2024-12-31", 50.0), ("2025-12-31", 75.0)],
        "net_income": [("2024-12-31", 10.0), ("2025-12-31", 25.0)],
        "operating_cash_flow": [("2024-12-31", 20.0), ("2025-12-31", 50.0)],
        "shares": [("2024-12-31", 1000.0), ("2025-12-31", 1250.0)],
    }


def test_the_row_carries_every_field_the_compiler_reads():
    row = screen.dossier_row(ticker="AAA", cik=123, sic=3600, rs=98.5,
                             rev_growth=1.0, market_cap=5e9,
                             bars=_bars(), series=_fundamentals())

    for key in ("ticker", "cik", "sic", "rs", "price", "forensics",
                "technicals", "mcap_b", "rev_growth"):
        assert key in row, f"the dossier compiler reads {key!r}"


def test_forensics_come_from_the_screen_not_a_second_copy():
    """`screen.forensics` is the one place these ratios are defined. A second
    implementation here would drift from the gate that uses it."""
    series = _fundamentals()
    row = screen.dossier_row(ticker="AAA", cik=1, sic=3600, rs=90.0,
                             rev_growth=1.0, market_cap=1e9,
                             bars=_bars(), series=series)

    expected = screen.forensics(screen.Fundamentals(
        revenue=series["revenue"], receivables=series["receivables"],
        net_income=series["net_income"],
        operating_cash_flow=series["operating_cash_flow"],
        shares=series["shares"]))

    assert row["forensics"] == expected
    # 75/50 - 1 = 0.5, and 200/100 - 1 = 1.0. Both exact in binary.
    assert row["forensics"]["ar_growth"] == pytest.approx(0.5)
    assert row["forensics"]["revenue_growth"] == pytest.approx(1.0)
    # Shares 1000 -> 1250 is +25%, which the screen reports as dilution.
    assert row["forensics"]["dilution_rate"] == pytest.approx(0.25)


def test_price_and_technicals_come_from_the_bars():
    row = screen.dossier_row(ticker="AAA", cik=1, sic=3600, rs=90.0,
                             rev_growth=1.0, market_cap=1e9,
                             bars=_bars(), series=_fundamentals())

    assert row["price"] == pytest.approx(125.0)
    assert row["technicals"]["high_52wk"] == pytest.approx(150.0)
    assert row["technicals"]["low_52wk"] == pytest.approx(80.0)
    # Last 200 of 260 closes = 140 at 100.0 plus 60 at 120.0, mean 106.0.
    assert row["technicals"]["ma200"] == pytest.approx(106.0)
    # Last 50 are all 120.0.
    assert row["technicals"]["ma50"] == pytest.approx(120.0)


def test_a_missing_series_yields_none_rather_than_raising():
    """A thin filer must produce a row with holes, never kill the cohort.
    `thesis_dossiers.py` is omit-never-fake and reads None fine."""
    row = screen.dossier_row(ticker="AAA", cik=1, sic=3600, rs=90.0,
                             rev_growth=None, market_cap=1e9,
                             bars=_bars(), series={"revenue": []})

    assert row["forensics"]["revenue_growth"] is None
    assert row["forensics"]["ar_growth"] is None
    assert row["rev_growth"] is None

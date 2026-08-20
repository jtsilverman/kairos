"""RED: [P1] high_52wk must come from intraday HIGH bars, not closes.

Close-based high_52wk understates the true range: AMAT's dossier printed
high_52wk 723.0 while [I1] carried a Form-4 sale @ 735.22 — a sale above
the section's own "high" (audit ledger shape p1-price-inconsistency,
SYSTEMIC 2026-07-11). Same for low_52wk from intraday lows.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from kairos import screen

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "weekly_screen.py"
_spec = importlib.util.spec_from_file_location("weekly_screen", _SCRIPT)
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)


def _bars(*, closes, highs, lows):
    return screen.BarsSummary(
        price=closes[-1],
        dollar_vol_20d_median=40_000_000.0,
        closes=closes,
        highs=highs,
        lows=lows,
    )


def test_high_low_52wk_use_intraday_bars_not_closes():
    n = 253
    closes = [100.0] * n
    highs = [101.0] * n
    lows = [99.0] * n
    # the AMAT shape: an intraday spike the closes never printed
    highs[200] = 735.22
    closes[200] = 723.0
    lows[10] = 88.5
    t = ws._technicals(_bars(closes=closes, highs=highs, lows=lows))
    assert t["high_52wk"] == 735.22
    assert t["low_52wk"] == 88.5
    assert t["pct_off_high"] == round(closes[-1] / 735.22 - 1.0, 4)


def test_window_is_trailing_252_sessions_of_bars():
    n = 300  # longer history: only the trailing 252 count
    closes = [100.0] * n
    highs = [110.0] * n
    lows = [90.0] * n
    highs[0] = 999.0  # outside the trailing window -> ignored
    lows[0] = 1.0
    t = ws._technicals(_bars(closes=closes, highs=highs, lows=lows))
    assert t["high_52wk"] == 110.0
    assert t["low_52wk"] == 90.0

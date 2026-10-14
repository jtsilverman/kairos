"""thesis-rewind-eval CONTRACT assertion 4: the retro scorer.

Mirrors the ledger outcome definition (entry first close STRICTLY after
as_of; exit first close on/after as_of + 8 weeks; alpha = ticker return -
SPY return; hit sign by direction), prints Spearman rank correlation,
Brier by band, and the challenger-p distribution, deterministically.
Expected values hand-computed, never recomputed through the scorer's math.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "score_rewind.py"
_spec = importlib.util.spec_from_file_location("score_rewind", _SCRIPT)
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)


_SERIES = [
    ("2026-02-02", 100.0),   # as_of itself: never the entry
    ("2026-02-03", 100.0),   # entry (first close strictly after)
    ("2026-03-27", 105.0),
    ("2026-03-30", 110.0),   # the OLD 56-day exit; now an ordinary bar
    ("2026-04-01", 130.0),
    ("2026-05-04", 110.0),   # first close on/after 2026-05-04 (= as_of+91d)
    ("2026-05-05", 140.0),   # roll-forward target when 05-04 is missing
]
_SPY = [
    ("2026-02-02", 500.0),
    ("2026-02-03", 500.0),
    ("2026-03-27", 510.0),
    ("2026-03-30", 525.0),
    ("2026-04-01", 550.0),
    ("2026-05-04", 525.0),
    ("2026-05-05", 560.0),
]


def test_a4_outcome_entry_strictly_after_exit_on_or_after_horizon():
    o = sr.outcome(_SERIES, _SPY, as_of="2026-02-02")
    assert o["entry_date"] == "2026-02-03"
    assert o["exit_date"] == "2026-05-04"
    # hand math: ticker 110/100-1 = +10%; SPY 525/500-1 = +5%; alpha +5%
    assert o["alpha"] == pytest.approx(0.05)
    assert o["beat"] is True


def test_a4_outcome_rolls_exit_forward_over_missing_bars():
    series = [s for s in _SERIES if s[0] != "2026-05-04"]
    spy = [s for s in _SPY if s[0] != "2026-05-04"]
    o = sr.outcome(series, spy, as_of="2026-02-02")
    assert o["exit_date"] == "2026-05-05"      # first AVAILABLE on/after horizon


def test_a4_outcome_fails_loud_when_series_ends_before_horizon():
    with pytest.raises(sr.IncompleteWindowError):
        sr.outcome(_SERIES[:2], _SPY[:2], as_of="2026-02-02")


def test_a4_spearman_known_values():
    assert sr.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert sr.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    # hand-computed: ranks x=[1,2,3,4], y=[2,1,4,3] -> d2=[1,1,1,1],
    # rho = 1 - 6*4/(4*15) = 0.6
    assert sr.spearman([1, 2, 3, 4], [5, 3, 9, 7]) == pytest.approx(0.6)


def test_a4_brier_by_band_hand_computed():
    rows = [
        {"p": 0.80, "beat": True},    # A band: (0.80-1)^2 = 0.04
        {"p": 0.70, "beat": False},   # B band: (0.70-0)^2 = 0.49
        {"p": 0.66, "beat": True},    # B band: (0.66-1)^2 = 0.1156
        # 0.5 exactly is contractually illegal (memo._check_p: "not a
        # verdict") — the scorer inherits the live rule, so the fixture
        # stays off it
        {"p": 0.51, "beat": False},   # C band: (0.51-0)^2 = 0.2601
    ]
    out = sr.brier_by_band(rows)
    assert out["A"] == pytest.approx(0.04)
    assert out["B"] == pytest.approx((0.49 + 0.1156) / 2)
    assert out["C"] == pytest.approx(0.2601)


def test_a4_challenger_distribution_reports_bullish_fraction():
    d = sr.challenger_distribution([0.2, 0.3, 0.55, 0.4])
    assert d["n"] == 4
    assert d["frac_above_half"] == pytest.approx(0.25)


def test_outcome_takes_an_explicit_horizon_and_the_constant_stays_91():
    """thesis-exemplars unit 7: the two-quarter window is an explicit
    parameter, never a change to the frozen one-quarter constant."""
    import datetime as dt
    as_of = "2026-02-02"
    days = [(dt.date(2026, 2, 2) + dt.timedelta(days=i)).isoformat() for i in range(1, 200)]
    series = [(d, 100.0 + i) for i, d in enumerate(days)]
    spy = [(d, 100.0) for d in days]
    one_q = sr.outcome(series, spy, as_of=as_of)
    two_q = sr.outcome(series, spy, as_of=as_of, horizon_days=182)
    assert sr.HORIZON_DAYS == 91
    assert one_q["exit_date"] == "2026-05-04"
    assert two_q["exit_date"] == "2026-08-03"
    assert two_q["ticker_return"] > one_q["ticker_return"]

"""thesis-engine unit 1 RED: RS module (weighted score, field percentile,
level+rising gate).

Expected values are hand-computed literals on constructed series -- never
recomputed through the module's own return math (anti-tautology).
"""

from __future__ import annotations

import pytest

from kairos.signals import rs


def _series_with_returns(r63: float, r126: float, r252: float) -> list[float]:
    """253 closes ending at 100.0 whose trailing 63/126/252-session returns are
    exactly the arguments. Only the four anchor closes matter to rs_raw; filler
    values between anchors are flat segments."""
    end = 100.0
    c63 = end / (1 + r63)    # closes[-64]
    c126 = end / (1 + r126)  # closes[-127]
    c252 = end / (1 + r252)  # closes[-253]
    closes = [c252] * 253
    for i in range(-127, 0):
        closes[i] = c126
    for i in range(-64, 0):
        closes[i] = c63
    closes[-1] = end
    return closes


def test_rs_raw_weights_trailing_returns_40_30_30():
    closes = _series_with_returns(r63=0.10, r126=0.20, r252=0.40)
    # hand math: 0.4*0.10 + 0.3*0.20 + 0.3*0.40 = 0.04 + 0.06 + 0.12 = 0.22
    assert rs.rs_raw(closes) == pytest.approx(0.22)


def test_rs_raw_insufficient_history_returns_none():
    closes = [100.0] * 252  # one short of the 253 needed for r_252d
    assert rs.rs_raw(closes) is None


def test_rs_percentile_ranks_within_field():
    scores = {"AAA": 0.50, "BBB": 0.10, "CCC": -0.20, "DDD": 0.30}
    pct = rs.rs_percentile(scores)
    # rank order CCC < BBB < DDD < AAA; percentile = 100 * rank / (n - 1)
    assert pct["CCC"] == pytest.approx(0.0)
    assert pct["BBB"] == pytest.approx(100 / 3)
    assert pct["DDD"] == pytest.approx(200 / 3)
    assert pct["AAA"] == pytest.approx(100.0)


def test_rs_percentile_excludes_none_scores():
    scores = {"AAA": 0.50, "SHORT": None, "BBB": 0.10}
    pct = rs.rs_percentile(scores)
    assert "SHORT" not in pct
    assert pct["BBB"] == pytest.approx(0.0)
    assert pct["AAA"] == pytest.approx(100.0)


def test_rs_gate_requires_level_and_rising():
    assert rs.rs_gate(current=75.0, prior=60.0) is True
    assert rs.rs_gate(current=75.0, prior=80.0) is False   # level ok, falling
    assert rs.rs_gate(current=65.0, prior=40.0) is False   # rising, level short
    assert rs.rs_gate(current=70.0, prior=70.0) is False   # flat is not rising
    assert rs.rs_gate(current=70.0, prior=69.0) is True    # boundary: 70 counts


# --- price legs (dossier-data U3): the RS score's decomposition ---

def test_price_legs_hand_computed():
    # closes[-64]=100, closes[-127]=80, closes[-253]=60, last=120:
    # legs 120/100-1, 120/80-1, 120/60-1 — piecewise-constant fixture,
    # values between the anchor indices are irrelevant to the legs.
    closes = [60.0] * 126 + [80.0] * 63 + [100.0] * 63 + [120.0]
    assert len(closes) == 253
    assert rs.price_legs(closes) == {
        "63d": 120.0 / 100.0 - 1,
        "126d": 120.0 / 80.0 - 1,
        "252d": 120.0 / 60.0 - 1,
    }


def test_price_legs_none_on_insufficient_history():
    # mirrors rs_raw: a partial decomposition would misrepresent the score
    assert rs.price_legs([10.0] * 252) is None

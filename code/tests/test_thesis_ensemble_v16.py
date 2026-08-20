"""thesis-scale-v16 aggregate: two p_outperform seats -> one aggregate p,
direction/tier derived. Same-side -> nearer 0.5 (worse-of-two analog);
opposite sides -> the panel disagrees on direction, so the verdict can never
be actionable: fable's value clamped just inside the no-action zone.
Expected values HAND-WRITTEN from the spec's frozen rules, never recomputed
through the implementation.
"""

from __future__ import annotations

import pytest

from kairos.thesis import ensemble


def _judges(p_opus, p_fable):
    return [{"seat": "opus", "p_outperform": p_opus},
            {"seat": "fable", "p_outperform": p_fable}]


def test_same_side_long_nearer_half_wins():
    agg = ensemble.aggregate_v16(_judges(0.72, 0.81))
    assert agg["p_outperform"] == 0.72
    assert agg["direction"] == "long"
    assert agg["tier"] == "B"


def test_same_side_short_nearer_half_wins():
    agg = ensemble.aggregate_v16(_judges(0.28, 0.31))
    assert agg["p_outperform"] == 0.31
    assert agg["direction"] == "short"
    assert agg["tier"] == "B"


def test_same_side_top_band_survives():
    agg = ensemble.aggregate_v16(_judges(0.86, 0.82))
    assert agg["p_outperform"] == 0.82
    assert agg["tier"] == "A"


def test_extreme_straddle_clamps_to_no_action():
    # reviewer-F1 fixture: a split 0.95/0.10 panel must NEVER be actionable
    agg = ensemble.aggregate_v16(_judges(0.95, 0.10))
    assert agg["p_outperform"] == 0.36
    assert agg["direction"] == "short"
    assert agg["tier"] == "C"


def test_split_fable_long_clamps_to_no_action():
    agg = ensemble.aggregate_v16(_judges(0.30, 0.70))
    assert agg["p_outperform"] == 0.64
    assert agg["direction"] == "long"
    assert agg["tier"] == "C"


def test_split_fable_already_inside_no_action_passes_through():
    agg = ensemble.aggregate_v16(_judges(0.60, 0.45))
    assert agg["p_outperform"] == 0.45
    assert agg["direction"] == "short"
    assert agg["tier"] == "C"


def test_judges_carried_in_aggregate():
    judges = _judges(0.72, 0.81)
    assert ensemble.aggregate_v16(judges)["judges"] == judges


def test_wrong_seat_names_raise():
    judges = [{"seat": "opus", "p_outperform": 0.7},
              {"seat": "opus", "p_outperform": 0.6}]
    with pytest.raises(ensemble.EnsembleError, match="seat"):
        ensemble.aggregate_v16(judges)


def test_wrong_count_raises():
    with pytest.raises(ensemble.EnsembleError, match="2"):
        ensemble.aggregate_v16([{"seat": "opus", "p_outperform": 0.7}])


def test_p_half_raises():
    with pytest.raises(Exception, match="0.5"):
        ensemble.aggregate_v16(_judges(0.5, 0.7))


def test_missing_p_raises():
    judges = [{"seat": "opus"}, {"seat": "fable", "p_outperform": 0.7}]
    with pytest.raises(Exception, match="p_outperform"):
        ensemble.aggregate_v16(judges)


def test_count_dispatch_untouched_by_v16():
    # aggregate()'s count dispatch stays v9/v8-only; a 2-judge tier payload
    # still routes to aggregate_v9, never to the p path
    judges = [{"seat": "opus", "tier": "B", "direction": "long"},
              {"seat": "fable", "tier": "A", "direction": "long"}]
    assert ensemble.aggregate(judges)["tier"] == "B"


def test_clamp_knobs_sit_strictly_inside_the_no_action_zone():
    # tuning-loop invariant (U7): a threshold move that leaves the clamps
    # outside the zone makes a SPLIT panel actionable — the exact failure
    # the clamp exists to prevent. Guards the knobs, not the literals.
    from kairos.thesis import memo
    assert memo.ACTIONABLE_SHORT < memo.NO_ACTION_CLAMP_SHORT < 0.5
    assert 0.5 < memo.NO_ACTION_CLAMP_LONG < memo.ACTIONABLE_LONG

"""Frozen v8 ensemble rule (3 seats), via the era dispatcher.

Spec rule (pinned 2026-07-09, frozen by thesis-judges-v9): direction must be
UNANIMOUS for the median tier to stand; any 2-1 direction split -> tier C
no-trade with the majority direction recorded. `aggregate` era-dispatches on
judge count (3 -> this rule; 2 -> v9, tested in test_thesis_ensemble_v9.py),
so a seatless 2-payload list raises on the v9 seat check.
"""

import pytest

from kairos.thesis import ensemble


def _judge(tier, direction):
    return {"tier": tier, "direction": direction,
            "rationale": "r", "decisive_citations": ["F1"],
            "adversary_adjudication": []}


def test_unanimous_direction_takes_median_tier():
    agg = ensemble.aggregate([_judge("A", "long"),
                              _judge("B", "long"),
                              _judge("C", "long")])
    assert agg["direction"] == "long"
    assert agg["tier"] == "B"  # median of A,B,C — hand-computed


def test_direction_split_forces_tier_c_with_majority_direction():
    agg = ensemble.aggregate([_judge("A", "long"),
                              _judge("A", "long"),
                              _judge("A", "short")])
    assert agg["tier"] == "C"          # split kills the trade, tiers ignored
    assert agg["direction"] == "long"  # 2-1 majority recorded


def test_unanimous_two_same_tiers_median_is_that_tier():
    agg = ensemble.aggregate([_judge("B", "short"),
                              _judge("B", "short"),
                              _judge("C", "short")])
    assert agg["tier"] == "B"
    assert agg["direction"] == "short"


def test_aggregate_carries_all_three_judge_payloads():
    judges = [_judge("B", "long"), _judge("B", "long"), _judge("C", "long")]
    agg = ensemble.aggregate(judges)
    assert agg["judges"] == judges


def test_wrong_count_raises():
    with pytest.raises(ensemble.EnsembleError):
        ensemble.aggregate([_judge("B", "long"), _judge("B", "long")])


def test_malformed_tier_raises():
    bad = _judge("D", "long")
    with pytest.raises(ensemble.EnsembleError):
        ensemble.aggregate([_judge("B", "long"), _judge("B", "long"), bad])


def test_malformed_direction_raises():
    bad = _judge("B", "flat")
    with pytest.raises(ensemble.EnsembleError):
        ensemble.aggregate([_judge("B", "long"), _judge("B", "long"), bad])


def test_exhaustive_invariants_over_all_input_combos():
    """216-combo sweep: split always -> C; unanimous -> median by ordinal;
    direction always the majority of inputs."""
    import itertools
    for tiers in itertools.product("ABC", repeat=3):
        for dirs in itertools.product(("long", "short"), repeat=3):
            agg = ensemble.aggregate(
                [_judge(t, d) for t, d in zip(tiers, dirs)])
            assert agg["direction"] == max(("long", "short"),
                                           key=list(dirs).count)
            if len(set(dirs)) > 1:
                assert agg["tier"] == "C"
            else:
                assert agg["tier"] == sorted(tiers)[1]

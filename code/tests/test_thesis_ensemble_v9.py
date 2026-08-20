"""thesis-judges-v9 U1 RED: 2-seat heterogeneous ensemble (opus + fable).

Spec rule (specs/thesis-judges-v9.md, signed off 2026-07-15): direction
unanimous -> WORSE of the two tiers; 1-1 direction split -> tier C with the
FABLE seat's lean recorded (forced-lean invariant,
thesis-verdict-ledger.md:115-116). Exactly one opus seat + one fable seat,
identified by a required `seat` field, never by array order. `aggregate`
era-dispatches on judge count: 2 -> v9, 3 -> frozen v8 rule, else raises.
"""

import itertools

import pytest

from kairos.thesis import ensemble


def _judge(seat, tier, direction):
    return {"seat": seat, "tier": tier, "direction": direction,
            "rationale": "r", "decisive_citations": ["F1"],
            "adversary_adjudication": []}


def test_unanimous_direction_takes_worse_tier():
    agg = ensemble.aggregate_v9([_judge("opus", "A", "long"),
                                 _judge("fable", "B", "long")])
    assert agg["tier"] == "B"  # worse of A,B — hand-picked, B is nearer C
    assert agg["direction"] == "long"


def test_unanimous_same_tier_stands():
    agg = ensemble.aggregate_v9([_judge("opus", "B", "short"),
                                 _judge("fable", "B", "short")])
    assert agg["tier"] == "B"
    assert agg["direction"] == "short"


def test_split_forces_c_with_fable_lean():
    agg = ensemble.aggregate_v9([_judge("opus", "A", "long"),
                                 _judge("fable", "B", "short")])
    assert agg["tier"] == "C"
    assert agg["direction"] == "short"  # fable's lean, not opus's


def test_split_fable_lean_is_seat_keyed_not_order_keyed():
    judges = [_judge("fable", "B", "long"), _judge("opus", "C", "short")]
    agg = ensemble.aggregate_v9(judges)
    assert agg["tier"] == "C"
    assert agg["direction"] == "long"  # fable listed FIRST still wins the lean


def test_seat_order_never_changes_unanimous_result():
    a = ensemble.aggregate_v9([_judge("opus", "A", "long"),
                               _judge("fable", "C", "long")])
    b = ensemble.aggregate_v9([_judge("fable", "C", "long"),
                               _judge("opus", "A", "long")])
    assert a["tier"] == b["tier"] == "C"
    assert a["direction"] == b["direction"] == "long"


def test_aggregate_carries_both_judge_payloads():
    judges = [_judge("opus", "B", "long"), _judge("fable", "B", "long")]
    agg = ensemble.aggregate_v9(judges)
    assert agg["judges"] == judges


def test_v9_wrong_count_raises():
    for judges in ([_judge("opus", "B", "long")],
                   [_judge("opus", "B", "long"), _judge("fable", "B", "long"),
                    _judge("opus", "B", "long")]):
        with pytest.raises(ensemble.EnsembleError):
            ensemble.aggregate_v9(judges)


def test_duplicate_seat_raises():
    with pytest.raises(ensemble.EnsembleError):
        ensemble.aggregate_v9([_judge("opus", "B", "long"),
                               _judge("opus", "B", "long")])


def test_missing_seat_field_raises():
    seatless = {"tier": "B", "direction": "long"}
    with pytest.raises(ensemble.EnsembleError):
        ensemble.aggregate_v9([seatless, _judge("fable", "B", "long")])


def test_v9_malformed_tier_raises():
    with pytest.raises(ensemble.EnsembleError):
        ensemble.aggregate_v9([_judge("opus", "D", "long"),
                               _judge("fable", "B", "long")])


def test_v9_malformed_direction_raises():
    with pytest.raises(ensemble.EnsembleError):
        ensemble.aggregate_v9([_judge("opus", "B", "flat"),
                               _judge("fable", "B", "long")])


def test_exhaustive_invariants_over_all_36_seat_pairs():
    """36-pair sweep (3 tiers x 3 tiers x 2 dirs x 2 dirs): split always ->
    C + fable lean; unanimous -> worse tier by ordinal (A best, C worst)."""
    for ot, ft, od, fd in itertools.product("ABC", "ABC",
                                            ("long", "short"),
                                            ("long", "short")):
        agg = ensemble.aggregate_v9([_judge("opus", ot, od),
                                     _judge("fable", ft, fd)])
        if od != fd:
            assert agg["tier"] == "C"
            assert agg["direction"] == fd  # fable lean on every split
        else:
            assert agg["direction"] == od
            assert agg["tier"] == max(ot, ft)  # 'C' > 'B' > 'A' lexically


def test_dispatcher_routes_two_seated_judges_to_v9():
    judges = [_judge("opus", "A", "long"), _judge("fable", "B", "long")]
    assert ensemble.aggregate(judges) == ensemble.aggregate_v9(judges)


def test_dispatcher_still_routes_three_to_frozen_v8():
    v8 = [{"tier": t, "direction": "long"} for t in ("A", "B", "C")]
    agg = ensemble.aggregate(v8)
    assert agg["tier"] == "B"  # v8 median rule untouched
    assert agg["direction"] == "long"


def test_dispatcher_rejects_other_counts():
    with pytest.raises(ensemble.EnsembleError):
        ensemble.aggregate([_judge("opus", "B", "long")] * 4)

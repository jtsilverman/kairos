"""Judge-ensemble aggregation, era-dispatched on judge count.

v9 (thesis-judges-v9, 2026-07-15): 2 heterogeneous seats (opus + fable,
seat-keyed, never order-keyed). Direction unanimous -> the WORSE of the two
tiers stands; a 1-1 direction split is a C no-trade with the FABLE seat's
lean recorded (forced-lean invariant, thesis-verdict-ledger.md).

v8/v7 (frozen): 3 same-model seats, unanimous direction -> median tier, any
2-1 split -> C with the majority direction. Kept as the scoring instrument
of the 76 memos of record; the era-partitioned rebuild and their contract
re-checks still consume it. NOT dead code.

Judge payloads are untrusted agent output: wrong count, wrong seats, or
malformed enum raises, nothing is coerced.
"""

from __future__ import annotations

_TIERS = ("A", "B", "C")
_DIRECTIONS = ("long", "short")
_SEATS = ("opus", "fable")


class EnsembleError(Exception):
    """Judge payloads unusable for aggregation; nothing is recorded."""


def _check_enums(judges: list[dict]) -> None:
    for j in judges:
        if j.get("tier") not in _TIERS:
            raise EnsembleError(f"malformed tier: {j.get('tier')!r}")
        if j.get("direction") not in _DIRECTIONS:
            raise EnsembleError(f"malformed direction: {j.get('direction')!r}")


def aggregate(judges: list[dict]) -> dict:
    """Era dispatch: the judge count IS the era marker (2 -> v9, 3 -> v8)."""
    if len(judges) == 2:
        return aggregate_v9(judges)
    if len(judges) == 3:
        return _aggregate_v8(judges)
    raise EnsembleError(f"need 2 (v9) or 3 (v8) judge payloads, got {len(judges)}")


def aggregate_v9(judges: list[dict]) -> dict:
    if len(judges) != 2:
        raise EnsembleError(f"v9 needs exactly 2 judge payloads, got {len(judges)}")
    if sorted(j.get("seat") for j in judges if j.get("seat")) != sorted(_SEATS):
        raise EnsembleError(
            f"v9 needs one seat each of {_SEATS}, got "
            f"{[j.get('seat') for j in judges]}")
    _check_enums(judges)

    by_seat = {j["seat"]: j for j in judges}
    if by_seat["opus"]["direction"] != by_seat["fable"]["direction"]:
        return {"tier": "C", "direction": by_seat["fable"]["direction"],
                "judges": judges}

    worse_tier = max(j["tier"] for j in judges)  # 'C' > 'B' > 'A' lexically
    return {"tier": worse_tier, "direction": by_seat["opus"]["direction"],
            "judges": judges}


def aggregate_v16(judges: list[dict]) -> dict:
    """thesis-scale-v16: two p_outperform seats -> one aggregate p;
    direction/tier DERIVED from it (agents never state letters). Same side
    of 0.5 -> the value nearer 0.5 (worse-of-two analog; same-side
    equidistant = identical values, no tiebreak needed). Opposite sides ->
    the panel disagrees on direction, so the verdict can NEVER be
    actionable: the fable seat's value clamped just inside the no-action
    zone (carries v9's split->C+fable-lean forward). Never routes through
    _check_enums -- v16 payloads carry no tier/direction to check."""
    # memo owns the threshold/clamp knobs (one home); memo imports this
    # module at top level, so the import is deferred to call time
    from kairos.thesis import memo

    if len(judges) != 2:
        raise EnsembleError(
            f"v16 needs exactly 2 judge payloads, got {len(judges)}")
    if sorted(j.get("seat") for j in judges if j.get("seat")) != sorted(_SEATS):
        raise EnsembleError(
            f"v16 needs one seat each of {_SEATS}, got "
            f"{[j.get('seat') for j in judges]}")
    by_seat = {}
    for j in judges:
        if "p_outperform" not in j:
            raise EnsembleError(f"seat {j.get('seat')}: p_outperform missing")
        by_seat[j["seat"]] = memo._check_p(j["p_outperform"])

    if (by_seat["opus"] > 0.5) == (by_seat["fable"] > 0.5):
        p = min(by_seat.values(), key=lambda v: abs(v - 0.5))
    elif by_seat["fable"] > 0.5:
        p = min(by_seat["fable"], memo.NO_ACTION_CLAMP_LONG)
    else:
        p = max(by_seat["fable"], memo.NO_ACTION_CLAMP_SHORT)

    return {"p_outperform": p, "direction": memo.direction_from_p(p),
            "tier": memo.band_from_p(p), "judges": judges}


def _aggregate_v8(judges: list[dict]) -> dict:
    if len(judges) != 3:
        raise EnsembleError(f"v8 needs exactly 3 judge payloads, got {len(judges)}")
    _check_enums(judges)

    directions = [j["direction"] for j in judges]
    majority = max(_DIRECTIONS, key=directions.count)
    if len(set(directions)) > 1:
        return {"tier": "C", "direction": majority, "judges": judges}

    median_tier = sorted(j["tier"] for j in judges)[1]
    return {"tier": median_tier, "direction": majority, "judges": judges}

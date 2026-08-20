"""Relative strength (thesis-engine unit 1): recency-weighted trailing return,
percentile rank across the ranking field, and the level+rising entry gate.

Pure logic on ordered daily closes -- no provider coupling. The ranking-field
eligibility mask (price/mcap/dollar-volume floors) is the CALLER's job (screen,
unit 3); this module scores and ranks whatever field it is handed. Frozen
numbers per docs/framework-thesis-engine.md: weights 0.4/0.3/0.3 over
63/126/252 sessions, gate level 70, rising vs 21 sessions ago.
"""

from __future__ import annotations

from typing import Optional, Sequence

# Trailing windows (sessions) and their weights, frozen in the framework doc.
_WINDOWS = ((63, 0.4), (126, 0.3), (252, 0.3))
_GATE_LEVEL = 70.0


def rs_raw(closes: Sequence[float]) -> Optional[float]:
    """0.4*r_63d + 0.3*r_126d + 0.3*r_252d off ordered daily closes.

    r_Nd = closes[-1]/closes[-(N+1)] - 1. Returns None on insufficient history
    (< 253 closes): a partial score would rank incomparably against full ones.
    """
    if len(closes) < _WINDOWS[-1][0] + 1:
        return None
    last = closes[-1]
    return sum(w * (last / closes[-(n + 1)] - 1) for n, w in _WINDOWS)


def rs_percentile(scores: dict[str, Optional[float]]) -> dict[str, float]:
    """Percentile rank (0-100) of each scored ticker within the field.

    None scores (insufficient history) are excluded, not ranked as worst --
    a young listing is unknown, not weak. Ties share the lower rank.
    """
    field = {t: s for t, s in scores.items() if s is not None}
    if not field:
        return {}
    if len(field) == 1:
        return {t: 100.0 for t in field}
    ordered = sorted(field.values())
    n = len(ordered)
    return {t: 100.0 * ordered.index(s) / (n - 1) for t, s in field.items()}


def rs_gate(*, current: float, prior: float) -> bool:
    """Entry-gate: RS level >= 70 AND strictly above its value 21 sessions ago."""
    return current >= _GATE_LEVEL and current > prior


def price_legs(closes: Sequence[float]) -> Optional[dict]:
    """The rs_raw score's three price legs, unweighted ({"63d": r_63d, ...}).

    Decomposition input for the dossier's [P1] line (revisions-led vs
    price-led repricing read; the estimate side prints in [R1]). Same
    history floor as rs_raw: None under 253 closes — a partial
    decomposition would misrepresent the score."""
    if len(closes) < _WINDOWS[-1][0] + 1:
        return None
    last = closes[-1]
    return {f"{n}d": last / closes[-(n + 1)] - 1 for n, _ in _WINDOWS}

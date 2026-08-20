"""Story age (dossier-data U1): per-session RS-percentile history over the
trailing window, reproducing the live screen field pipeline
(screen.rs_field_eligible -> rs.rs_raw -> rs.rs_percentile semantics,
screen.py:160-161), and the attainment scan ("sessions since first RS>=90",
docs/winners-study.md:131).

Pure logic on injected session bars — no provider coupling; fetching lives
in the runner (scripts/thesis_dossiers.py). An LLM input, not a gate.
"""

from __future__ import annotations

import statistics
from bisect import bisect_left
from typing import Optional, Sequence

from kairos import screen
from kairos.signals import rs

# Attainment threshold per the winners-study definition ("first RS>=90",
# docs/winners-study.md:131). Numerically equal to the screen's admission
# gate but pinned by the study, not coupled to it.
_ATTAIN = 90.0
# rs.rs_raw needs 253 closes (252 returns + 1); mirrors weekly_screen
# TRADING_DAYS. A ticker with fewer appearances is unknown, not weak.
_RANKABLE = 253
_DVOL_SESSIONS = 20
# The 253 appearances must fit in the trailing _RANK_SPAN sessions —
# build_bars scans TRADING_DAYS+14 = 267 weekdays (~257 sessions after
# holidays), so a name absent ~5+ sessions or trading gappily falls out
# of the live screen's field; without this rule dead names carry forward
# forever (live 2026-07-13: 426 dead names inflated the field 4263 vs
# 3797 and biased survivor percentiles -0.5 to -0.7).
_RANK_SPAN = 257


def percentile_history(
    sessions: Sequence[tuple[str, dict[str, tuple[float, float]]]],
    *,
    targets: set[str],
) -> dict[str, list[tuple[str, Optional[float]]]]:
    """Per-session RS percentile for each target over the evaluation span.

    `sessions`: ordered [(date, {ticker: (close, volume)})], oldest first,
    real sessions only (holidays absent). Evaluation sessions are those at
    index >= _RANKABLE-1 (the first where any ticker can have 253
    appearances). Per session the field is built exactly like the live
    screen: rs_field_eligible mask on (last close, median of last-20
    dollar-vols), rs_raw over the ticker's own last 253 appearances, scores
    carried forward for tickers not trading that day. Percentile mirrors
    rs.rs_percentile semantics (ties share the lower rank, None excluded,
    single-member field ranks 100.0) via bisect_left on the sorted field —
    the equality is pinned by test against rs.rs_percentile itself.

    A target absent from a session's field (ineligible or unrankable) gets
    None for that session — omit, never fake.
    """
    closes: dict[str, list[float]] = {}
    dvols: dict[str, list[float]] = {}
    appear_idx: dict[str, list[int]] = {}  # rolling, aligned with `closes`
    # ticker -> (score, eligible, window_open_idx): updated on each
    # appearance, carried across sessions the ticker does not trade;
    # window_open_idx (the 253rd-most-recent appearance) ages the entry
    # out of the field once it no longer fits the trailing _RANK_SPAN.
    state: dict[str, tuple[Optional[float], bool, int]] = {}
    out: dict[str, list[tuple[str, Optional[float]]]] = {t: [] for t in targets}

    for idx, (date, bars) in enumerate(sessions):
        for t, (close, volume) in bars.items():
            c = closes.setdefault(t, [])
            c.append(close)
            ai = appear_idx.setdefault(t, [])
            ai.append(idx)
            # rolling buffers: only the last 253 closes / 20 dvols are ever
            # read, and a full-market span (9.5k tickers x ~1000 sessions)
            # would otherwise hold every close in memory
            if len(c) > _RANKABLE:
                del c[: len(c) - _RANKABLE]
                del ai[: len(ai) - _RANKABLE]
            dv = dvols.setdefault(t, [])
            dv.append(close * volume)
            if len(dv) > _DVOL_SESSIONS:
                del dv[: len(dv) - _DVOL_SESSIONS]
            if len(c) < _RANKABLE:
                continue
            score = rs.rs_raw(c[-_RANKABLE:])
            eligible = screen.rs_field_eligible(screen.BarsSummary(
                price=close,
                dollar_vol_20d_median=statistics.median(dv),
                closes=(),
            ))
            state[t] = (score, eligible, ai[0])
        if idx < _RANKABLE - 1:
            continue
        span_open = idx - (_RANK_SPAN - 1)
        field = {t: s for t, (s, ok, w0) in state.items()
                 if ok and s is not None and w0 >= span_open}
        ordered = sorted(field.values())
        n = len(ordered)
        for t in targets:
            s = field.get(t)
            if s is None:
                out[t].append((date, None))
            elif n == 1:
                out[t].append((date, 100.0))
            else:
                out[t].append((date, 100.0 * bisect_left(ordered, s) / (n - 1)))
    return out


def scan(history: Sequence[tuple[str, Optional[float]]]) -> Optional[dict]:
    """Sessions since first RS>=90 attainment within `history` (ordered,
    oldest first). None when never attained in the window (including
    never-rankable). Attainment at the window's first session is
    left-censored: the true first attainment may predate the window, so
    the age is a lower bound. Ages count from first rankability — a None
    prefix (young listing) is not censoring."""
    attained = next((i for i, (_, p) in enumerate(history)
                     if p is not None and p >= _ATTAIN), None)
    if attained is None:
        return None
    return {"sessions": len(history) - 1 - attained,
            "left_censored": attained == 0,
            "window_sessions": len(history)}

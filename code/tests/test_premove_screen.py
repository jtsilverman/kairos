"""premove-cohort U1 RED: the t-21 rising-percentile snapshot.

Cohort 2 admits RS percentile [70, 90) RISING — today's percentile above the
name's own percentile 21 sessions ago, both against the $5/$5M field
discipline evaluated WITH t-21 data (spec U1 inline decision). Expected
values hand-set, never recomputed through the functions under test.
"""

from __future__ import annotations

import importlib.util
import statistics
from pathlib import Path

from kairos import screen

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "weekly_screen.py"
_spec = importlib.util.spec_from_file_location("weekly_screen", _SCRIPT)
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)


def _linear(n: int, start: float, end: float) -> list[float]:
    step = (end - start) / (n - 1)
    return [start + i * step for i in range(n)]


def _bars(closes, *, dvol=40_000_000.0, dvol_prior=10_000_000.0):
    return screen.BarsSummary(
        price=closes[-1],
        dollar_vol_20d_median=dvol,
        closes=closes,
        highs=closes,
        lows=closes,
        dollar_vol_20d_median_prior=dvol_prior,
    )


# --- band predicate: [70, 90) half-open ---

def test_premove_band_half_open_boundaries():
    assert screen.premove_band(69.99) is False
    assert screen.premove_band(70.0) is True
    assert screen.premove_band(89.99) is True
    assert screen.premove_band(90.0) is False


# --- rising: strict, prior-None never rising ---

def test_premove_rising_strict_and_prior_none():
    assert screen.premove_rising(current=85.0, prior=78.0) is True
    assert screen.premove_rising(current=85.0, prior=87.0) is False
    assert screen.premove_rising(current=85.0, prior=85.0) is False
    assert screen.premove_rising(current=85.0, prior=None) is False


# --- prior field percentiles: t-21 snapshot with t-21-consistent eligibility ---

def _abc_field():
    # prior-window (first 253 closes) shapes: A flat (rs_raw 0), B rising
    # (positive), C falling (negative); the last 21 closes are noise the
    # prior snapshot must ignore.
    a = [10.0] * 253 + [10.0] * 21
    b = _linear(253, 10.0, 20.0) + [20.0] * 21
    c = _linear(253, 20.0, 10.0) + [10.0] * 21
    return {"A": _bars(a), "B": _bars(b), "C": _bars(c)}


def test_prior_field_percentiles_rank_the_t21_snapshot():
    pct = screen.prior_field_percentiles(_abc_field())
    assert pct == {"C": 0.0, "A": 50.0, "B": 100.0}


def test_prior_field_excludes_price_ineligible_at_t21():
    field = _abc_field()
    # $4 at t-21 (every prior close), $6 today: current-field member,
    # prior-field non-member
    d = [4.0] * 253 + [6.0] * 21
    field["D"] = _bars(d)
    pct = screen.prior_field_percentiles(field)
    assert "D" not in pct
    assert set(pct) == {"A", "B", "C"}


def test_prior_field_excludes_short_history():
    field = _abc_field()
    # 260 closes: rankable today (>= 253) but only 239 at t-21
    field["E"] = _bars([10.0] * 260)
    pct = screen.prior_field_percentiles(field)
    assert "E" not in pct


def test_prior_field_requires_prior_dvol():
    field = _abc_field()
    field["F"] = _bars([10.0] * 274, dvol_prior=None)
    field["G"] = _bars([10.0] * 274, dvol_prior=4_000_000.0)
    pct = screen.prior_field_percentiles(field)
    assert "F" not in pct
    assert "G" not in pct


# --- U2: the cohort-2 admission funnel ---
#
# Exact-control fixture: a flat-10.0 series where ONLY closes[-1] and
# closes[-22] are bumped gives hand-exact rs_raw for both windows
# independently — every current-window lookback (closes[-64]/[-127]/[-253])
# reads 10.0, so current rs_raw = x exactly; the prior window's last close
# is closes[-22], so prior rs_raw = y exactly. Percentiles then follow from
# RANK alone: 11 names at x = .01*(i+1) sit at exactly 0,10,...,100.

def _ctrl(x: float, y: float):
    """closes with current rs_raw == x and prior rs_raw == y, exactly."""
    closes = [10.0] * 274
    closes[-22] = 10.0 * (1.0 + y)
    closes[-1] = 10.0 * (1.0 + x)
    return _bars(closes)


def _funnel_field():
    """T0..T10 ascending current scores -> current percentile of Ti is
    exactly 10*i. Prior scores identical EXCEPT T7/T8 swapped: T8 prior
    percentile 70 < current 80 (rising, in band); T7 prior 80 > current 70
    (falling, in band); T9 at 90.0 and T10 at 100 are cohort-1 territory."""
    x = {i: 0.01 * (i + 1) for i in range(11)}
    y = dict(x)
    y[7], y[8] = x[8], x[7]
    return {f"T{i}": _ctrl(x[i], y[i]) for i in range(11)}


def _snap(*, net_up=3, delta=0.05, positive=True):
    from kairos.data.estimates import RevisionSnapshot
    return RevisionSnapshot(net_up_30d=net_up, trend_delta_90d=delta,
                            positive=positive)


def _profile_ok(t):
    return screen.Profile(market_cap=1_000_000_000.0, industry="semis")


def _fundamentals_ok(t):
    return screen.Fundamentals(
        revenue=[("2024-12-31", 100.0), ("2025-12-31", 120.0)],
        receivables=[("2024-12-31", 10.0), ("2025-12-31", 11.0)],
        net_income=[("2024-12-31", 5.0), ("2025-12-31", 8.0)],
        operating_cash_flow=[("2024-12-31", 9.0), ("2025-12-31", 12.0)],
        shares=[("2024-12-31", 50.0), ("2025-12-31", 50.0)],
    )


def _run_premove(field, *, revisions_fetch=None, net_up_floor=0):
    return screen.run_premove_screen(
        field,
        profile_fetch=_profile_ok,
        fundamentals_fetch=_fundamentals_ok,
        revisions_fetch=revisions_fetch or (lambda t: _snap()),
        net_up_floor=net_up_floor,
    )


def test_premove_funnel_band_splits_cohorts():
    """Same field, same fetches, disjoint admissions: T10 (pct 100) and T9
    (pct 90.0) are cohort-1 survivors and NOT cohort-2; T8 (pct 80, rising
    from 70) is cohort-2 and NOT cohort-1."""
    field = _funnel_field()
    premove = _run_premove(field)
    cohort1 = screen.run_screen(
        field, profile_fetch=_profile_ok, fundamentals_fetch=_fundamentals_ok)

    c1 = {c.ticker for c in cohort1.survivors}
    c2 = {c.ticker for c in premove.survivors}
    assert "T10" in c1 and "T9" in c1
    assert c2 == {"T8"}
    assert c1 & c2 == set()


def test_premove_funnel_counts_not_rising_and_prior_unrankable():
    field = _funnel_field()
    # T6: steady (prior pct == current pct 60... in band? 60 -> below band).
    # T7 is the in-band falling name (prior 80 > current 70).
    r = _run_premove(field)
    assert r.exclusions.get("T7") == "rs_not_rising"
    assert "T7" not in {c.ticker for c in r.survivors}

    # prior-unrankable: T8 truncated to 260 closes (rankable today, 239 at
    # t-21); current percentile unchanged (rank-based, all lookbacks flat)
    field2 = _funnel_field()
    t8 = field2["T8"]
    field2["T8"] = screen.BarsSummary(
        price=t8.price, dollar_vol_20d_median=t8.dollar_vol_20d_median,
        closes=list(t8.closes)[-260:],
        dollar_vol_20d_median_prior=t8.dollar_vol_20d_median_prior)
    r2 = _run_premove(field2)
    assert r2.exclusions.get("T8") == "rs_prior_unrankable"


def test_premove_funnel_revisions_gate_reads_positive_by_call():
    """The gate consults RevisionSnapshot.positive, never a re-derived
    formula: a snapshot whose numeric fields contradict its positive flag
    is admitted iff the flag says so."""
    field = _funnel_field()
    contradictory = _snap(net_up=-5, delta=-1.0, positive=True)
    r = _run_premove(field, revisions_fetch=lambda t: contradictory,
                     net_up_floor=-999)
    assert "T8" in {c.ticker for c in r.survivors}

    negative = _snap(net_up=5, delta=1.0, positive=False)
    r2 = _run_premove(field, revisions_fetch=lambda t: negative)
    assert r2.exclusions.get("T8") == "revisions_negative"


def test_premove_funnel_missing_revisions_is_counted_exclusion():
    from kairos.data.estimates import MissingEstimatesError

    def raising(t):
        raise MissingEstimatesError(t)

    r = _run_premove(_funnel_field(), revisions_fetch=raising)
    assert r.exclusions.get("T8") == "revisions_missing"


def test_premove_funnel_net_up_floor_knob():
    r = _run_premove(_funnel_field(),
                     revisions_fetch=lambda t: _snap(net_up=1),
                     net_up_floor=2)
    assert r.exclusions.get("T8") == "revisions_below_floor"
    r2 = _run_premove(_funnel_field(),
                      revisions_fetch=lambda t: _snap(net_up=2),
                      net_up_floor=2)
    assert "T8" in {c.ticker for c in r2.survivors}


def test_premove_funnel_fetch_stage_gates_still_apply():
    def small_cap(t):
        return screen.Profile(market_cap=100_000_000.0, industry="semis")

    r = screen.run_premove_screen(
        _funnel_field(), profile_fetch=small_cap,
        fundamentals_fetch=_fundamentals_ok,
        revisions_fetch=lambda t: _snap())
    assert r.exclusions.get("T8") == "mcap_floor"


# --- U3: cohort flag, subdir output, glob isolation ---

_PT_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pull_transcripts.py"
_pt_spec = importlib.util.spec_from_file_location("pull_transcripts", _PT_SCRIPT)
pt = importlib.util.module_from_spec(_pt_spec)
_pt_spec.loader.exec_module(pt)


def test_latest_screen_glob_ignores_premove_subdir(monkeypatch, tmp_path):
    """pull_transcripts --auto resolves the lexicographic-last cohort-1 file;
    a NEWER premove file in the subdir must never hijack it."""
    (tmp_path / "data" / "screen" / "premove").mkdir(parents=True)
    (tmp_path / "data" / "screen" / "2026-07-10.json").write_text("{}")
    (tmp_path / "data" / "screen" / "premove" / "2026-07-17.json").write_text("{}")
    monkeypatch.setattr(pt, "_ROOT", tmp_path)
    assert pt._latest_screen() == tmp_path / "data" / "screen" / "2026-07-10.json"


def _one_survivor_result():
    field = _funnel_field()
    r = _run_premove(field)
    return r, field


def test_payload_premove_carries_cohort_tag():
    import datetime as dt
    r, field = _one_survivor_result()
    p = ws.payload(dt.date(2026, 7, 17), r, field, cohort="premove")
    assert p["cohort"] == "premove"
    s = p["survivors"][0]
    # cohort-1 survivor shape preserved: same keys, technicals included
    assert set(s) == {"ticker", "rs", "forensics", "price", "technicals"}


def test_payload_default_has_no_cohort_key():
    """Byte-compat: the cohort-1 payload must not gain a cohort key."""
    import datetime as dt
    r, field = _one_survivor_result()
    p = ws.payload(dt.date(2026, 7, 17), r, field)
    assert "cohort" not in p
    assert set(p) == {"as_of", "survivors", "exclusions"}


def test_premove_default_output_path():
    import datetime as dt
    assert ws.default_json_path(dt.date(2026, 7, 17), "premove") == Path(
        "data/screen/premove/2026-07-17.json")
    assert ws.default_json_path(dt.date(2026, 7, 17), None) is None


# --- build_bars: window extended to 253+21, prior dvol median computed ---

def _fake_sessions(n_sessions: int, ticker: str = "T", *, base_vol: float = 1e6):
    """One GroupedBar per session; close ramps 1..n so window trims are
    detectable by value, volume constant so dollar-vol tracks close."""
    from kairos.data.polygon import GroupedBar

    days: list[list[GroupedBar]] = []
    for i in range(n_sessions):
        c = float(i + 1)
        days.append([GroupedBar(ticker=ticker, open=c, high=c, low=c,
                                close=c, volume=base_vol)])
    return days


def test_build_bars_keeps_274_closes_and_prior_dvol(monkeypatch):
    import datetime as dt

    days = _fake_sessions(300)
    calls = iter(days[-(ws.TRADING_DAYS + 21 + 16):])
    monkeypatch.setattr(ws, "fetch_grouped_daily", lambda day: next(calls))
    out = ws.build_bars(dt.date(2026, 7, 10))
    b = out["T"]
    assert len(b.closes) == 274
    # last fetched close is session 300 -> close 300.0
    assert b.closes[-1] == 300.0
    # prior 20d dvol median: sessions -41..-22 (closes 260..279) * base_vol
    expected_prior = statistics.median(
        [c * 1e6 for c in range(260, 280)])
    assert b.dollar_vol_20d_median_prior == expected_prior
    # current 20d dvol median unchanged in meaning: sessions -20..-1
    assert b.dollar_vol_20d_median == statistics.median(
        [c * 1e6 for c in range(281, 301)])


def test_build_bars_field_membership_is_old_window_relative(monkeypatch):
    """The extended fetch window must NOT change field membership: a name is
    rankable iff it has >= TRADING_DAYS closes within the ORIGINAL
    TRADING_DAYS+14 candidate suffix. A stale name with 271 total closes but
    only 248 inside that suffix was excluded by the 267-day window and must
    stay excluded (else every percentile drifts vs the cohort-1 baseline)."""
    import datetime as dt

    n_window = ws.TRADING_DAYS + 21 + 16  # 290
    days = _fake_sessions(n_window)
    # trades sessions 0..270, delisted after: 271 closes total, but the old
    # 267-candidate suffix starts at session 23 -> 248 closes inside it
    for d in days[271:]:
        d.clear()
    calls = iter(days)
    monkeypatch.setattr(ws, "fetch_grouped_daily", lambda day: next(calls))
    out = ws.build_bars(dt.date(2026, 7, 10))
    assert "T" not in out


def test_build_bars_keeps_a_260_close_name(monkeypatch):
    """Cohort-1 IPO rule unchanged: >= 253 closes stays in, even when the
    name cannot fill the extended 274 window."""
    import datetime as dt

    n_window = ws.TRADING_DAYS + 21 + 16
    days = _fake_sessions(n_window)
    # name absent for the first (n_window - 260) sessions: 260 appearances
    for d in days[: n_window - 260]:
        d.clear()
    calls = iter(days)
    monkeypatch.setattr(ws, "fetch_grouped_daily", lambda day: next(calls))
    out = ws.build_bars(dt.date(2026, 7, 10))
    assert "T" in out
    assert len(out["T"].closes) == 260

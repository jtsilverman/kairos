"""dossier-data U2 RED: P/S percentile vs own history — vintage-consistent
(operand fiscal-end + 90d filing lag <= bar date), PIT (a bar past as_of
raises), None under 1yr of computable points. The two RED cases that ARE
the watch-item de-risk: the vintage trap and the poisoned as_of.
"""

from __future__ import annotations

import pytest

from kairos.thesis import dossier


def _dates(n, start="2023-01-01"):
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    out, d = [], d0
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def test_ps_percentile_hand_computed_mid_case():
    # constant revenue/shares vintage -> P/S proportional to close.
    # closes 1..299 then today 150.5: exactly 150 points below today in the
    # 300-point distribution -> bisect_left convention = 100*150/299.
    dates = _dates(300)
    closes = list(zip(dates, [float(i) for i in range(1, 300)] + [150.5]))
    out = dossier.ps_history_percentile(
        closes=closes,
        shares_series=[("2022-06-30", 1_000.0)],
        revenue_series=[("2022-06-30", 10_000.0)],
        as_of=dates[-1],
    )
    assert out["percentile"] == 100.0 * 150 / 299
    assert out["window_sessions"] == 300
    assert out["today_ps"] == 150.5 * 1_000.0 / 10_000.0


def test_ps_percentile_uses_prior_vintage_inside_filing_lag():
    # Revenue doubles at FY2025-12-31, but as_of sits 30d after fiscal end —
    # inside the 90d filing lag, so today's P/S must price off the PRIOR
    # vintage (rev 100_000 -> P/S 100.0), never the unfiled new year
    # (which would read 50.0).
    dates = _dates(300, start="2025-01-02")  # runs into 2026 past 2025-12-31
    closes = list(zip(dates, [10.0] * 300))
    out = dossier.ps_history_percentile(
        closes=closes,
        shares_series=[("2023-12-31", 1_000_000.0)],
        revenue_series=[("2023-12-31", 100_000.0), ("2025-12-31", 200_000.0)],
        as_of=dates[-1],
    )
    assert out["today_ps"] == 10.0 * 1_000_000.0 / 100_000.0


def test_ps_percentile_raises_on_bar_past_as_of():
    dates = _dates(300)
    closes = list(zip(dates, [10.0] * 300))
    with pytest.raises(ValueError):
        dossier.ps_history_percentile(
            closes=closes,
            shares_series=[("2022-06-30", 1_000.0)],
            revenue_series=[("2022-06-30", 10_000.0)],
            as_of=dates[-2],  # the final bar postdates as_of -> fail loud
        )


def test_ps_percentile_none_under_one_year_of_computable_points():
    # 251 computable points -> None; 252 -> a real result (the 1yr floor).
    for n, expect_none in ((251, True), (252, False)):
        dates = _dates(n)
        closes = list(zip(dates, [10.0] * n))
        out = dossier.ps_history_percentile(
            closes=closes,
            shares_series=[("2022-06-30", 1_000.0)],
            revenue_series=[("2022-06-30", 10_000.0)],
            as_of=dates[-1],
        )
        assert (out is None) is expect_none


def test_ps_percentile_skips_uncomputable_early_points():
    # First vintage becomes usable (fiscal_end + 90d) mid-window: bars
    # before that are skipped, and with fewer than 252 computable points
    # left the result is None — omitted, never a fake percentile over a
    # partial distribution.
    dates = _dates(300)
    closes = list(zip(dates, [10.0] * 300))
    # usable only ~60 sessions before the end of the window
    late = dates[240]
    import datetime as dt
    fiscal_end = (dt.date.fromisoformat(late) - dt.timedelta(days=90)).isoformat()
    out = dossier.ps_history_percentile(
        closes=closes,
        shares_series=[(fiscal_end, 1_000.0)],
        revenue_series=[(fiscal_end, 10_000.0)],
        as_of=dates[-1],
    )
    assert out is None


def test_ps_percentile_ties_share_lower_rank():
    # 100 points at P/S 0.5, 200 at 1.0 (today ties the 1.0 block):
    # bisect_left convention -> exactly the 100 strictly-below points count.
    dates = _dates(300)
    closes = list(zip(dates, [5.0] * 100 + [10.0] * 200))
    out = dossier.ps_history_percentile(
        closes=closes,
        shares_series=[("2022-06-30", 1_000.0)],
        revenue_series=[("2022-06-30", 10_000.0)],
        as_of=dates[-1],
    )
    assert out["percentile"] == 100.0 * 100 / 299

"""thesis-engine unit 2 RED: screen-input data wrappers.

edgar: companyfacts JSON -> annual fact series with revenue tag fallback,
fail-loud when no tag matches. estimates: yfinance frames -> revision
snapshot, fail-loud on empty/missing frames. Network edges injected; fixture
shapes copied from real live probes (ZETA 2026-07-08), values hand-set.
"""

from __future__ import annotations

import pandas as pd
import pytest

from kairos.data import edgar, estimates


def _facts(gaap: dict, dei: dict | None = None) -> dict:
    return {"cik": 1851003, "entityName": "TEST CORP",
            "facts": {"us-gaap": gaap, "dei": dei or {}}}


def _tag(unit: str, rows: list[dict]) -> dict:
    return {"units": {unit: rows}}


def _fy(end: str, val: float) -> dict:
    return {"end": end, "val": val, "form": "10-K", "fp": "FY"}


def test_annual_series_uses_asc606_revenue_fallback():
    facts = _facts({
        "RevenueFromContractWithCustomerExcludingAssessedTax": _tag("USD", [
            _fy("2024-12-31", 900.0), _fy("2025-12-31", 1300.0),
        ]),
    })
    series = edgar.annual_series(facts, edgar.REVENUE_TAGS)
    assert series == [("2024-12-31", 900.0), ("2025-12-31", 1300.0)]


def test_annual_series_prefers_tag_with_most_recent_annual_row():
    # tag-migration case (live: MGNI/Rubicon filed "Revenues" pre-2020, ASC-606
    # after): the stale first-listed tag must lose to the currently-filed one
    facts = _facts({
        "Revenues": _tag("USD", [_fy("2019-12-31", 48.0)]),
        "RevenueFromContractWithCustomerExcludingAssessedTax": _tag("USD", [
            _fy("2024-12-31", 668.0), _fy("2025-12-31", 730.0),
        ]),
    })
    assert edgar.annual_series(facts, edgar.REVENUE_TAGS) == [
        ("2024-12-31", 668.0), ("2025-12-31", 730.0),
    ]


def test_net_income_tags_survive_filer_migration_off_netincomeloss():
    # live: CAT stopped tagging NetIncomeLoss after FY2010; recent years live
    # under NetIncomeLossAvailableToCommonStockholdersBasic (probed
    # 2026-07-11). A single-tag tuple silently returns the 2010 series and
    # the dossier's [Q1] net_margin computes 2010 NI over current revenue.
    facts = _facts({
        "NetIncomeLoss": _tag("USD", [
            _fy("2009-12-31", 895.0), _fy("2010-12-31", 2700.0),
        ]),
        "NetIncomeLossAvailableToCommonStockholdersBasic": _tag("USD", [
            _fy("2024-12-31", 10792.0), _fy("2025-12-31", 10635.0),
        ]),
    })
    assert edgar.annual_series(facts, edgar.NET_INCOME_TAGS) == [
        ("2024-12-31", 10792.0), ("2025-12-31", 10635.0),
    ]


def test_net_income_tags_prefer_common_attributable_over_profitloss_on_tie():
    # ProfitLoss includes noncontrolling interests; when both are currently
    # filed (same latest FY), attributable-to-common must win the tie
    facts = _facts({
        "ProfitLoss": _tag("USD", [_fy("2025-12-31", 11000.0)]),
        "NetIncomeLossAvailableToCommonStockholdersBasic": _tag("USD", [
            _fy("2025-12-31", 10635.0),
        ]),
    })
    assert edgar.annual_series(facts, edgar.NET_INCOME_TAGS) == [
        ("2025-12-31", 10635.0),
    ]


def test_annual_series_raises_when_no_tag_matches():
    with pytest.raises(edgar.MissingFactError):
        edgar.annual_series(_facts({}), edgar.REVENUE_TAGS)


def test_annual_series_excludes_quarterly_rows():
    facts = _facts({
        "NetIncomeLoss": _tag("USD", [
            {"end": "2025-09-30", "val": 10.0, "form": "10-Q", "fp": "Q3"},
            _fy("2025-12-31", -31.5),
        ]),
    })
    assert edgar.annual_series(facts, ("NetIncomeLoss",)) == [("2025-12-31", -31.5)]


def test_annual_series_excludes_quarter_duration_rows_inside_10k():
    # live: DELL's 10-K carries quarter-period revenue rows tagged form=10-K
    # fp=FY (end 2024-11-01, $24.4B ~ one quarter); form/fp alone admitted them
    # and _growth read quarter-vs-year = +374%. Duration must be ~annual.
    facts = _facts({
        "Revenues": _tag("USD", [
            {"start": "2024-08-03", "end": "2024-11-01", "val": 24.4,
             "form": "10-K", "fp": "FY"},
            {"start": "2024-02-03", "end": "2025-01-31", "val": 95.6,
             "form": "10-K", "fp": "FY"},
            {"start": "2025-02-01", "end": "2026-01-30", "val": 113.5,
             "form": "10-K", "fp": "FY"},
        ]),
    })
    assert edgar.annual_series(facts, ("Revenues",)) == [
        ("2025-01-31", 95.6), ("2026-01-30", 113.5),
    ]


def test_annual_series_keeps_instant_concepts_without_start():
    # instant concepts (shares outstanding) have no "start"; duration filter
    # must not drop them
    facts = _facts({
        "CommonStockSharesOutstanding": _tag("shares", [
            _fy("2024-12-31", 100.0), _fy("2025-12-31", 106.0),
        ]),
    })
    assert edgar.annual_series(facts, ("CommonStockSharesOutstanding",)) == [
        ("2024-12-31", 100.0), ("2025-12-31", 106.0),
    ]


def _trend_frame(rows: dict[str, list[float]]) -> pd.DataFrame:
    # index periods 0q/+1q/0y/+1y, columns current/7daysAgo/30daysAgo/60daysAgo/90daysAgo
    cols = ["current", "7daysAgo", "30daysAgo", "60daysAgo", "90daysAgo"]
    return pd.DataFrame.from_dict(rows, orient="index", columns=cols)


def _rev_frame(rows: dict[str, list[int]]) -> pd.DataFrame:
    cols = ["upLast7days", "upLast30days", "downLast30days", "downLast7Days"]
    return pd.DataFrame.from_dict(rows, orient="index", columns=cols)


def test_revision_snapshot_breadth_and_magnitude():
    trend = _trend_frame({"0y": [1.10, 1.09, 1.05, 1.02, 1.00]})
    rev = _rev_frame({"0y": [2, 5, 1, 0]})
    snap = estimates.revision_snapshot_from_frames(trend=trend, revisions=rev)
    assert snap.net_up_30d == 4          # 5 up - 1 down, current year
    assert snap.trend_delta_90d == pytest.approx(0.10)  # 1.10 - 1.00
    assert snap.positive is True


def test_revision_snapshot_negative_when_trend_falling():
    trend = _trend_frame({"0y": [0.93, 0.93, 0.95, 0.96, 0.95]})
    rev = _rev_frame({"0y": [1, 1, 3, 3]})
    snap = estimates.revision_snapshot_from_frames(trend=trend, revisions=rev)
    assert snap.net_up_30d == -2
    assert snap.trend_delta_90d == pytest.approx(-0.02)
    assert snap.positive is False


def test_revision_snapshot_mixed_signals_not_positive():
    # breadth positive but magnitude falling -> not positive (both must agree)
    trend = _trend_frame({"0y": [0.95, 0.95, 0.96, 0.96, 0.97]})
    rev = _rev_frame({"0y": [3, 6, 1, 0]})
    snap = estimates.revision_snapshot_from_frames(trend=trend, revisions=rev)
    assert snap.positive is False


def test_revision_snapshot_raises_on_empty_frames():
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.revision_snapshot_from_frames(
            trend=pd.DataFrame(), revisions=pd.DataFrame()
        )


def test_revision_snapshot_raises_on_missing_current_year_row():
    trend = _trend_frame({"0q": [0.19, 0.19, 0.19, 0.20, 0.20]})  # no 0y row
    rev = _rev_frame({"0q": [1, 1, 1, 1]})
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.revision_snapshot_from_frames(trend=trend, revisions=rev)


def test_profile_from_info_extracts_and_fails_loud():
    info = {"marketCap": 5_000_000_000, "industry": "Packaged Software", "x": 1}
    assert estimates.profile_from_info(info) == {
        "market_cap": 5_000_000_000, "industry": "Packaged Software",
    }
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.profile_from_info({"industry": "Packaged Software"})
    with pytest.raises(estimates.MissingEstimatesError):
        estimates.profile_from_info({"marketCap": None, "industry": "Software"})

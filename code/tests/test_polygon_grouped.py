"""PIT-universe unit 1: fetch_grouped_daily (whole-market OHLCV for one date).

One API call returns every ticker's daily bar -> the cheap survivorship-clean
liquidity primitive (delisted names are present on the day they traded). Mock-DI
tests for mapping + cache; a live smoke (gated) hits the real SDK once because
MagicMock masks a wrong SDK path.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from kairos.data import polygon


@pytest.fixture
def cache_path(tmp_path: Path) -> Path:
    return tmp_path / "polygon-cache.sqlite"


@pytest.fixture
def open_limiter() -> polygon.RateLimiter:
    return polygon.RateLimiter(max_calls=1000, per_seconds=0.001)


def _row(ticker, close, volume, o=None, h=None, low=None):
    return SimpleNamespace(
        ticker=ticker,
        open=o if o is not None else close,
        high=h if h is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=volume,
    )


def test_fetch_grouped_daily_maps_rows(cache_path, open_limiter):
    client = SimpleNamespace(
        get_grouped_daily_aggs=lambda *a, **kw: [
            _row("AAPL", 200.0, 50_000_000),
            _row("NVDA", 120.0, 300_000_000),
        ]
    )
    out = polygon.fetch_grouped_daily(
        "2024-07-01", cache_path=cache_path, client=client, limiter=open_limiter
    )
    by_ticker = {b.ticker: b for b in out}
    assert by_ticker["AAPL"].close == 200.0
    assert by_ticker["AAPL"].volume == 50_000_000.0
    assert by_ticker["NVDA"].close == 120.0
    assert len(out) == 2


def test_fetch_grouped_daily_cache_hit_skips_client(cache_path, open_limiter):
    calls = {"n": 0}

    def _grouped(*a, **kw):
        calls["n"] += 1
        return [_row("AAPL", 200.0, 50_000_000)]

    client = SimpleNamespace(get_grouped_daily_aggs=_grouped)
    kw = dict(cache_path=cache_path, client=client, limiter=open_limiter)
    polygon.fetch_grouped_daily("2024-07-01", **kw)
    polygon.fetch_grouped_daily("2024-07-01", **kw)
    assert calls["n"] == 1  # second served from SQLite cache


@pytest.mark.skipif(
    os.environ.get("KAIROS_LIVE_SMOKE") != "1" or not os.environ.get("POLYGON_API_KEY"),
    reason="live smoke: set KAIROS_LIVE_SMOKE=1 and POLYGON_API_KEY",
)
def test_live_smoke_real_grouped(tmp_path):
    import socket

    socket.setdefaulttimeout(30)
    cp = tmp_path / "live-cache.sqlite"
    lm = polygon.RateLimiter(max_calls=100, per_seconds=1.0)
    bars = polygon.fetch_grouped_daily("2024-07-01", cache_path=cp, limiter=lm)
    assert bars and any(b.ticker == "AAPL" for b in bars)
    aapl = next(b for b in bars if b.ticker == "AAPL")
    assert aapl.close > 0 and aapl.volume > 0


# --- funnel-loop W1 CONTRACT 2: point-in-time ETF classification -----------
#
# The market denominator runs both with and without ETFs. Built from TODAY's
# ETF list it would misclassify a 2025 universe: 4,190 ETFs existed on
# 2025-08-01 against 5,374 today (verified live 2026-08-17), so the as-of date
# is not optional.


def test_fetch_etf_tickers_returns_a_set(cache_path, open_limiter):
    client = SimpleNamespace(
        list_tickers=lambda *a, **kw: [
            SimpleNamespace(ticker="SPY"), SimpleNamespace(ticker="QQQ"),
        ]
    )
    out = polygon.fetch_etf_tickers(
        "2025-08-01", cache_path=cache_path, client=client, limiter=open_limiter
    )
    assert out == {"SPY", "QQQ"}


def test_fetch_etf_tickers_passes_the_as_of_date_through(cache_path, open_limiter):
    """The as-of date must reach the SDK. Without it the call silently returns
    today's ETF list and the point-in-time universe is wrong."""
    seen = {}

    def _list(*a, **kw):
        seen.update(kw)
        return [SimpleNamespace(ticker="SPY")]

    polygon.fetch_etf_tickers(
        "2025-08-01", cache_path=cache_path,
        client=SimpleNamespace(list_tickers=_list), limiter=open_limiter,
    )
    assert seen["date"] == "2025-08-01"
    assert seen["type"] == "ETF"


def test_fetch_etf_tickers_cache_hit_skips_client(cache_path, open_limiter):
    calls = {"n": 0}

    def _list(*a, **kw):
        calls["n"] += 1
        return [SimpleNamespace(ticker="SPY")]

    client = SimpleNamespace(list_tickers=_list)
    for _ in range(2):
        polygon.fetch_etf_tickers(
            "2025-08-01", cache_path=cache_path, client=client,
            limiter=open_limiter,
        )
    assert calls["n"] == 1


# --- ruleout-screen fix: cumulative split factor -----------------------------


def test_split_factor_multiplies_splits_inside_the_window(cache_path, open_limiter):
    """A 25-for-1 then a 2-for-1, both after the filing and before the as-of
    date, compound to 50."""
    client = SimpleNamespace(list_splits=lambda *a, **kw: [
        SimpleNamespace(execution_date="2026-04-06", split_from=1, split_to=25),
        SimpleNamespace(execution_date="2026-06-01", split_from=1, split_to=2),
    ])
    got = polygon.split_factor(
        "BKNG", after="2025-12-31", through="2026-08-17",
        cache_path=cache_path, client=client, limiter=open_limiter)
    assert got == 50.0


def test_split_factor_ignores_splits_outside_the_window(cache_path, open_limiter):
    """A split BEFORE the filing period end is already in the filed share
    count. A split AFTER the as-of date has not happened yet. Neither counts."""
    client = SimpleNamespace(list_splits=lambda *a, **kw: [
        SimpleNamespace(execution_date="2020-01-01", split_from=1, split_to=4),
        SimpleNamespace(execution_date="2027-01-01", split_from=1, split_to=3),
    ])
    got = polygon.split_factor(
        "X", after="2025-12-31", through="2026-08-17",
        cache_path=cache_path, client=client, limiter=open_limiter)
    assert got == 1.0


def test_a_reverse_split_gives_a_factor_below_one(cache_path, open_limiter):
    """1-for-10 reverse split: 10 old shares become 1, so the filed count is
    multiplied by 0.1."""
    client = SimpleNamespace(list_splits=lambda *a, **kw: [
        SimpleNamespace(execution_date="2026-03-01", split_from=10, split_to=1),
    ])
    got = polygon.split_factor(
        "Y", after="2025-12-31", through="2026-08-17",
        cache_path=cache_path, client=client, limiter=open_limiter)
    assert got == 0.1


def test_no_splits_is_a_factor_of_one(cache_path, open_limiter):
    got = polygon.split_factor(
        "Z", after="2025-12-31", through="2026-08-17", cache_path=cache_path,
        client=SimpleNamespace(list_splits=lambda *a, **kw: []),
        limiter=open_limiter)
    assert got == 1.0


def test_an_empty_future_date_is_not_cached(cache_path, open_limiter):
    # Fetching a date before it trades returns nothing; that must not pin the
    # date to empty once it has traded.
    replies = [[], [_row("AAPL", 200.0, 50_000_000)]]
    client = SimpleNamespace(get_grouped_daily_aggs=lambda *a, **kw: replies.pop(0))
    assert polygon.fetch_grouped_daily("2999-01-04", cache_path=cache_path, client=client, limiter=open_limiter) == []
    out = polygon.fetch_grouped_daily("2999-01-04", cache_path=cache_path, client=client, limiter=open_limiter)
    assert [b.ticker for b in out] == ["AAPL"]


def test_an_empty_past_date_is_cached(cache_path, open_limiter):
    # a holiday stays empty; it is fetched once
    calls = {"n": 0}

    def reply(*a, **kw):
        calls["n"] += 1
        return []
    client = SimpleNamespace(get_grouped_daily_aggs=reply)
    for _ in range(2):
        assert polygon.fetch_grouped_daily("2024-12-25", cache_path=cache_path, client=client, limiter=open_limiter) == []
    assert calls["n"] == 1

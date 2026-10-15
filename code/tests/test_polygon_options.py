"""WS1 unit 3: Polygon option fetchers (fetch_option_contracts, fetch_option_aggs).

Mock-DI tests for mapping/cap/cache/guard, plus a live smoke (gated by
KAIROS_LIVE_SMOKE=1 + POLYGON_API_KEY) that hits the real SDK once -- the
MagicMock-masks-wrong-SDK-path trap means a wrapper is not done until a real
client returns real data.
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


def _contract(ticker, strike, exp, ctype="call", underlying="SPY"):
    return SimpleNamespace(
        ticker=ticker,
        underlying_ticker=underlying,
        contract_type=ctype,
        strike_price=strike,
        expiration_date=exp,
        shares_per_contract=100,
    )


def test_fetch_option_contracts_maps_caps_and_sorts(cache_path, open_limiter):
    # Returned out of order; limit caps to 3; result mapped + sorted (exp, strike).
    client = SimpleNamespace(
        list_options_contracts=lambda **kw: iter(
            [
                _contract("O:SPY...C00520000", 520.0, "2026-08-21"),
                _contract("O:SPY...C00500000", 500.0, "2026-07-17"),
                _contract("O:SPY...C00510000", 510.0, "2026-07-17"),
                _contract("O:SPY...C00530000", 530.0, "2026-09-18"),
                _contract("O:SPY...C00540000", 540.0, "2026-10-16"),
            ]
        )
    )
    out = polygon.fetch_option_contracts(
        "SPY", contract_type="call", limit=3,
        cache_path=cache_path, client=client, limiter=open_limiter,
    )
    assert len(out) == 3
    assert [(c.strike, c.expiration) for c in out] == [
        (500.0, "2026-07-17"),
        (510.0, "2026-07-17"),
        (520.0, "2026-08-21"),
    ]
    c0 = out[0]
    assert c0.ticker == "O:SPY...C00500000"
    assert c0.underlying == "SPY" and c0.contract_type == "call"
    assert c0.shares_per_contract == 100


def test_fetch_option_contracts_cache_hit_skips_client(cache_path, open_limiter):
    calls = {"n": 0}

    def _list(**kw):
        calls["n"] += 1
        return iter([_contract("O:SPY...C00500000", 500.0, "2026-07-17")])

    client = SimpleNamespace(list_options_contracts=_list)
    kw = dict(cache_path=cache_path, client=client, limiter=open_limiter)
    polygon.fetch_option_contracts("SPY", contract_type="call", **kw)
    polygon.fetch_option_contracts("SPY", contract_type="call", **kw)
    assert calls["n"] == 1  # second call served from SQLite cache


def test_fetch_option_aggs_rejects_bare_underlying(cache_path, open_limiter):
    with pytest.raises(ValueError, match="OCC option ticker"):
        polygon.fetch_option_aggs(
            "SPY", from_date="2026-05-01", to_date="2026-06-01",
            cache_path=cache_path, limiter=open_limiter,
        )


def test_fetch_option_aggs_maps_bars(cache_path, open_limiter):
    client = SimpleNamespace(
        get_aggs=lambda **kw: [
            SimpleNamespace(timestamp=1, open=1.0, high=1.5, low=0.9, close=1.2, volume=42)
        ]
    )
    out = polygon.fetch_option_aggs(
        "O:SPY260629C00500000", from_date="2026-05-01", to_date="2026-06-01",
        cache_path=cache_path, client=client, limiter=open_limiter,
    )
    assert len(out) == 1 and out[0].close == 1.2 and out[0].volume == 42.0


@pytest.mark.skipif(
    os.environ.get("KAIROS_LIVE_SMOKE") != "1" or not os.environ.get("POLYGON_API_KEY"),
    reason="live smoke: set KAIROS_LIVE_SMOKE=1 and POLYGON_API_KEY",
)
def test_live_smoke_real_sdk(tmp_path):
    import socket

    socket.setdefaulttimeout(30)  # SDK ~1.16 does not apply its own timeout
    cp = tmp_path / "live-cache.sqlite"
    lm = polygon.RateLimiter(max_calls=100, per_seconds=1.0)
    contracts = polygon.fetch_option_contracts(
        "SPY", contract_type="call", limit=3, cache_path=cp, limiter=lm
    )
    assert contracts and contracts[0].ticker.startswith("O:SPY")
    bars = polygon.fetch_option_aggs(
        contracts[0].ticker, from_date="2026-05-01", to_date="2026-06-20",
        cache_path=cp, limiter=lm,
    )
    assert isinstance(bars, list)  # contract may be illiquid; shape is what matters

"""Polygon REST wrapper with rate limiting and SQLite-backed memoization.

Cloned from swing-trader's wrapper, trimmed to what an options bot needs:
`fetch_aggs` (underlying daily/intraday OHLCV bars). The options-specific
fetchers (`fetch_option_contracts`, `fetch_option_aggs`) are added in WS1 unit 3.
Equity-fundamentals fetchers (CAN-SLIM-shaped) are intentionally omitted — dead
weight for options.

Each fetch runs through a sliding-window rate limiter (default 5 calls / 60s, the
Polygon free-tier ceiling) and a SQLite cache keyed by `(function, args)`. Live
API calls happen only on cache miss; tests inject mocked clients and limiters via
keyword arguments. `POLYGON_API_KEY` is read from the environment by `_get_client`;
the key is never committed (`.env` is gitignored).

Known SDK limitation (polygon-api-client ~1.16): the RESTClient constructor stores
`urllib3.Timeout(connect=..., read=...)` but the internal `_get()` does NOT pass it
to `self.client.request()`, so the timeout object is created but unused at the HTTP
layer. Passing explicit values is still load-bearing (constructor-kwarg tests verify
the threading); the real hang guard is `socket.setdefaulttimeout()` in `_get_client`
(the SDK/TCP-keepalive path did NOT prevent a 5h 0%-CPU hang on a stuck fetch,
2026-07-04) plus `POLYGON_MAX_RETRIES`.
"""

from __future__ import annotations

import itertools
import json
import os
import socket
import sqlite3
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any, Callable

from polygon import RESTClient


DEFAULT_CACHE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "polygon-cache.sqlite"
)


@dataclass(frozen=True)
class Agg:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class OptionContract:
    ticker: str  # OCC option ticker, e.g. "O:SPY260629C00500000"
    underlying: str
    contract_type: str  # "call" | "put"
    strike: float
    expiration: str  # ISO "YYYY-MM-DD"
    shares_per_contract: int


@dataclass(frozen=True)
class GroupedBar:
    """One ticker's daily OHLCV from a whole-market grouped-daily fetch.

    No timestamp: the date is the fetch argument. Dollar-volume = close * volume.
    """

    ticker: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class NewsItem:
    title: str
    published_utc: str
    url: str
    description: str
    # per-ticker relevance from Polygon's insights block; defaulted so cache
    # rows written before the field existed still load via NewsItem(**row)
    insights: list = field(default_factory=list)


def ticker_insight(item: NewsItem, ticker: str) -> dict | None:
    """The article's insight entry for `ticker`, or None when the article is
    not about it (mention-based ticker matching pollutes list_ticker_news —
    live: 9/10 MU items were other-company/macro, audit 2026-07-08)."""
    for ins in item.insights:
        if ins.get("ticker") == ticker:
            return ins
    return None


def news_context(item: NewsItem, ticker: str) -> tuple[str, str, str] | None:
    """(date, title, body) for a relevant article, None otherwise. The body
    keeps the per-ticker relevance REASONING prose (the filter's footprint —
    junk self-discounts) relabeled `context:`, and drops the directional
    sentiment label: news sentiment is a 1-2 week signal, noise at the 4-26
    week thesis horizon (dossier-v4; Fed-study evidence). Prompts reframe
    news as dated-factual-catalyst extraction."""
    ins = ticker_insight(item, ticker)
    if ins is None:
        return None
    body = (f"{item.description}\ncontext ({ticker}): "
            f"{ins['sentiment_reasoning']}")
    return (item.published_utc[:10], item.title, body)


class RateLimiter:
    """Sliding-window limiter: at most ``max_calls`` per ``per_seconds`` window.

    The Polygon free tier caps at 5 calls / 60s; we run a hair under by blocking
    until the oldest in-window call ages out. ``_now`` and ``_sleep`` are
    injectable for deterministic tests.
    """

    def __init__(self, max_calls: int = 5, per_seconds: float = 60.0) -> None:
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(
        self,
        *,
        _now: Callable[[], float] = time.monotonic,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        with self._lock:
            now = _now()
            self._evict(now)
            if len(self._calls) >= self.max_calls:
                wait = self.per_seconds - (now - self._calls[0])
                if wait > 0:
                    _sleep(wait)
                now = _now()
                self._evict(now)
            self._calls.append(now)

    def _evict(self, now: float) -> None:
        while self._calls and now - self._calls[0] >= self.per_seconds:
            self._calls.popleft()


_DEFAULT_LIMITER = RateLimiter(max_calls=5, per_seconds=60.0)


def _get_client() -> RESTClient:
    # Lazy import avoids a circular dependency: config imports RateLimiter from
    # this module, so this module cannot import config at module level.
    from kairos import config  # noqa: PLC0415

    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        raise RuntimeError(
            "POLYGON_API_KEY env var is required (see .env.example)."
        )
    # The SDK ignores its own Timeout object (see module docstring), so a hung socket read
    # blocks FOREVER (a detached overnight backfill sat 5h at 0% CPU on one stuck fetch,
    # 2026-07-04). A process-global socket default timeout IS honored at the urllib3/socket
    # layer and turns an infinite block into a raise -> POLYGON_MAX_RETRIES then retries.
    socket.setdefaulttimeout(config.POLYGON_REQUEST_TIMEOUT)
    return RESTClient(
        key,
        connect_timeout=config.POLYGON_REQUEST_TIMEOUT,
        read_timeout=config.POLYGON_REQUEST_TIMEOUT,
        retries=config.POLYGON_MAX_RETRIES,
    )


def _ensure_cache(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polygon_cache (
          function TEXT NOT NULL,
          args_json TEXT NOT NULL,
          response_json TEXT NOT NULL,
          fetched_at TEXT NOT NULL,
          PRIMARY KEY (function, args_json)
        )
        """
    )
    conn.commit()
    return conn


def _cache_get(conn: sqlite3.Connection, function: str, args_json: str) -> str | None:
    row = conn.execute(
        "SELECT response_json FROM polygon_cache WHERE function = ? AND args_json = ?",
        (function, args_json),
    ).fetchone()
    return row[0] if row else None


def _cache_put(
    conn: sqlite3.Connection, function: str, args_json: str, response_json: str
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO polygon_cache (function, args_json, response_json, fetched_at) "
        "VALUES (?, ?, ?, ?)",
        (function, args_json, response_json, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _resolve(
    cache_path: Path | None, client: RESTClient | None, limiter: RateLimiter | None
) -> tuple[Path, RateLimiter, Callable[[], RESTClient]]:
    cp = cache_path or DEFAULT_CACHE_PATH
    lm = limiter or _DEFAULT_LIMITER
    get_client = (lambda: client) if client is not None else _get_client
    return cp, lm, get_client


def fetch_aggs(
    symbol: str,
    *,
    from_date: str,
    to_date: str,
    timespan: str = "day",
    multiplier: int = 1,
    cache_path: Path | None = None,
    client: RESTClient | None = None,
    limiter: RateLimiter | None = None,
) -> list[Agg]:
    """Underlying OHLCV bars for `symbol` over [from_date, to_date] (ISO dates)."""
    cp, lm, get_client = _resolve(cache_path, client, limiter)
    args_json = json.dumps(
        {
            "symbol": symbol,
            "from_date": from_date,
            "to_date": to_date,
            "timespan": timespan,
            "multiplier": multiplier,
        },
        sort_keys=True,
    )
    conn = _ensure_cache(cp)
    try:
        cached = _cache_get(conn, "fetch_aggs", args_json)
        if cached is not None:
            return [Agg(**row) for row in json.loads(cached)]
        lm.acquire()
        raw = get_client().get_aggs(
            ticker=symbol,
            multiplier=multiplier,
            timespan=timespan,
            from_=from_date,
            to=to_date,
        )
        aggs = [
            Agg(
                timestamp=int(a.timestamp),
                open=float(a.open),
                high=float(a.high),
                low=float(a.low),
                close=float(a.close),
                volume=float(a.volume),
            )
            for a in raw
        ]
        _cache_put(conn, "fetch_aggs", args_json, json.dumps([asdict(a) for a in aggs]))
        return aggs
    finally:
        conn.close()


_GROUPED_MISS_COUNT = 0


def miss_count() -> int:
    """Cold grouped-daily fetches since the last reset. A rewind-corpus
    warm re-run must report 0 (thesis-rewind-eval A3): the null-ledger
    precedent is an all-zero backtest that passed on a silently empty
    cache."""
    return _GROUPED_MISS_COUNT


def reset_miss_count() -> None:
    global _GROUPED_MISS_COUNT
    _GROUPED_MISS_COUNT = 0


def fetch_grouped_daily(
    date: str,
    *,
    adjusted: bool = True,
    cache_path: Path | None = None,
    client: RESTClient | None = None,
    limiter: RateLimiter | None = None,
) -> list[GroupedBar]:
    """Every US-stock ticker's daily OHLCV for one `date` (ISO) in ONE API call.

    The survivorship-clean liquidity primitive: a name appears iff it actually
    traded that day, so later-delisted names are present on their live dates. Rank
    by close*volume to reconstruct the point-in-time liquid universe. Rows with a
    missing ticker are skipped (the grouped feed occasionally returns blanks).
    """
    cp, lm, get_client = _resolve(cache_path, client, limiter)
    args_json = json.dumps({"date": date, "adjusted": adjusted}, sort_keys=True)
    conn = _ensure_cache(cp)
    try:
        cached = _cache_get(conn, "fetch_grouped_daily", args_json)
        if cached is not None:
            return [GroupedBar(**row) for row in json.loads(cached)]
        global _GROUPED_MISS_COUNT
        _GROUPED_MISS_COUNT += 1
        lm.acquire()
        raw = get_client().get_grouped_daily_aggs(date, adjusted=adjusted)
        bars = [
            GroupedBar(
                ticker=r.ticker,
                open=float(r.open),
                high=float(r.high),
                low=float(r.low),
                close=float(r.close),
                volume=float(r.volume),
            )
            for r in raw
            if getattr(r, "ticker", None)
        ]
        _cache_put(
            conn, "fetch_grouped_daily", args_json, json.dumps([asdict(b) for b in bars])
        )
        return bars
    finally:
        conn.close()


def split_factor(
    ticker: str,
    *,
    after: str,
    through: str,
    cache_path: Path | None = None,
    client: RESTClient | None = None,
    limiter: RateLimiter | None = None,
) -> float:
    """Cumulative share-count multiplier for splits executed in (`after`,
    `through`].

    Grouped-daily closes are SPLIT-ADJUSTED; a share count read from a filing
    is not. Multiply the filed count by this factor before pairing it with a
    close, or the market cap is wrong by the split ratio (see
    `screen.pit_market_cap`).

    `after` is the filing's period end: a split before it is already reflected
    in the filed count. `through` is the as-of date: a later split has not
    happened yet. A 25-for-1 returns 25.0, a 1-for-10 reverse returns 0.1, and
    no splits in the window returns 1.0.
    """
    cp, lm, get_client = _resolve(cache_path, client, limiter)
    args_json = json.dumps({"ticker": ticker}, sort_keys=True)
    conn = _ensure_cache(cp)
    try:
        cached = _cache_get(conn, "list_splits", args_json)
        if cached is not None:
            rows = json.loads(cached)
        else:
            lm.acquire()
            raw = get_client().list_splits(ticker=ticker, limit=1000)
            rows = [{"date": r.execution_date, "from": r.split_from,
                     "to": r.split_to} for r in raw
                    if getattr(r, "execution_date", None)]
            _cache_put(conn, "list_splits", args_json, json.dumps(rows))
        factor = 1.0
        for r in rows:
            if after < r["date"] <= through and r["from"]:
                factor *= r["to"] / r["from"]
        return factor
    finally:
        conn.close()


def fetch_etf_tickers(
    date: str,
    *,
    cache_path: Path | None = None,
    client: RESTClient | None = None,
    limiter: RateLimiter | None = None,
) -> set[str]:
    """Every ticker classified as an ETF ON `date` (ISO), as a set.

    Point-in-time by the `date` argument, never today's list: 4,190 tickers
    were ETFs on 2025-08-01 against 5,374 on 2026-08-17, so a today-built set
    would strike names out of a 2025 universe that were ordinary stocks then,
    and miss ETFs that have since delisted.

    Used to build the ETF-free market denominator for the filter bench
    (`scripts/score_filter.py`, funnel-loop CONTRACT 2). ETFs almost never
    reach the market's top alpha decile, so leaving them in flatters every
    lift number the bench prints.
    """
    cp, lm, get_client = _resolve(cache_path, client, limiter)
    args_json = json.dumps({"date": date, "type": "ETF"}, sort_keys=True)
    conn = _ensure_cache(cp)
    try:
        cached = _cache_get(conn, "fetch_etf_tickers", args_json)
        if cached is not None:
            return set(json.loads(cached))
        lm.acquire()
        raw = get_client().list_tickers(
            market="stocks", type="ETF", active=True, limit=1000, date=date
        )
        out = {t.ticker for t in raw if getattr(t, "ticker", None)}
        _cache_put(conn, "fetch_etf_tickers", args_json,
                   json.dumps(sorted(out)))
        return out
    finally:
        conn.close()


def fetch_ticker_news(
    ticker: str,
    *,
    limit: int = 10,
    published_lte: str | None = None,
    cache_path: Path | None = None,
    client: RESTClient | None = None,
    limiter: RateLimiter | None = None,
) -> list["NewsItem"]:
    """Recent news articles for `ticker` (title/date/url/description).

    `published_lte` (ISO date) bounds the fetch point-in-time for rewind
    dossiers: passed to the API as `published_utc.lte` AND enforced on the
    returned rows, so neither a cached payload nor a misbehaving response can
    leak a post-as-of article. Cached like every other fetcher; the thesis
    engine treats article content as untrusted input (catalyst-flagging,
    never an instruction)."""
    cp, lm, get_client = _resolve(cache_path, client, limiter)
    # v3: published_lte joins the cache key — an as-of-blind v2 row holding
    # today's articles must never be served to a rewind (as-of) call
    args_json = json.dumps(
        {"ticker": ticker, "limit": limit, "published_lte": published_lte,
         "v": 3},
        sort_keys=True)
    conn = _ensure_cache(cp)
    try:
        cached = _cache_get(conn, "fetch_ticker_news", args_json)
        if cached is not None:
            # clamp on read too: rows cached before the islice fix hold full
            # paginated payloads (185+ items under a limit=5 key)
            return [NewsItem(**row) for row in json.loads(cached)[:limit]]
        lm.acquire()
        api_kwargs = {}
        if published_lte is not None:
            api_kwargs["published_utc_lte"] = published_lte
        # islice: the SDK iterator auto-paginates past `limit` (it is a
        # per-page size), so an unbounded list() fetches every page
        raw = itertools.islice(
            get_client().list_ticker_news(ticker=ticker, limit=limit,
                                          **api_kwargs),
            limit,
        )
        items = [
            NewsItem(
                title=str(a.title),
                published_utc=str(a.published_utc),
                url=str(a.article_url),
                description=str(getattr(a, "description", "") or ""),
                insights=[
                    {"ticker": str(ins.ticker), "sentiment": str(ins.sentiment),
                     "sentiment_reasoning": str(ins.sentiment_reasoning)}
                    for ins in (getattr(a, "insights", None) or [])
                ],
            )
            for a in raw
        ]
        if published_lte is not None:
            items = [i for i in items if i.published_utc[:10] <= published_lte]
        _cache_put(conn, "fetch_ticker_news", args_json, json.dumps([asdict(i) for i in items]))
        return items
    finally:
        conn.close()


def fetch_option_contracts(
    underlying: str,
    *,
    contract_type: str | None = None,
    expiration_date: str | None = None,
    expiration_gte: str | None = None,
    expiration_lte: str | None = None,
    as_of: str | None = None,
    limit: int = 250,
    cache_path: Path | None = None,
    client: RESTClient | None = None,
    limiter: RateLimiter | None = None,
) -> list[OptionContract]:
    """Option-chain contract reference for `underlying`.

    `contract_type` is "call"/"put" (None = both). The expiration filters take an
    exact date or a gte/lte band. `as_of` requests the chain as it stood on a past
    date (point-in-time, for backtest). `limit` caps the TOTAL contracts returned
    via islice -- the SDK's list_options_contracts auto-paginates and treats its own
    `limit` as a page size, so without this guard a broad query pulls the entire
    chain (thousands of rows). Sorted by (expiration, strike) for determinism.
    """
    cp, lm, get_client = _resolve(cache_path, client, limiter)
    args_json = json.dumps(
        {
            "underlying": underlying,
            "contract_type": contract_type,
            "expiration_date": expiration_date,
            "expiration_gte": expiration_gte,
            "expiration_lte": expiration_lte,
            "as_of": as_of,
            "limit": limit,
        },
        sort_keys=True,
    )
    conn = _ensure_cache(cp)
    try:
        cached = _cache_get(conn, "fetch_option_contracts", args_json)
        if cached is not None:
            return [OptionContract(**row) for row in json.loads(cached)]
        lm.acquire()
        kwargs: dict[str, Any] = {"underlying_ticker": underlying, "limit": limit}
        if contract_type is not None:
            kwargs["contract_type"] = contract_type
        if expiration_date is not None:
            kwargs["expiration_date"] = expiration_date
        if expiration_gte is not None:
            kwargs["expiration_date_gte"] = expiration_gte
        if expiration_lte is not None:
            kwargs["expiration_date_lte"] = expiration_lte
        if as_of is not None:
            kwargs["as_of"] = as_of
        raw = islice(get_client().list_options_contracts(**kwargs), limit)
        contracts = [
            OptionContract(
                ticker=c.ticker,
                underlying=c.underlying_ticker,
                contract_type=c.contract_type,
                strike=float(c.strike_price),
                expiration=c.expiration_date,
                shares_per_contract=int(getattr(c, "shares_per_contract", 100) or 100),
            )
            for c in raw
        ]
        contracts.sort(key=lambda c: (c.expiration, c.strike))
        _cache_put(
            conn,
            "fetch_option_contracts",
            args_json,
            json.dumps([asdict(c) for c in contracts]),
        )
        return contracts
    finally:
        conn.close()


def fetch_option_aggs(
    option_ticker: str,
    *,
    from_date: str,
    to_date: str,
    timespan: str = "day",
    multiplier: int = 1,
    cache_path: Path | None = None,
    client: RESTClient | None = None,
    limiter: RateLimiter | None = None,
) -> list[Agg]:
    """Historical OHLCV bars for one OCC option contract (the backtest source).

    Guards on the `O:` prefix: passing a bare underlying (e.g. "SPY") would silently
    fetch equity bars into the options path, corrupting a backtest. Fail loud instead.
    """
    if not option_ticker.startswith("O:"):
        raise ValueError(
            f"fetch_option_aggs expects an OCC option ticker (e.g. 'O:SPY260629C00500000'); "
            f"got {option_ticker!r}. Use fetch_aggs for underlying bars."
        )
    cp, lm, get_client = _resolve(cache_path, client, limiter)
    args_json = json.dumps(
        {
            "option_ticker": option_ticker,
            "from_date": from_date,
            "to_date": to_date,
            "timespan": timespan,
            "multiplier": multiplier,
        },
        sort_keys=True,
    )
    conn = _ensure_cache(cp)
    try:
        cached = _cache_get(conn, "fetch_option_aggs", args_json)
        if cached is not None:
            return [Agg(**row) for row in json.loads(cached)]
        lm.acquire()
        raw = get_client().get_aggs(
            ticker=option_ticker,
            multiplier=multiplier,
            timespan=timespan,
            from_=from_date,
            to=to_date,
        )
        aggs = [
            Agg(
                timestamp=int(a.timestamp),
                open=float(a.open),
                high=float(a.high),
                low=float(a.low),
                close=float(a.close),
                volume=float(a.volume),
            )
            for a in raw
        ]
        _cache_put(
            conn, "fetch_option_aggs", args_json, json.dumps([asdict(a) for a in aggs])
        )
        return aggs
    finally:
        conn.close()

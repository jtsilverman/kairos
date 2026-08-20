"""Forward verdict ledger (thesis-verdict-ledger spec): every recorded
thesis verdict becomes a scoreable prediction.

Three INSERT-only tables, self-owned here (the memo.ensure_schema additive
idiom): `verdict_ledger` (one row per memo — entry mark, status, outcome),
`verdict_marks` (daily closes per open verdict), `verdict_reviews`
(move/news/manual/missing_bar flags + outcome notes). Reasoning stays in
`thesis_memos` (FK, never copied); marks are strictly forward-only PIT.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from kairos import config

_ET = ZoneInfo("America/New_York")   # DST-aware; a fixed UTC offset misreads EST season
_CLOSE_ET = time(16, 0)


class MissingBarError(Exception):
    """A traded date's grouped bars lack the ticker (or SPY) — fail loud,
    never fake a price."""


class PITViolationError(Exception):
    """A mark dated before the row's entry — forward-only, always."""


class PrematureMarkError(Exception):
    """Marking today before 16:15 ET (or a future date) — refused BEFORE any
    fetch: an intraday grouped-daily fetch would poison the forever-cache
    with a partial bar (polygon cache has no TTL)."""


class NoBarsError(Exception):
    """The mark date returned zero grouped bars (non-trading day)."""


class MarkConflictError(Exception):
    """A different value for an already-marked (memo_id, mark_date)."""


class UnknownMemoError(Exception):
    """A review against a memo_id with no thesis_memos row — a typo'd id
    would otherwise insert an orphan the report JOIN silently drops."""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS verdict_ledger (
    memo_id       INTEGER PRIMARY KEY,      -- FK thesis_memos.id, one row per memo
    entry_date    TEXT,                     -- NULL only while entry-pending
    entry_price   REAL,
    spy_entry     REAL,
    status        TEXT NOT NULL DEFAULT 'open',  -- open|closed
    closed_date   TEXT,
    ticker_return REAL,
    spy_return    REAL,
    alpha         REAL,
    hit           INTEGER                   -- 1|0, NULL until closed
);
CREATE TABLE IF NOT EXISTS verdict_marks (
    memo_id   INTEGER NOT NULL,
    mark_date TEXT NOT NULL,
    close     REAL NOT NULL,
    spy_close REAL NOT NULL,
    PRIMARY KEY (memo_id, mark_date)
);
CREATE TABLE IF NOT EXISTS verdict_reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    memo_id     INTEGER NOT NULL,
    review_date TEXT NOT NULL,
    trigger     TEXT NOT NULL CHECK (trigger IN
                    ('move', 'news', 'manual', 'missing_bar')),
    note        TEXT NOT NULL
);
"""

# Additive migration registry, per table (memo.ensure_schema idiom):
# CREATE IF NOT EXISTS skips an existing table, so columns added after a
# DB was created must be ALTERed in; existing rows stay readable (NULL).
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "verdict_ledger": {
        "entry_date": "TEXT",
        "entry_price": "REAL",
        "spy_entry": "REAL",
        "closed_date": "TEXT",
        "ticker_return": "REAL",
        "spy_return": "REAL",
        "alpha": "REAL",
        "hit": "INTEGER",
    },
    "verdict_marks": {},
    "verdict_reviews": {},
}


@dataclass(frozen=True)
class OpenRow:
    memo_id: int
    entry_date: Optional[str]    # None while entry-pending
    entry_price: Optional[float]
    spy_entry: Optional[float]


def entry_due_date(recorded_at: str) -> str:
    """First ET calendar date whose 16:00 close falls STRICTLY AFTER the
    verdict existed. A record at/after the close rolls to the next day;
    weekends/holidays resolve later by bar availability, not here."""
    dt = datetime.fromisoformat(recorded_at)
    if dt.tzinfo is None:
        raise ValueError(f"recorded_at must be timezone-aware: {recorded_at!r}")
    et = dt.astimezone(_ET)
    due = et.date()
    if et.time() >= _CLOSE_ET:
        due += timedelta(days=1)
    return due.isoformat()


def open_row(memo_id: int, ticker: str, recorded_at: str,
             bars_by_date: dict[str, dict[str, float]]) -> OpenRow:
    """Build the ledger open row from the first available bar date on/after
    the due date. No qualifying date yet -> entry-pending (all None); a
    qualifying date missing the ticker or SPY -> MissingBarError."""
    due = entry_due_date(recorded_at)
    for date in sorted(bars_by_date):
        if date < due:
            continue
        bars = bars_by_date[date]
        for symbol in (ticker, "SPY"):
            if symbol not in bars:
                raise MissingBarError(f"{symbol} absent from {date} grouped bars")
        return OpenRow(memo_id, date, bars[ticker], bars["SPY"])
    return OpenRow(memo_id, None, None, None)


@dataclass(frozen=True)
class Closure:
    closed_date: str
    ticker_return: float
    spy_return: float
    alpha: float
    hit: int  # graded market-relative: long = beat SPY, short = lagged SPY


def close_out(direction: str, entry_price: float, spy_entry: float,
              marks: list[tuple[str, float, float]],
              *, review_date: str) -> Optional[Closure]:
    """Close at the FIRST mark on/after review_date; None = stays open.
    marks: (mark_date, close, spy_close) in date order."""
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be long|short, got {direction!r}")
    for mark_date, close, spy_close in marks:
        if mark_date < review_date:
            continue
        ticker_return = close / entry_price - 1.0
        spy_return = spy_close / spy_entry - 1.0
        alpha = ticker_return - spy_return
        hit = int(alpha > 0 if direction == "long" else alpha < 0)
        return Closure(mark_date, ticker_return, spy_return, alpha, hit)
    return None


def move_flags(entry_price: float, marks: list[tuple[str, float]],
               *, already_flagged: set[str]) -> list[tuple[str, str, float]]:
    """Review flags for large moves against entry: (mark_date, direction,
    pct) at the FIRST crossing per direction ('up'/'down') not already
    flagged — at most one per direction over the row's lifetime, advisory
    only (nothing auto-closes). Threshold: config.REVIEW_MOVE_TRIGGER_PCT."""
    flagged = set(already_flagged)
    out = []
    for mark_date, close in marks:
        pct = close / entry_price - 1.0
        direction = "up" if pct > 0 else "down"
        if abs(pct) >= config.REVIEW_MOVE_TRIGGER_PCT and direction not in flagged:
            out.append((mark_date, direction, pct))
            flagged.add(direction)
    return out


def append_mark(conn: sqlite3.Connection, memo_id: int, mark_date: str,
                close: float, spy_close: float, *, entry_date: str) -> bool:
    """INSERT-only daily mark. True = written, False = identical row already
    present (idempotent re-run). Validates BEFORE insert: a pre-entry mark
    raises PITViolationError; a differing value for an existing day raises
    MarkConflictError (never silently kept or replaced)."""
    if mark_date < entry_date:
        raise PITViolationError(
            f"mark {mark_date} predates entry {entry_date} (memo {memo_id})")
    existing = conn.execute(
        "SELECT close, spy_close FROM verdict_marks"
        " WHERE memo_id = ? AND mark_date = ?", (memo_id, mark_date)).fetchone()
    if existing is not None:
        if existing != (close, spy_close):
            raise MarkConflictError(
                f"memo {memo_id} {mark_date}: stored {existing} != "
                f"({close}, {spy_close})")
        return False
    conn.execute(
        "INSERT INTO verdict_marks (memo_id, mark_date, close, spy_close)"
        " VALUES (?, ?, ?, ?)", (memo_id, mark_date, close, spy_close))
    # no commit here: mark_day's sweep transaction owns atomicity (an inner
    # commit would flush earlier rows and defeat rollback-on-failure);
    # standalone callers commit themselves.
    return True


@dataclass(frozen=True)
class MarkSummary:
    marks_written: int
    entries_filled: int
    move_flags: int
    closed: int
    missing: int


_POST_CLOSE_ET = time(16, 15)


def _flag_once(conn: sqlite3.Connection, memo_id: int, review_date: str,
               trigger: str, note: str) -> int:
    """Insert a review flag unless one with this (memo_id, date, trigger)
    already exists. Returns rows written (0 or 1)."""
    exists = conn.execute(
        'SELECT 1 FROM verdict_reviews WHERE memo_id=? AND review_date=?'
        ' AND "trigger"=?', (memo_id, review_date, trigger)).fetchone()
    if exists:
        return 0
    conn.execute(
        'INSERT INTO verdict_reviews (memo_id, review_date, "trigger", note)'
        " VALUES (?,?,?,?)", (memo_id, review_date, trigger, note))
    return 1


def _flagged_move_directions(conn: sqlite3.Connection, memo_id: int) -> set[str]:
    """Lifetime move-flag state, derived from verdict_reviews (the note's
    first token is the direction — written by mark_day below, one module
    owns both sides of that convention)."""
    return {row[0].split()[0] for row in conn.execute(
        'SELECT note FROM verdict_reviews WHERE memo_id=? AND "trigger"=?',
        (memo_id, "move"))}


def mark_day(conn: sqlite3.Connection, mark_date: str, *,
             now_et: datetime, fetch_bars) -> MarkSummary:
    """One post-close marking sweep for every open verdict row.

    Guards fire BEFORE fetch_bars is called (cache-poison trap). Missing
    SPY halts with zero writes; a single missing ticker flags and skips
    that row while siblings mark. Entry-pending rows whose due date has
    arrived fill from this date's bars. Rows past review_date close via
    close_out; an entry-pending row past review_date flags loud and stays
    open. Idempotent: a same-day re-run writes nothing new."""
    et_now = now_et.astimezone(_ET)
    today = et_now.date().isoformat()
    if mark_date > today:
        raise PrematureMarkError(f"mark date {mark_date} is in the future")
    if mark_date == today and et_now.time() < _POST_CLOSE_ET:
        raise PrematureMarkError(
            f"refusing to mark {mark_date} before 16:15 ET (now "
            f"{et_now.time():%H:%M} ET) — an intraday fetch poisons the cache")

    bars = fetch_bars(mark_date)
    if not bars:
        raise NoBarsError(f"{mark_date}: no grouped bars (non-trading day?)")
    if "SPY" not in bars:
        raise MissingBarError(
            f"SPY absent from {mark_date} grouped bars — no marks without "
            "the benchmark")
    spy_close = bars["SPY"]

    rows = conn.execute(
        "SELECT vl.memo_id, m.ticker, m.direction, m.recorded_at,"
        " m.review_date, vl.entry_date, vl.entry_price, vl.spy_entry"
        " FROM verdict_ledger vl JOIN thesis_memos m ON m.id = vl.memo_id"
        " WHERE vl.status = 'open' ORDER BY vl.memo_id").fetchall()

    marks = filled = flags = closed = missing = 0
    with conn:
        for (memo_id, ticker, direction, recorded_at, review_date,
             entry_date, entry_price, spy_entry) in rows:
            if entry_date is None:
                due = entry_due_date(recorded_at)
                if due > mark_date:
                    continue  # not yet due, silently pending
                if ticker not in bars:
                    past = ", past review_date" if review_date <= mark_date else ""
                    missing += _flag_once(
                        conn, memo_id, mark_date, "missing_bar",
                        f"{ticker} absent from {mark_date} grouped bars "
                        f"(entry-pending{past})")
                    continue
                entry_date, entry_price, spy_entry = (
                    mark_date, bars[ticker], spy_close)
                conn.execute(
                    "UPDATE verdict_ledger SET entry_date=?, entry_price=?,"
                    " spy_entry=? WHERE memo_id=?",
                    (entry_date, entry_price, spy_entry, memo_id))
                filled += 1

            if ticker not in bars:
                missing += _flag_once(
                    conn, memo_id, mark_date, "missing_bar",
                    f"{ticker} absent from {mark_date} grouped bars")
                continue
            close = bars[ticker]
            if append_mark(conn, memo_id, mark_date, close, spy_close,
                           entry_date=entry_date):
                marks += 1
            for date, dirn, pct in move_flags(
                    entry_price, [(mark_date, close)],
                    already_flagged=_flagged_move_directions(conn, memo_id)):
                conn.execute(
                    'INSERT INTO verdict_reviews (memo_id, review_date,'
                    ' "trigger", note) VALUES (?,?,?,?)',
                    (memo_id, date, "move", f"{dirn} {pct:+.1%} at {date}"))
                flags += 1
            if review_date <= mark_date:
                c = close_out(direction, entry_price, spy_entry,
                              [(mark_date, close, spy_close)],
                              review_date=review_date)
                if c is not None:
                    conn.execute(
                        "UPDATE verdict_ledger SET status='closed',"
                        " closed_date=?, ticker_return=?, spy_return=?,"
                        " alpha=?, hit=? WHERE memo_id=?",
                        (c.closed_date, c.ticker_return, c.spy_return,
                         c.alpha, c.hit, memo_id))
                    closed += 1
    return MarkSummary(marks, filled, flags, closed, missing)


def pin_key(agent_hashes_json: str) -> str:
    """Canonical scorer-pin grouping key over the THREE live shapes: legacy
    flat `{"analyst": "<sha>"}` (66 rows, no efforts), nested scorer_pin()
    `{"analyst": {"sha256", "effort"}}`, and v9 per-seat
    `{..., "judge_opus": {..., "model"}, "judge_fable": {...}}` — short-shas
    in canonical role order, plus efforts and models when present. The model
    segment is load-bearing: without it a degraded seat would land in the
    same evidence window as true opus+fable memos."""
    pin = json.loads(agent_hashes_json)
    roles = (("analyst", "adversary", "judge_opus", "judge_fable")
             if "judge_opus" in pin else ("analyst", "adversary", "judge"))
    shas, efforts, models = [], [], []
    for role in roles:
        v = pin[role]
        if isinstance(v, str):
            shas.append(v[:12])
        else:
            shas.append(v["sha256"][:12])
            efforts.append(f"{role}={v['effort']}")
            if "model" in v:
                models.append(f"{role}={v['model']}")
    key = ":".join(shas)
    if efforts:
        key = f"{key}|{','.join(efforts)}"
    if models:
        key = f"{key}|{','.join(models)}"
    return key


def report_aggregates(rows: list[tuple]) -> list[dict]:
    """Aggregate (tier, direction, pin, cohort, status, alpha, hit) rows
    into per-group stats. cohort joined the key for the premove cohort-2
    readout slice. mean_alpha/hit_rate are over CLOSED rows only and are
    None (never NaN) when a group has zero closed."""
    groups: dict[tuple, dict] = {}
    for tier, direction, pin, cohort, status, alpha, hit in rows:
        g = groups.setdefault((tier, direction, pin, cohort), {
            "tier": tier, "direction": direction, "pin": pin,
            "cohort": cohort,
            "n": 0, "open": 0, "closed": 0, "_alphas": [], "_hits": []})
        g["n"] += 1
        if status == "closed":
            g["closed"] += 1
            g["_alphas"].append(alpha)
            g["_hits"].append(hit)
        else:
            g["open"] += 1
    out = []
    for key in sorted(groups):
        g = groups[key]
        alphas, hits = g.pop("_alphas"), g.pop("_hits")
        g["mean_alpha"] = sum(alphas) / len(alphas) if alphas else None
        g["hit_rate"] = sum(hits) / len(hits) if hits else None
        out.append(g)
    return out


def record_review(conn: sqlite3.Connection, memo_id: int, trigger: str,
                  note: str, *, review_date: str) -> None:
    """Record a review outcome (human/session adjudication) against a row.
    Fails loud on an unknown memo_id."""
    if conn.execute("SELECT 1 FROM thesis_memos WHERE id = ?",
                    (memo_id,)).fetchone() is None:
        raise UnknownMemoError(f"no thesis_memos row with id {memo_id}")
    conn.execute(
        'INSERT INTO verdict_reviews (memo_id, review_date, "trigger", note)'
        " VALUES (?,?,?,?)", (memo_id, review_date, trigger, note))
    conn.commit()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    for table, cols in _ADDITIVE_COLUMNS.items():
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, ddl_type in cols.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl_type}")
    conn.commit()

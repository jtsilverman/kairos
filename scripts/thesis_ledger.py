#!/usr/bin/env python3
"""Forward verdict ledger runner (thesis-verdict-ledger spec). Manual only —
no launchd. Subcommands:

  backfill  open one verdict_ledger row per thesis_memos row (entry = first
            close strictly after recorded_at in ET; rows whose entry close
            hasn't traded yet open entry-pending). One transaction: any
            missing expected bar HALTS with zero partial writes.
  mark      (U7) post-close daily marks for every open row.
  report    (U8) tier x direction x scorer-pin aggregates.
  review    (U8) record a review outcome note.

Usage:
    .venv/bin/python scripts/thesis_ledger.py backfill [--db data/kairos.db]
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sqlite3
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "code" / "src"))

from kairos.data import polygon
from kairos.thesis import ledger

logger = logging.getLogger("thesis_ledger")


def _et_today() -> dt.date:
    return dt.datetime.now(ZoneInfo("America/New_York")).date()


def _bars_map(dates: list[str]) -> dict[str, dict[str, float]]:
    """Grouped-daily closes for each date; empty responses (weekend/holiday)
    are skipped, never treated as a missing ticker."""
    out: dict[str, dict[str, float]] = {}
    for date in dates:
        bars = polygon.fetch_grouped_daily(date)
        if not bars:
            logger.info("%s: no grouped bars (non-trading day), skipped", date)
            continue
        out[date] = {b.ticker: b.close for b in bars}
        logger.info("%s: %d grouped bars", date, len(out[date]))
    return out


def _trading_dates_through_today(start: str) -> list[str]:
    d = dt.date.fromisoformat(start)
    today = _et_today()
    dates = []
    while d <= today:
        dates.append(d.isoformat())
        d += dt.timedelta(days=1)
    return dates


def cmd_backfill(args: argparse.Namespace) -> int:
    db = Path(args.db)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = db.with_name(f"{db.name}.bak-{stamp}-ledger-backfill")
    src = sqlite3.connect(db)
    dst = sqlite3.connect(bak)
    src.backup(dst)
    dst.close()
    if not bak.exists() or bak.stat().st_size == 0:
        raise SystemExit(f"backup missing/empty at {bak} — refusing to write")
    print(f"backup: {bak} ({bak.stat().st_size} bytes)")

    ledger.ensure_schema(src)
    memos = src.execute(
        "SELECT id, ticker, recorded_at FROM thesis_memos"
        " WHERE id NOT IN (SELECT memo_id FROM verdict_ledger)"
        " ORDER BY id").fetchall()
    if not memos:
        print("backfill: nothing to open (all memos already in verdict_ledger)")
        return 0

    due_dates = [ledger.entry_due_date(rec) for _, _, rec in memos]
    fetchable = [d for d in sorted(set(due_dates)) if d <= _et_today().isoformat()]
    candidate_dates = (_trading_dates_through_today(min(fetchable))
                       if fetchable else [])
    bars_by_date = _bars_map(candidate_dates)

    opened = pending = 0
    with src:  # one transaction: a MissingBarError rolls back everything
        for memo_id, ticker, recorded_at in memos:
            row = ledger.open_row(memo_id, ticker, recorded_at, bars_by_date)
            src.execute(
                "INSERT INTO verdict_ledger (memo_id, entry_date, entry_price,"
                " spy_entry, status) VALUES (?, ?, ?, ?, 'open')",
                (row.memo_id, row.entry_date, row.entry_price, row.spy_entry))
            if row.entry_date is None:
                pending += 1
                logger.info("%s (memo %d): entry-pending (due %s)",
                            ticker, memo_id, ledger.entry_due_date(recorded_at))
            else:
                opened += 1
    print(f"backfill: {opened} rows priced, {pending} entry-pending, "
          f"0 marks written")
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    conn = sqlite3.connect(args.db)
    ledger.ensure_schema(conn)
    now_et = dt.datetime.now(ZoneInfo("America/New_York"))
    mark_date = args.date or now_et.date().isoformat()

    def fetch_bars(date: str) -> dict[str, float]:
        return {b.ticker: b.close for b in polygon.fetch_grouped_daily(date)}

    s = ledger.mark_day(conn, mark_date, now_et=now_et, fetch_bars=fetch_bars)
    print(f"mark {mark_date}: {s.marks_written} marks written, "
          f"{s.entries_filled} entries filled, {s.move_flags} move flags, "
          f"{s.closed} closed, {s.missing} missing-bar flags")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    conn = sqlite3.connect(args.db)
    ledger.ensure_schema(conn)
    rows = [
        (tier, direction, ledger.pin_key(pin_json), cohort, status, alpha, hit)
        for tier, direction, pin_json, cohort, status, alpha, hit in conn.execute(
            "SELECT m.conviction_tier, m.direction, m.agent_hashes_json,"
            " m.cohort, vl.status, vl.alpha, vl.hit"
            " FROM verdict_ledger vl JOIN thesis_memos m ON m.id = vl.memo_id")
    ]
    fmt = "{:<4} {:<6} {:<52} {:<8} {:>3} {:>5} {:>7} {:>10} {:>9}"
    print(fmt.format("tier", "dir", "scorer pin", "cohort", "n", "open",
                     "closed", "mean_alpha", "hit_rate"))
    for g in ledger.report_aggregates(rows):
        print(fmt.format(
            g["tier"], g["direction"], g["pin"][:52], g["cohort"], g["n"],
            g["open"], g["closed"],
            "-" if g["mean_alpha"] is None else f"{g['mean_alpha']:+.3f}",
            "-" if g["hit_rate"] is None else f"{g['hit_rate']:.0%}"))
    flagged = conn.execute(
        'SELECT r.memo_id, m.ticker, r.review_date, r."trigger", r.note'
        " FROM verdict_reviews r JOIN thesis_memos m ON m.id = r.memo_id"
        " ORDER BY r.review_date, r.memo_id").fetchall()
    print(f"\nreview flags ({len(flagged)}):")
    for memo_id, ticker, date, trigger, note in flagged:
        print(f"  {date} {ticker} (memo {memo_id}) [{trigger}] {note}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    if not (args.memo_id and args.trigger and args.note):
        raise SystemExit("review requires --memo-id --trigger --note")
    conn = sqlite3.connect(args.db)
    ledger.ensure_schema(conn)
    today = dt.datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    ledger.record_review(conn, args.memo_id, args.trigger, args.note,
                         review_date=today)
    print(f"review recorded: memo {args.memo_id} [{args.trigger}] {args.note}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("backfill", "mark", "report", "review"))
    ap.add_argument("--db", default=str(_ROOT / "data" / "kairos.db"))
    ap.add_argument("--date", default=None,
                    help="mark date (default: today ET; must be post-close)")
    ap.add_argument("--memo-id", type=int, default=None)
    ap.add_argument("--trigger", choices=("news", "manual"), default=None)
    ap.add_argument("--note", default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        stream=sys.stderr, format="%(name)s %(levelname)s %(message)s")
    return {"backfill": cmd_backfill, "mark": cmd_mark,
            "report": cmd_report, "review": cmd_review}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

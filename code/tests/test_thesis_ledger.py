"""Forward verdict ledger (thesis-verdict-ledger spec).

U1: schema — three INSERT-only tables self-owned by ledger.ensure_schema
(memo.ensure_schema additive idiom): idempotent second call, additive
column migration that never touches existing rows, and the review-move
knob in config.
"""

import sqlite3

import pytest

from kairos import config
from kairos.thesis import ledger


def _conn(tmp_path):
    return sqlite3.connect(tmp_path / "t.db")


def test_ensure_schema_second_call_is_a_no_op(tmp_path):
    conn = _conn(tmp_path)
    ledger.ensure_schema(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"verdict_ledger", "verdict_marks", "verdict_reviews"} <= tables
    conn.execute(
        "INSERT INTO verdict_ledger (memo_id, status) VALUES (7, 'open')")
    conn.commit()
    ledger.ensure_schema(conn)  # must not drop/recreate/error
    assert conn.execute(
        "SELECT memo_id, status FROM verdict_ledger").fetchall() == [(7, "open")]


def test_ensure_schema_adds_missing_column_without_touching_rows(tmp_path):
    conn = _conn(tmp_path)
    # simulate an older DB: verdict_ledger exists but lacks the `hit` column
    conn.execute(
        "CREATE TABLE verdict_ledger ("
        " memo_id INTEGER PRIMARY KEY,"
        " entry_date TEXT, entry_price REAL, spy_entry REAL,"
        " status TEXT NOT NULL DEFAULT 'open',"
        " closed_date TEXT, ticker_return REAL, spy_return REAL, alpha REAL)")
    conn.execute(
        "INSERT INTO verdict_ledger (memo_id, entry_date, entry_price,"
        " spy_entry, status) VALUES (3, '2026-07-09', 10.0, 620.0, 'open')")
    conn.commit()
    ledger.ensure_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(verdict_ledger)")}
    assert "hit" in cols
    row = conn.execute(
        "SELECT memo_id, entry_price, status, hit FROM verdict_ledger"
    ).fetchone()
    assert row == (3, 10.0, "open", None)


def test_review_move_trigger_knob_lives_in_config():
    assert isinstance(config.REVIEW_MOVE_TRIGGER_PCT, float)
    assert 0.0 < config.REVIEW_MOVE_TRIGGER_PCT < 1.0


# --- U2: open-row builder (entry = first close STRICTLY AFTER recorded_at, ET)

def test_entry_due_date_utc_prefix_trap_after_close_rolls_forward():
    # 2026-07-09T21:00Z = 17:00 EDT — the 07-09 close (16:00 ET) already
    # traded BEFORE the verdict existed; a naive UTC-date-prefix rule keeps
    # 07-09 and commits a PIT violation. Must roll to 07-10.
    assert ledger.entry_due_date("2026-07-09T21:00:00+00:00") == "2026-07-10"


def test_entry_due_date_before_close_keeps_same_day():
    # 14:00Z = 10:00 EDT, before the close -> that day's close qualifies.
    assert ledger.entry_due_date("2026-07-09T14:00:00+00:00") == "2026-07-09"


def test_entry_due_date_dst_november_est_not_fixed_utc4():
    # 2026-11-20T20:30Z = 15:30 EST (UTC-5): before the close, same day.
    # A fixed UTC-4 offset reads 16:30 -> would wrongly roll to 11-21.
    assert ledger.entry_due_date("2026-11-20T20:30:00+00:00") == "2026-11-20"


def test_entry_due_date_rejects_naive_timestamp():
    with pytest.raises(ValueError):
        ledger.entry_due_date("2026-07-09T14:00:00")


def test_open_row_picks_first_available_bar_on_or_after_due_date():
    # due 2026-07-11 (Sat): first available bar date is Monday 07-13.
    bars = {
        "2026-07-10": {"XYZ": 10.0, "SPY": 620.0},
        "2026-07-13": {"XYZ": 11.5, "SPY": 625.0},
    }
    row = ledger.open_row(7, "XYZ", "2026-07-10T22:30:11+00:00", bars)
    assert (row.entry_date, row.entry_price, row.spy_entry) == (
        "2026-07-13", 11.5, 625.0)


def test_open_row_missing_ticker_on_present_date_raises_never_fakes():
    bars = {"2026-07-09": {"SPY": 620.0}}  # XYZ absent from a traded date
    with pytest.raises(ledger.MissingBarError):
        ledger.open_row(7, "XYZ", "2026-07-09T14:00:00+00:00", bars)


def test_open_row_pends_when_no_bar_on_or_after_due_date_yet():
    bars = {"2026-07-09": {"XYZ": 10.0, "SPY": 620.0}}
    row = ledger.open_row(7, "XYZ", "2026-07-10T22:30:11+00:00", bars)
    assert (row.entry_date, row.entry_price, row.spy_entry) == (None, None, None)


# --- U3: mark appender (INSERT-only, idempotent, PIT-guarded)

def _ledger_conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "l.db")
    ledger.ensure_schema(conn)
    return conn


def test_append_mark_boundary_pair_pit(tmp_path):
    conn = _ledger_conn(tmp_path)
    # mark_date == entry_date: accepted
    assert ledger.append_mark(conn, 7, "2026-07-09", 10.5, 621.0,
                              entry_date="2026-07-09") is True
    # mark_date one day BEFORE entry_date: rejected loud
    with pytest.raises(ledger.PITViolationError):
        ledger.append_mark(conn, 7, "2026-07-08", 10.2, 619.0,
                           entry_date="2026-07-09")


def test_append_mark_rerun_same_day_writes_nothing(tmp_path):
    conn = _ledger_conn(tmp_path)
    assert ledger.append_mark(conn, 7, "2026-07-09", 10.5, 621.0,
                              entry_date="2026-07-09") is True
    assert ledger.append_mark(conn, 7, "2026-07-09", 10.5, 621.0,
                              entry_date="2026-07-09") is False
    rows = conn.execute("SELECT COUNT(*) FROM verdict_marks").fetchone()[0]
    assert rows == 1


def test_append_mark_conflicting_value_for_existing_day_raises(tmp_path):
    # validate BEFORE insert: a silent INSERT OR IGNORE would freeze the
    # first-written row and mask the conflict.
    conn = _ledger_conn(tmp_path)
    ledger.append_mark(conn, 7, "2026-07-09", 10.5, 621.0,
                       entry_date="2026-07-09")
    with pytest.raises(ledger.MarkConflictError):
        ledger.append_mark(conn, 7, "2026-07-09", 10.6, 621.0,
                           entry_date="2026-07-09")


# --- U4: move-trigger rule (at most one review per direction per lifetime)

def test_move_flags_oscillation_flags_up_direction_once():
    # entry 100: +16% cross, retreat, +17% re-cross -> ONE up flag, first date
    marks = [("2026-07-10", 116.0), ("2026-07-11", 110.0),
             ("2026-07-14", 117.0)]
    flags = ledger.move_flags(100.0, marks, already_flagged=set())
    assert flags == [("2026-07-10", "up", pytest.approx(0.16))]


def test_move_flags_below_threshold_no_flag():
    # +14% stays under the 0.15 knob (literal off the float boundary)
    assert ledger.move_flags(100.0, [("2026-07-10", 114.0)],
                             already_flagged=set()) == []


def test_move_flags_down_direction():
    marks = [("2026-07-10", 84.0)]  # -16%
    assert ledger.move_flags(100.0, marks, already_flagged=set()) == [
        ("2026-07-10", "down", pytest.approx(-0.16))]


def test_move_flags_both_directions_flag_independently():
    marks = [("2026-07-10", 116.0), ("2026-07-20", 83.0)]
    got = ledger.move_flags(100.0, marks, already_flagged=set())
    assert [(d, dirn) for d, dirn, _ in got] == [
        ("2026-07-10", "up"), ("2026-07-20", "down")]


def test_move_flags_respects_already_flagged_directions():
    marks = [("2026-07-15", 118.0)]
    assert ledger.move_flags(100.0, marks, already_flagged={"up"}) == []


# --- U5: close-out rule (first mark on/after review_date; alpha-based hit)

_MARKS = [("2026-08-01", 104.0, 660.0), ("2026-08-04", 90.0, 640.0)]


def test_close_out_short_positive_return_negative_alpha_is_hit():
    # short that ROSE +4% while SPY rose +10%: lagged the market = hit.
    c = ledger.close_out("short", 100.0, 600.0, _MARKS, review_date="2026-08-01")
    assert c.closed_date == "2026-08-01"
    assert c.ticker_return == pytest.approx(0.04)
    assert c.spy_return == pytest.approx(0.10)
    assert c.alpha == pytest.approx(-0.06)
    assert c.hit == 1


def test_close_out_long_beats_spy_is_hit():
    marks = [("2026-08-01", 120.0, 630.0)]
    c = ledger.close_out("long", 100.0, 600.0, marks, review_date="2026-08-01")
    assert c.alpha == pytest.approx(0.20 - 0.05)
    assert c.hit == 1


def test_close_out_long_lags_spy_is_miss():
    c = ledger.close_out("long", 100.0, 600.0, _MARKS, review_date="2026-08-01")
    assert c.alpha == pytest.approx(-0.06)
    assert c.hit == 0


def test_close_out_uses_first_qualifying_mark_not_a_later_one():
    c = ledger.close_out("long", 100.0, 600.0, _MARKS, review_date="2026-07-20")
    assert c.closed_date == "2026-08-01"


def test_close_out_none_when_no_mark_on_or_after_review_date():
    assert ledger.close_out("long", 100.0, 600.0, _MARKS,
                            review_date="2026-09-01") is None


# --- U7: mark_day orchestration (guard-before-fetch, per-ticker missing,
#         move-flag lifetime seam, entry fill, close-out wiring, idempotence)

import datetime as dt

from kairos.thesis import memo as memo_mod

_ET = ledger._ET


def _memo_row(conn, memo_id, ticker, *, recorded_at, direction="long",
              review_date="2026-12-01"):
    conn.execute(
        "INSERT INTO thesis_memos (id, ticker, as_of, dossier_sha256,"
        " analyst_json, adversary_json, judge_json, direction,"
        " conviction_tier, mispricing_claim, horizon_weeks, catalysts_json,"
        " tripwire_json, review_date, model_alias, agent_hashes_json,"
        " forensics_json, recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (memo_id, ticker, "2026-07-07", f"sha-{memo_id}", "{}", "{}", "{}",
         direction, "B", "claim", 8, "[]", "{}", review_date, "opus", "{}",
         "{}", recorded_at))


def _mark_db(tmp_path):
    conn = sqlite3.connect(tmp_path / "m.db")
    memo_mod.ensure_schema(conn)
    ledger.ensure_schema(conn)
    return conn


def _open(conn, memo_id, entry_date="2026-07-09", entry_price=100.0,
          spy=600.0):
    conn.execute(
        "INSERT INTO verdict_ledger (memo_id, entry_date, entry_price,"
        " spy_entry, status) VALUES (?,?,?,?, 'open')",
        (memo_id, entry_date, entry_price, spy))
    conn.commit()


_AFTER_CLOSE = dt.datetime(2026, 7, 10, 17, 0, tzinfo=_ET)


def test_mark_day_refuses_before_1615_et_without_touching_the_fetch(tmp_path):
    conn = _mark_db(tmp_path)

    def fetch_never(date):
        raise AssertionError("fetch called before the clock guard")

    now = dt.datetime(2026, 7, 10, 15, 59, tzinfo=_ET)
    with pytest.raises(ledger.PrematureMarkError):
        ledger.mark_day(conn, "2026-07-10", now_et=now, fetch_bars=fetch_never)


def test_mark_day_missing_spy_halts_with_zero_writes(tmp_path):
    conn = _mark_db(tmp_path)
    _memo_row(conn, 1, "XYZ", recorded_at="2026-07-09T00:57:00+00:00")
    _open(conn, 1)
    with pytest.raises(ledger.MissingBarError):
        ledger.mark_day(conn, "2026-07-10", now_et=_AFTER_CLOSE,
                        fetch_bars=lambda d: {"XYZ": 101.0})
    assert conn.execute("SELECT COUNT(*) FROM verdict_marks").fetchone()[0] == 0


def test_mark_day_missing_ticker_flags_and_siblings_still_mark(tmp_path):
    conn = _mark_db(tmp_path)
    _memo_row(conn, 1, "GONE", recorded_at="2026-07-09T00:57:00+00:00")
    _memo_row(conn, 2, "LIVE", recorded_at="2026-07-09T00:57:00+00:00")
    _open(conn, 1)
    _open(conn, 2)
    s = ledger.mark_day(conn, "2026-07-10", now_et=_AFTER_CLOSE,
                        fetch_bars=lambda d: {"LIVE": 104.0, "SPY": 606.0})
    assert s.marks_written == 1
    flagged = conn.execute(
        "SELECT memo_id, \"trigger\" FROM verdict_reviews").fetchall()
    assert (1, "missing_bar") in flagged


def test_mark_day_move_flag_survives_across_runs(tmp_path):
    # pre-existing 'up' move review = the lifetime seam: a later re-cross
    # writes NO new review row.
    conn = _mark_db(tmp_path)
    _memo_row(conn, 1, "XYZ", recorded_at="2026-07-09T00:57:00+00:00")
    _open(conn, 1)
    conn.execute(
        "INSERT INTO verdict_reviews (memo_id, review_date, \"trigger\", note)"
        " VALUES (1, '2026-07-10', 'move', 'up +16.0% at 2026-07-10')")
    conn.commit()
    now = dt.datetime(2026, 7, 13, 17, 0, tzinfo=_ET)
    ledger.mark_day(conn, "2026-07-13", now_et=now,
                    fetch_bars=lambda d: {"XYZ": 118.0, "SPY": 606.0})
    moves = conn.execute(
        "SELECT COUNT(*) FROM verdict_reviews WHERE \"trigger\"='move'"
    ).fetchone()[0]
    assert moves == 1


def test_mark_day_fills_entry_pending_row(tmp_path):
    conn = _mark_db(tmp_path)
    _memo_row(conn, 1, "XYZ", recorded_at="2026-07-10T22:30:11+00:00")
    conn.execute(
        "INSERT INTO verdict_ledger (memo_id, status) VALUES (1, 'open')")
    conn.commit()
    now = dt.datetime(2026, 7, 13, 17, 0, tzinfo=_ET)
    ledger.mark_day(conn, "2026-07-13", now_et=now,
                    fetch_bars=lambda d: {"XYZ": 11.5, "SPY": 625.0})
    row = conn.execute(
        "SELECT entry_date, entry_price, spy_entry FROM verdict_ledger"
        " WHERE memo_id=1").fetchone()
    assert row == ("2026-07-13", 11.5, 625.0)


def test_mark_day_closes_row_past_review_date_and_flags_pending_past_due(tmp_path):
    conn = _mark_db(tmp_path)
    _memo_row(conn, 1, "XYZ", recorded_at="2026-07-09T00:57:00+00:00",
              direction="short", review_date="2026-07-10")
    _open(conn, 1)
    # entry-pending row already past its review_date -> loud flag, stays open
    _memo_row(conn, 2, "PEND", recorded_at="2026-07-09T21:00:00+00:00",
              review_date="2026-07-10")
    conn.execute(
        "INSERT INTO verdict_ledger (memo_id, status) VALUES (2, 'open')")
    conn.commit()
    ledger.mark_day(conn, "2026-07-10", now_et=_AFTER_CLOSE,
                    fetch_bars=lambda d: {"XYZ": 104.0, "SPY": 660.0})
    st, alpha, hit = conn.execute(
        "SELECT status, alpha, hit FROM verdict_ledger WHERE memo_id=1"
    ).fetchone()
    assert st == "closed"
    assert alpha == pytest.approx(0.04 - 0.10)
    assert hit == 1  # short that lagged SPY
    st2 = conn.execute(
        "SELECT status FROM verdict_ledger WHERE memo_id=2").fetchone()[0]
    assert st2 == "open"
    assert conn.execute(
        "SELECT COUNT(*) FROM verdict_reviews WHERE memo_id=2"
        " AND \"trigger\"='missing_bar'").fetchone()[0] == 1


def test_mark_day_rerun_same_day_writes_nothing_new(tmp_path):
    conn = _mark_db(tmp_path)
    _memo_row(conn, 1, "XYZ", recorded_at="2026-07-09T00:57:00+00:00")
    _open(conn, 1)
    fetch = lambda d: {"XYZ": 101.0, "SPY": 606.0}
    s1 = ledger.mark_day(conn, "2026-07-10", now_et=_AFTER_CLOSE, fetch_bars=fetch)
    s2 = ledger.mark_day(conn, "2026-07-10", now_et=_AFTER_CLOSE, fetch_bars=fetch)
    assert s1.marks_written == 1 and s2.marks_written == 0
    assert conn.execute("SELECT COUNT(*) FROM verdict_marks").fetchone()[0] == 1


# --- U8: report aggregation (pin normalization, zero-closed None) + review

def test_pin_key_flat_legacy_shape():
    j = ('{"analyst": "' + "a" * 64 + '", "adversary": "' + "b" * 64 +
         '", "judge": "' + "c" * 64 + '"}')
    assert ledger.pin_key(j) == "aaaaaaaaaaaa:bbbbbbbbbbbb:cccccccccccc"


def test_pin_key_nested_scorer_pin_shape_carries_efforts():
    j = ('{"analyst": {"sha256": "' + "a" * 64 + '", "effort": "max"},'
         ' "adversary": {"sha256": "' + "b" * 64 + '", "effort": "max"},'
         ' "judge": {"sha256": "' + "c" * 64 + '", "effort": "xhigh"}}')
    assert ledger.pin_key(j) == ("aaaaaaaaaaaa:bbbbbbbbbbbb:cccccccccccc"
                                 "|analyst=max,adversary=max,judge=xhigh")


def test_report_aggregates_zero_closed_group_prints_none_not_nan():
    rows = [("B", "long", "p1", "rs90", "open", None, None),
            ("B", "long", "p1", "rs90", "open", None, None)]
    (g,) = ledger.report_aggregates(rows)
    assert (g["n"], g["open"], g["closed"]) == (2, 2, 0)
    assert g["mean_alpha"] is None and g["hit_rate"] is None


def test_report_aggregates_hand_computed_mean_and_hit_rate():
    rows = [("B", "short", "p1", "rs90", "closed", -0.06, 1),
            ("B", "short", "p1", "rs90", "closed", 0.02, 0),
            ("B", "short", "p1", "rs90", "open", None, None)]
    (g,) = ledger.report_aggregates(rows)
    assert g["closed"] == 2
    assert g["mean_alpha"] == pytest.approx((-0.06 + 0.02) / 2)
    assert g["hit_rate"] == pytest.approx(0.5)


def test_record_review_row_visible(tmp_path):
    conn = _mark_db(tmp_path)
    _memo_row(conn, 1, "XYZ", recorded_at="2026-07-09T00:57:00+00:00")
    _open(conn, 1)
    ledger.record_review(conn, 1, "manual", "thesis intact, noise",
                         review_date="2026-07-15")
    got = conn.execute(
        'SELECT memo_id, "trigger", note FROM verdict_reviews').fetchall()
    assert got == [(1, "manual", "thesis intact, noise")]


# --- reviewer findings 2026-07-10 ---

def test_mark_day_mid_sweep_failure_rolls_back_all_rows(tmp_path):
    # F1: append_mark's inner commit defeated the sweep transaction — a
    # MarkConflictError on row 2 must leave row 1's mark unwritten too.
    conn = _mark_db(tmp_path)
    _memo_row(conn, 1, "AAA", recorded_at="2026-07-09T00:57:00+00:00")
    _memo_row(conn, 2, "BBB", recorded_at="2026-07-09T00:57:00+00:00")
    _open(conn, 1)
    _open(conn, 2)
    conn.execute("INSERT INTO verdict_marks (memo_id, mark_date, close,"
                 " spy_close) VALUES (2, '2026-07-10', 999.0, 606.0)")
    conn.commit()
    with pytest.raises(ledger.MarkConflictError):
        ledger.mark_day(conn, "2026-07-10", now_et=_AFTER_CLOSE,
                        fetch_bars=lambda d: {"AAA": 101.0, "BBB": 102.0,
                                              "SPY": 606.0})
    got = conn.execute(
        "SELECT memo_id, close FROM verdict_marks ORDER BY memo_id").fetchall()
    assert got == [(2, 999.0)]  # only the pre-existing row; AAA rolled back


def test_record_review_unknown_memo_id_fails_loud(tmp_path):
    # F2: a typo'd memo_id must raise, never insert an orphan the report
    # JOIN silently drops.
    conn = _mark_db(tmp_path)
    with pytest.raises(ledger.UnknownMemoError):
        ledger.record_review(conn, 9999, "manual", "typo", 
                             review_date="2026-07-15")
    assert conn.execute("SELECT COUNT(*) FROM verdict_reviews").fetchone()[0] == 0


# --- premove U6: cohort slice in the readout (specs/premove-cohort.md) ---

def test_report_aggregates_splits_cohorts():
    rows = [("B", "long", "p1", "rs90", "closed", 0.04, 1),
            ("B", "long", "p1", "premove", "closed", -0.02, 0),
            ("B", "long", "p1", "rs90", "open", None, None)]
    groups = ledger.report_aggregates(rows)
    assert len(groups) == 2
    by_cohort = {g["cohort"]: g for g in groups}
    assert by_cohort["rs90"]["n"] == 2 and by_cohort["rs90"]["closed"] == 1
    assert by_cohort["premove"]["n"] == 1
    assert by_cohort["premove"]["mean_alpha"] == pytest.approx(-0.02)


def test_cmd_report_renders_cohort_column(tmp_path, capsys):
    import argparse
    import importlib.util
    from pathlib import Path as _P

    script = _P(__file__).resolve().parents[2] / "scripts" / "thesis_ledger.py"
    spec = importlib.util.spec_from_file_location("thesis_ledger_cli", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    from kairos.thesis import memo as memo_mod
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    memo_mod.ensure_schema(conn)
    ledger.ensure_schema(conn)
    for ticker, cohort in (("MU", "rs90"), ("GEV", "premove")):
        conn.execute(
            "INSERT INTO thesis_memos (ticker, as_of, dossier_sha256,"
            " analyst_json, adversary_json, judge_json, direction,"
            " conviction_tier, mispricing_claim, horizon_weeks,"
            " catalysts_json, tripwire_json, review_date, model_alias,"
            " agent_hashes_json, forensics_json, recorded_at, cohort)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ticker, "2026-07-10", ticker.lower() * 16, "{}", "{}", "{}",
             "long", "B", "claim", 8, "[]", "{}", "2026-09-01", "opus",
             '{"analyst": "a1", "adversary": "a2", "judge": "a3"}', "{}",
             "2026-07-10T20:00:00+00:00", cohort))
        (memo_id,) = conn.execute(
            "SELECT id FROM thesis_memos WHERE ticker = ?", (ticker,)).fetchone()
        conn.execute("INSERT INTO verdict_ledger (memo_id) VALUES (?)", (memo_id,))
    conn.commit()
    conn.close()

    cli.cmd_report(argparse.Namespace(db=str(db)))
    out = capsys.readouterr().out
    header, *lines = [ln for ln in out.splitlines() if ln.strip()]
    assert "cohort" in header
    assert any("premove" in ln for ln in lines)
    assert any("rs90" in ln for ln in lines)


# --- thesis-judges-v9 U2 RED: per-seat pin_key -------------------------------

def _v9_pin_json(fable_model="fable"):
    return ('{"analyst": {"sha256": "' + "a" * 64 + '", "effort": "max"},'
            ' "adversary": {"sha256": "' + "b" * 64 + '", "effort": "max"},'
            ' "judge_opus": {"sha256": "' + "c" * 64 + '", "effort": "xhigh",'
            ' "model": "opus"},'
            ' "judge_fable": {"sha256": "' + "c" * 64 + '", "effort": "xhigh",'
            ' "model": "' + fable_model + '"}}')


def test_pin_key_v9_per_seat_shape_carries_models():
    assert ledger.pin_key(_v9_pin_json()) == (
        "aaaaaaaaaaaa:bbbbbbbbbbbb:cccccccccccc:cccccccccccc"
        "|analyst=max,adversary=max,judge_opus=xhigh,judge_fable=xhigh"
        "|judge_opus=opus,judge_fable=fable")


def test_pin_key_v9_seat_model_change_changes_key():
    # the failure this prevents: a fable seat silently degraded to opus
    # landing in the SAME evidence window as true opus+fable memos
    assert ledger.pin_key(_v9_pin_json()) != \
        ledger.pin_key(_v9_pin_json(fable_model="opus"))

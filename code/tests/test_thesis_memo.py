"""thesis-engine unit 5b RED: memo contract checks (fail-loud, code not
judgment) + PIT journal write.

The workflow's agent outputs are untrusted input: record_memo validates the
mechanical contract BEFORE anything lands in the DB — tripwire observable and
dated, citations resolve to dossier doc ids, every flagged forensic ratio
addressed. A judge cannot waive these.
"""

from __future__ import annotations

import sqlite3

import pytest

from kairos.thesis import memo


def _memo(**over):
    base = dict(
        ticker="MU",
        as_of="2026-07-07",
        dossier_sha256="a" * 64,
        dossier_doc_ids=("P1", "X1", "F1", "F2", "N1", "I1", "R1"),
        forensics={"ar_growth": 0.322, "revenue_growth": 0.489,
                   "ni_exceeds_ocf_years": 0, "dilution_rate": 0.01},
        analyst={"dimensions": {"business_quality": {"score": 4, "citations": ["F1"]},
                                "growth": {"score": 5, "citations": ["F1", "R1"]}},
                 "forensic_notes": {}},
        adversary={"case": "DRAM cyclicality...",
                   "case_citations": ["F2"], "findings": []},
        judge={"tier": "A", "decisive_citations": ["F1", "N1"],
               "rationale": "guide above consensus..."},
        direction="long",
        conviction_tier="A",
        mispricing_claim="market prices DRAM peak; evidence supports supercycle",
        horizon_weeks=10,
        catalysts=[{"date": "2026-09-24", "event": "FQ4 earnings"}],
        tripwire={"condition": "DRAM spot price below $X for 10 sessions",
                  "review_by": "2026-08-15"},
        review_date="2026-10-01",
        model_alias="fable",
        agent_hashes={"analyst": "h1", "adversary": "h2", "judge": "h3"},
    )
    base.update(over)
    return memo.MemoRecord(**base)


def _db():
    conn = sqlite3.connect(":memory:")
    memo.ensure_schema(conn)
    return conn


def test_complete_memo_writes_pit_row():
    conn = _db()
    memo.record_memo(conn, _memo())
    row = conn.execute(
        "SELECT ticker, conviction_tier, dossier_sha256, model_alias, recorded_at "
        "FROM thesis_memos").fetchone()
    assert row[0] == "MU" and row[1] == "A" and row[2] == "a" * 64
    assert row[3] == "fable"
    assert row[4]  # PIT timestamp present


def test_citation_to_unknown_doc_id_raises():
    bad = _memo(judge={"tier": "A", "decisive_citations": ["F9"],
                       "rationale": "..."})
    with pytest.raises(memo.ContractViolation, match="F9"):
        memo.record_memo(_db(), bad)


def test_tripwire_missing_or_undated_raises():
    with pytest.raises(memo.ContractViolation, match="tripwire"):
        memo.record_memo(_db(), _memo(tripwire=None))
    with pytest.raises(memo.ContractViolation, match="tripwire"):
        memo.record_memo(_db(), _memo(
            tripwire={"condition": "vibes deteriorate", "review_by": ""}))


def test_flagged_forensic_unaddressed_raises():
    # dilution 26% breaches the 5%/yr flag threshold; memo must address it
    flagged = _memo(
        forensics={"ar_growth": 0.1, "revenue_growth": 0.2,
                   "ni_exceeds_ocf_years": 0, "dilution_rate": 0.26})
    with pytest.raises(memo.ContractViolation, match="dilution"):
        memo.record_memo(_db(), flagged)
    # same ratios WITH an addressing note passes
    addressed = _memo(
        forensics=flagged.forensics,
        analyst={"dimensions": {"growth": {"score": 4, "citations": ["F1"]}},
                 "forensic_notes": {"dilution_rate":
                                    {"note": "IPO lockup conversion [F2]",
                                     "citations": ["F2"]}}})
    conn = _db()
    memo.record_memo(conn, addressed)
    assert conn.execute("SELECT COUNT(*) FROM thesis_memos").fetchone()[0] == 1


def test_flag_thresholds():
    assert memo.flagged_ratios(
        {"ar_growth": 0.80, "revenue_growth": 0.20,
         "ni_exceeds_ocf_years": 0, "dilution_rate": 0.0}) == ["ar_growth"]
    assert memo.flagged_ratios(
        {"ar_growth": 0.10, "revenue_growth": 0.20,
         "ni_exceeds_ocf_years": 2, "dilution_rate": 0.06}) == [
        "dilution_rate", "ni_exceeds_ocf_years"]
    assert memo.flagged_ratios(
        {"ar_growth": None, "revenue_growth": None,
         "ni_exceeds_ocf_years": 0, "dilution_rate": None}) == []


def test_from_workflow_judge_tier_is_final():
    wf = {
        "ticker": "MU",
        "analyst": {"dimensions": {"growth": {"score": 5, "claims": "...",
                                              "citations": ["F1"]}},
                    "forensic_notes": {},
                    "direction": "long",      # v7: no conviction_tier
                    "mispricing_claim": "market prices peak; evidence says cycle",
                    "horizon_weeks": 10,
                    "catalysts": [{"date": "2026-09-24", "event": "FQ4"}],
                    "tripwire": {"condition": "DRAM spot < X 10 sessions",
                                 "review_by": "2026-08-15"},
                    "review_date": "2026-10-01"},
        "adversary": {"bear_case": "...", "bear_citations": ["F2"],
                      "findings": []},
        "judge": {"tier": "C", "rationale": "...", "decisive_citations": ["F1"],
                  "adversary_adjudication": []},
    }
    manifest = {"ticker": "MU", "as_of": "2026-07-07", "sha256": "b" * 64,
                "doc_ids": ["P1", "X1", "F1", "F2"],
                "forensics": {"ar_growth": 0.1, "revenue_growth": 0.2,
                              "ni_exceeds_ocf_years": 0, "dilution_rate": 0.0}}
    rec = memo.from_workflow(wf, manifest, model_alias="opus",
                             agent_hashes={"analyst": "h1", "adversary": "h2",
                                           "judge": "h3"})
    assert rec.conviction_tier == "C"      # judge's tier, analyst has none
    assert rec.dossier_sha256 == "b" * 64
    assert rec.direction == "long"


def test_from_workflow_direction_comes_from_judge():
    wf = {
        "ticker": "GEV",
        "analyst": {"dimensions": {"growth": {"score": 2, "claims": "...",
                                              "citations": ["F1"]}},
                    "forensic_notes": {},
                    "direction": "long",
                    "mispricing_claim": "...",
                    "horizon_weeks": 3,
                    "catalysts": [],
                    "tripwire": {"condition": "backlog stalls vs $200B path",
                                 "review_by": "2026-08-05"},
                    "review_date": "2026-08-05"},
        "adversary": {"bear_case": "...", "bear_citations": ["N6"],
                      "findings": []},
        "judge": {"tier": "B", "direction": "short", "rationale": "...",
                  "decisive_citations": ["N6"], "adversary_adjudication": []},
    }
    manifest = {"ticker": "GEV", "as_of": "2026-07-07", "sha256": "c" * 64,
                "doc_ids": ["P1", "X1", "F1", "N6"],
                "forensics": {"ar_growth": 0.1, "revenue_growth": 0.2,
                              "ni_exceeds_ocf_years": 0, "dilution_rate": 0.0}}
    rec = memo.from_workflow(wf, manifest, model_alias="opus:max",
                             agent_hashes={"analyst": "h", "adversary": "h",
                                           "judge": "h"})
    assert rec.direction == "short"   # judge's direction, not hardcoded long


def test_bracketed_citations_resolve_to_bare_doc_ids():
    # live (EZPW v4 run): one analyst emitted "[E1]"-style citations while
    # the manifest doc_ids are bare "E1" -- a formatting variance, not an
    # unknown source; the checker normalizes, it does not reject
    ok = _memo(judge={"tier": "A", "decisive_citations": ["[F1]", "[N1]"],
                      "rationale": "..."})
    memo.record_memo(_db(), ok)  # must not raise
    still_bad = _memo(judge={"tier": "A", "decisive_citations": ["[F9]"],
                             "rationale": "..."})
    with pytest.raises(memo.ContractViolation, match="F9"):
        memo.record_memo(_db(), still_bad)


# ---- thesis-debate-v2 unit 2 RED: v7 shapes + ensemble integrity ----

def _judge_payload(tier, direction, cites=("F1",)):
    return {"tier": tier, "direction": direction, "rationale": "...",
            "decisive_citations": list(cites), "adversary_adjudication": []}


def test_v7_ensemble_mismatch_rejected():
    # 2-1 direction split recomputes to C; a payload claiming B must void.
    split_judges = [_judge_payload("B", "long"), _judge_payload("B", "long"),
                    _judge_payload("B", "short")]
    bad = _memo(judge={"tier": "B", "direction": "long",
                       "judges": split_judges},
                conviction_tier="B")
    with pytest.raises(memo.ContractViolation, match="ensemble"):
        memo.record_memo(_db(), bad)


def test_v7_consistent_ensemble_records():
    judges = [_judge_payload("B", "long"), _judge_payload("A", "long"),
              _judge_payload("C", "long")]
    ok = _memo(judge={"tier": "B", "direction": "long", "judges": judges},
               conviction_tier="B")
    conn = _db()
    memo.record_memo(conn, ok)  # must not raise
    assert conn.execute("SELECT COUNT(*) FROM thesis_memos").fetchone()[0] == 1


def test_adversary_finding_citations_checked_against_doc_ids():
    bad = _memo(adversary={"case": "...", "case_citations": ["F1"],
                           "findings": [{"kind": "risk", "finding": "...",
                                         "citations": ["Z9"]}]})
    with pytest.raises(memo.ContractViolation, match="Z9"):
        memo.record_memo(_db(), bad)


def test_every_ensemble_judges_citations_checked():
    judges = [_judge_payload("B", "long"), _judge_payload("B", "long"),
              _judge_payload("B", "long", cites=("Q7",))]
    bad = _memo(judge={"tier": "B", "direction": "long", "judges": judges},
                conviction_tier="B")
    with pytest.raises(memo.ContractViolation, match="Q7"):
        memo.record_memo(_db(), bad)


def test_from_workflow_v7_shape_maps_aggregate():
    judges = [_judge_payload("B", "short"), _judge_payload("B", "short"),
              _judge_payload("A", "short")]
    wf = {
        "ticker": "ATI",
        "analyst": {"dimensions": {"growth": {"score": 3, "claims": "...",
                                              "citations": ["F1"]}},
                    "forensic_notes": {},
                    "direction": "short",     # v7: no conviction_tier
                    "mispricing_claim": "...",
                    "horizon_weeks": 6,
                    "catalysts": [],
                    "tripwire": {"condition": "titanium ASP prints below X",
                                 "review_by": "2026-08-20"},
                    "review_date": "2026-09-01"},
        "adversary": {"bear_case": "...", "bear_citations": ["F1"],
                      "findings": []},         # v7: no verdict, no direction
        "judge": {"tier": "B", "direction": "short", "judges": judges},
    }
    manifest = {"ticker": "ATI", "as_of": "2026-07-07", "sha256": "d" * 64,
                "doc_ids": ["P1", "X1", "F1"],
                "forensics": {"ar_growth": 0.1, "revenue_growth": 0.2,
                              "ni_exceeds_ocf_years": 0, "dilution_rate": 0.0}}
    rec = memo.from_workflow(wf, manifest, model_alias="opus",
                             agent_hashes={"analyst": "h", "adversary": "h",
                                           "judge": "h"})
    assert rec.conviction_tier == "B"     # median of A,B,B
    assert rec.direction == "short"
    memo.record_memo(_db(), rec)          # full contract passes end-to-end


# ---- thesis-debate-v2 unit 4 RED: scorer pin with per-role effort ----

def test_scorer_pin_hashes_files_and_carries_effort(tmp_path):
    a = tmp_path / "analyst.md"; a.write_text("analyst prompt v7")
    j = tmp_path / "judge.md"; j.write_text("judge prompt v7")
    import hashlib
    pin = memo.scorer_pin({"analyst": a, "judge": j},
                          efforts={"analyst": "max", "judge": "xhigh"})
    assert pin["analyst"]["sha256"] == hashlib.sha256(
        b"analyst prompt v7").hexdigest()   # independent recompute
    assert pin["analyst"]["effort"] == "max"
    assert pin["judge"]["effort"] == "xhigh"


def test_scorer_pin_missing_effort_for_role_raises():
    with pytest.raises(memo.ContractViolation, match="effort"):
        memo.scorer_pin({"analyst": __file__}, efforts={})


# ---- thesis-debate-v3 U1 RED: v8 shapes (two directional temperaments) ------

def _steelman(not_direction="short", nd_cites=("F1",),
              tiers=(("B", ("F1",)), ("C", ("F2",)))):
    return {"not_direction": not_direction,
            "not_direction_citations": list(nd_cites),
            "not_tiers": [{"tier": t, "why": "...", "citations": list(c)}
                          for t, c in tiers]}


def test_ra_case_citations_checked_against_doc_ids():
    # v8 rename bear_case/bear_citations -> case/case_citations: the walk
    # must follow the NEW key; a vacuous walk of the absent old key would
    # let this bad citation record silently
    bad = _memo(adversary={"case": "...", "case_citations": ["F9"],
                           "findings": []})
    with pytest.raises(memo.ContractViolation, match="F9"):
        memo.record_memo(_db(), bad)


def test_analyst_steelman_citations_checked_against_doc_ids():
    bad = _memo(analyst={"dimensions": {"growth": {"score": 4,
                                                   "citations": ["F1"]}},
                         "forensic_notes": {},
                         "direction": "long", "tier": "B",
                         "steelman": _steelman(nd_cites=("Z8",))})
    with pytest.raises(memo.ContractViolation, match="Z8"):
        memo.record_memo(_db(), bad)


def test_ra_steelman_citations_checked_against_doc_ids():
    bad = _memo(adversary={"case": "...", "case_citations": ["F1"],
                           "findings": [],
                           "direction": "long", "tier": "C",
                           "steelman": _steelman(
                               tiers=(("A", ("Q9",)), ("C", ("F2",))))})
    with pytest.raises(memo.ContractViolation, match="Q9"):
        memo.record_memo(_db(), bad)


def _v8_wf(judges):
    return {
        "ticker": "MU",
        "analyst": {"dimensions": {"growth": {"score": 5, "claims": "...",
                                              "citations": ["F1"]}},
                    "forensic_notes": {},
                    "direction": "long", "tier": "A",
                    "steelman": _steelman(),
                    "mispricing_claim": "market prices peak; evidence says cycle",
                    "horizon_weeks": 10,
                    "catalysts": [{"date": "2026-09-24", "event": "FQ4"}],
                    "tripwire": {"condition": "DRAM spot < X 10 sessions",
                                 "review_by": "2026-08-15"},
                    "review_date": "2026-10-01"},
        "adversary": {"case": "quality long at a cyclical discount",
                      "case_citations": ["F2"], "findings": [],
                      "direction": "long", "tier": "B",
                      "steelman": _steelman(not_direction="short",
                                            nd_cites=("F2",),
                                            tiers=(("A", ("F1",)),
                                                   ("C", ("F2",))))},
        "judge": {"tier": "B", "direction": "long", "judges": judges},
    }


_V8_MANIFEST = {"ticker": "MU", "as_of": "2026-07-10", "sha256": "e" * 64,
                "doc_ids": ["P1", "X1", "F1", "F2"],
                "forensics": {"ar_growth": 0.1, "revenue_growth": 0.2,
                              "ni_exceeds_ocf_years": 0, "dilution_rate": 0.0}}


def test_from_workflow_v8_shape_records_end_to_end():
    # both seats directional with tier + steelman; RA = case + findings, no
    # dimensions; judge tier/direction stay the record's verdict
    judges = [_judge_payload("B", "long"), _judge_payload("A", "long"),
              _judge_payload("B", "long")]
    rec = memo.from_workflow(_v8_wf(judges), _V8_MANIFEST, model_alias="opus",
                             agent_hashes={"analyst": "h", "adversary": "h",
                                           "judge": "h"})
    assert rec.conviction_tier == "B" and rec.direction == "long"
    assert rec.adversary["tier"] == "B"      # carried for the retro loop
    memo.record_memo(_db(), rec)             # full v8 contract end-to-end


def test_v8_ensemble_mismatch_still_rejected():
    judges = [_judge_payload("B", "long"), _judge_payload("B", "long"),
              _judge_payload("B", "short")]  # recomputes to C
    rec = memo.from_workflow(_v8_wf(judges), _V8_MANIFEST, model_alias="opus",
                             agent_hashes={"analyst": "h", "adversary": "h",
                                           "judge": "h"})
    with pytest.raises(memo.ContractViolation, match="ensemble"):
        memo.record_memo(_db(), rec)


def test_steelman_not_tiers_must_be_exactly_the_two_unselected():
    # completeness lives here, not JSON schema: the flat dialect can say
    # "exactly 2 items" but not "the 2 tiers you did NOT pick"
    dupe = _memo(analyst={
        "dimensions": {"growth": {"score": 4, "citations": ["F1"]}},
        "forensic_notes": {}, "direction": "long", "tier": "A",
        "steelman": _steelman(tiers=(("A", ("F1",)), ("C", ("F2",))))})
    with pytest.raises(memo.ContractViolation, match="steelman"):
        memo.record_memo(_db(), dupe)  # lists its OWN tier A

    ra_short = _memo(adversary={
        "case": "...", "case_citations": ["F1"], "findings": [],
        "direction": "long", "tier": "C",
        "steelman": _steelman(tiers=(("A", ("F1",)), ("A", ("F2",))))})
    with pytest.raises(memo.ContractViolation, match="steelman"):
        memo.record_memo(_db(), ra_short)  # duplicate, B never argued


def test_steelman_not_direction_echoing_own_direction_rejected():
    # reviewer finding: the schema enum can't express != the seat's own
    # direction — same class as the not_tiers gap; a seat "steelmanning"
    # its own direction defeats the contract silently
    echo = _memo(analyst={
        "dimensions": {"growth": {"score": 4, "citations": ["F1"]}},
        "forensic_notes": {}, "direction": "long", "tier": "A",
        "steelman": _steelman(not_direction="long",
                              tiers=(("B", ("F1",)), ("C", ("F2",))))})
    with pytest.raises(memo.ContractViolation, match="steelman"):
        memo.record_memo(_db(), echo)


def test_legacy_bear_citations_still_checked_on_v7_re_record():
    # reviewer finding: --era v7 rebuild + record is a live supported path;
    # the v8 rename must not leave legacy bear_citations silently unchecked
    bad = _memo(adversary={"bear_case": "...", "bear_citations": ["F9"],
                           "findings": []})
    with pytest.raises(memo.ContractViolation, match="F9"):
        memo.record_memo(_db(), bad)


def test_non_iso_review_dates_rejected():
    # review_date drives ledger.close_out via lexicographic compare; a
    # non-ISO value silently strands the row open — parse-check, not prose
    with pytest.raises(memo.ContractViolation, match="review_date"):
        memo.record_memo(_db(), _memo(review_date="next quarter"))
    with pytest.raises(memo.ContractViolation, match="review_date"):
        memo.record_memo(_db(), _memo(review_date="2026-13-45"))
    with pytest.raises(memo.ContractViolation, match="review_by"):
        memo.record_memo(_db(), _memo(
            tripwire={"condition": "DRAM spot < X", "review_by": "Q3-ish"}))


def test_steelman_with_both_unselected_tiers_passes():
    ok = _memo(analyst={
        "dimensions": {"growth": {"score": 4, "citations": ["F1"]}},
        "forensic_notes": {}, "direction": "long", "tier": "A",
        "steelman": _steelman(tiers=(("B", ("F1",)), ("C", ("F2",))))})
    conn = _db()
    memo.record_memo(conn, ok)
    assert conn.execute("SELECT COUNT(*) FROM thesis_memos").fetchone()[0] == 1


# -- thesis-regime-v1 U4: market-context columns + citation contract ----------

_OLD_SCHEMA = """
CREATE TABLE thesis_memos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT NOT NULL,
    as_of            TEXT NOT NULL,
    dossier_sha256   TEXT NOT NULL,
    analyst_json     TEXT NOT NULL,
    adversary_json   TEXT NOT NULL,
    judge_json       TEXT NOT NULL,
    direction        TEXT NOT NULL,
    conviction_tier  TEXT NOT NULL,
    mispricing_claim TEXT NOT NULL,
    horizon_weeks    INTEGER NOT NULL,
    catalysts_json   TEXT NOT NULL,
    tripwire_json    TEXT NOT NULL,
    review_date      TEXT NOT NULL,
    model_alias      TEXT NOT NULL,
    agent_hashes_json TEXT NOT NULL,
    forensics_json   TEXT NOT NULL,
    recorded_at      TEXT NOT NULL,
    UNIQUE (ticker, as_of, dossier_sha256)
);
"""


def test_memo_journals_market_context_when_run_carried_a_block():
    conn = _db()
    memo.record_memo(conn, _memo(
        market_context_text="MARKET CONTEXT ... NOT citable evidence ...",
        market_context_sha256="b" * 64,
    ))
    row = conn.execute(
        "SELECT market_context_text, market_context_sha256 FROM thesis_memos"
    ).fetchone()
    assert row == ("MARKET CONTEXT ... NOT citable evidence ...", "b" * 64)


def test_memo_market_context_columns_null_when_run_had_no_block():
    conn = _db()
    memo.record_memo(conn, _memo())
    row = conn.execute(
        "SELECT market_context_text, market_context_sha256 FROM thesis_memos"
    ).fetchone()
    assert row == (None, None)


def test_memo_citing_market_block_as_evidence_rejected():
    # The market block deliberately carries NO dossier doc id: any handle an
    # agent invents for it ("M1") is an unknown citation and must reject,
    # even on a record that carries the block itself.
    conn = _db()
    rec = _memo(
        judge={"tier": "B", "decisive_citations": ["F1", "M1"],
               "rationale": "regime-weighted"},
        market_context_text="MARKET CONTEXT ...",
        market_context_sha256="b" * 64,
    )
    with pytest.raises(memo.ContractViolation, match="M1"):
        memo.record_memo(conn, rec)
    assert conn.execute("SELECT COUNT(*) FROM thesis_memos").fetchone()[0] == 0


def test_ensure_schema_migrates_pre_regime_db_additively():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_OLD_SCHEMA)
    conn.execute(
        "INSERT INTO thesis_memos (ticker, as_of, dossier_sha256, analyst_json,"
        " adversary_json, judge_json, direction, conviction_tier,"
        " mispricing_claim, horizon_weeks, catalysts_json, tripwire_json,"
        " review_date, model_alias, agent_hashes_json, forensics_json,"
        " recorded_at) VALUES ('EZPW','2026-07-08','c','{}','{}','{}','long',"
        " 'B','claim',8,'[]','{}','2026-09-01','fable','{}','{}','t')")
    conn.commit()
    memo.ensure_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(thesis_memos)")}
    assert {"market_context_text", "market_context_sha256"} <= cols
    row = conn.execute(
        "SELECT ticker, market_context_text, market_context_sha256"
        " FROM thesis_memos").fetchone()
    assert row == ("EZPW", None, None)
    assert conn.execute("SELECT COUNT(*) FROM thesis_memos").fetchone()[0] == 1


def test_ensure_schema_idempotent_on_migrated_db():
    conn = _db()
    memo.ensure_schema(conn)  # second run must not raise duplicate-column
    cols = {r[1] for r in conn.execute("PRAGMA table_info(thesis_memos)")}
    assert {"market_context_text", "market_context_sha256"} <= cols


# --- premove U5: cohort column (specs/premove-cohort.md) ---

def test_cohort_column_added_to_existing_db_old_rows_read_rs90():
    """Pre-migration DB (no cohort column) + one live-era row: ensure_schema
    adds the column and the old row reads 'rs90', never NULL — the readout
    slices on this value."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE thesis_memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, as_of TEXT NOT NULL,
            dossier_sha256 TEXT NOT NULL, analyst_json TEXT NOT NULL,
            adversary_json TEXT NOT NULL, judge_json TEXT NOT NULL,
            direction TEXT NOT NULL, conviction_tier TEXT NOT NULL,
            mispricing_claim TEXT NOT NULL, horizon_weeks INTEGER NOT NULL,
            catalysts_json TEXT NOT NULL, tripwire_json TEXT NOT NULL,
            review_date TEXT NOT NULL, model_alias TEXT NOT NULL,
            agent_hashes_json TEXT NOT NULL, forensics_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            UNIQUE (ticker, as_of, dossier_sha256))""")
    conn.execute(
        "INSERT INTO thesis_memos (ticker, as_of, dossier_sha256, analyst_json,"
        " adversary_json, judge_json, direction, conviction_tier,"
        " mispricing_claim, horizon_weeks, catalysts_json, tripwire_json,"
        " review_date, model_alias, agent_hashes_json, forensics_json,"
        " recorded_at) VALUES ('MU','2026-07-07','a','{}','{}','{}','long',"
        " 'B','claim',8,'[]','{}','2026-09-01','fable','{}','{}','t')")
    conn.commit()
    memo.ensure_schema(conn)
    assert conn.execute(
        "SELECT cohort FROM thesis_memos WHERE ticker='MU'").fetchone() == ("rs90",)


def test_from_workflow_threads_manifest_cohort():
    judges = [_judge_payload("B", "long"), _judge_payload("B", "long"),
              _judge_payload("B", "long")]
    tagged = dict(_V8_MANIFEST, cohort="premove")
    rec = memo.from_workflow(_v8_wf(judges), tagged, model_alias="opus",
                             agent_hashes={"analyst": "h", "adversary": "h",
                                           "judge": "h"})
    assert rec.cohort == "premove"
    untagged = memo.from_workflow(_v8_wf(judges), _V8_MANIFEST,
                                  model_alias="opus",
                                  agent_hashes={"analyst": "h",
                                                "adversary": "h", "judge": "h"})
    assert untagged.cohort == "rs90"


def test_record_memo_persists_cohort():
    conn = _db()
    memo.record_memo(conn, _memo(cohort="premove"))
    assert conn.execute(
        "SELECT cohort FROM thesis_memos").fetchone() == ("premove",)


# ---- thesis-judges-v9 U2 RED: per-seat judge pins ---------------------------

def test_scorer_pin_carries_per_role_model_when_declared(tmp_path):
    j = tmp_path / "judge.md"; j.write_text("judge prompt v9")
    pin = memo.scorer_pin(
        {"judge_opus": j, "judge_fable": j},
        efforts={"judge_opus": "xhigh", "judge_fable": "xhigh"},
        models={"judge_opus": "opus", "judge_fable": "fable"})
    assert pin["judge_opus"]["model"] == "opus"
    assert pin["judge_fable"]["model"] == "fable"
    # same prompt file -> same sha; the MODEL is what tells the seats apart
    assert pin["judge_opus"]["sha256"] == pin["judge_fable"]["sha256"]


def test_scorer_pin_without_models_has_no_model_key(tmp_path):
    a = tmp_path / "analyst.md"; a.write_text("analyst prompt")
    pin = memo.scorer_pin({"analyst": a}, efforts={"analyst": "max"})
    assert "model" not in pin["analyst"]  # v8 pins keep their exact shape


def test_judge_seat_roles_two_judges_maps_to_per_seat_roles():
    records = [{"judge": {"judges": [{"seat": "opus"}, {"seat": "fable"}]}}]
    assert memo.judge_seat_roles(records) == (
        "analyst", "adversary", "judge_opus", "judge_fable")


def test_judge_seat_roles_three_judges_keeps_single_judge_role():
    records = [{"judge": {"judges": [{}, {}, {}]}}]
    assert memo.judge_seat_roles(records) == ("analyst", "adversary", "judge")


def test_judge_seat_roles_mixed_eras_raises():
    records = [{"judge": {"judges": [{}, {}, {}]}},
               {"judge": {"judges": [{"seat": "opus"}, {"seat": "fable"}]}}]
    with pytest.raises(memo.ContractViolation, match="mixed"):
        memo.judge_seat_roles(records)


def test_judge_seat_roles_empty_records_refuses():
    # a rebuild that emitted zero records must not silently pin v8-shaped
    # (director note, U2 boundary)
    with pytest.raises(memo.ContractViolation, match="zero"):
        memo.judge_seat_roles([])
# ---- thesis-scale-v16 U3: p_outperform contract (v15 p_beat block amended
# in-kind: band-mismatch voids -> bad/missing-p voids naming the seat;
# p_beat_band boundary pins superseded by test_band_from_p_boundaries_exact;
# consistent-seats-record-fine -> the v16 end-to-end record test;
# legacy-without-p_beat -> legacy-without-p_outperform, same guarantee) ----
# Era dispatch is judge-payload presence: m.judge carrying p_outperform is
# a v16 memo (every seat must then carry a valid p); absence -> the frozen
# v8/v9 path, untouched.


def _steelman_v16(not_direction="short", nd_cites=("F1",),
                  hi=("F1",), lo=("F2",)):
    return {"not_direction": not_direction,
            "not_direction_citations": list(nd_cites),
            "not_higher_conviction": {"why": "...", "citations": list(hi)},
            "not_lower_conviction": {"why": "...", "citations": list(lo)}}


def _v16_judge(seat, p):
    return {"seat": seat, "p_outperform": p, "rationale": "...",
            "decisive_citations": ["F1"], "adversary_adjudication": []}


def _v16_memo(**over):
    # aggregate of (0.72, 0.81) same-side -> p 0.72 -> long/B, hand-derived
    judges = [_v16_judge("opus", 0.72), _v16_judge("fable", 0.81)]
    base = dict(
        analyst={"dimensions": {"growth": {"score": 4, "citations": ["F1"]}},
                 "forensic_notes": {}, "p_outperform": 0.78,
                 "steelman": _steelman_v16()},
        adversary={"case": "...", "case_citations": ["F2"], "findings": [],
                   "p_outperform": 0.66, "steelman": _steelman_v16()},
        judge={"p_outperform": 0.72, "direction": "long", "tier": "B",
               "judges": judges},
        direction="long", conviction_tier="B",
    )
    base.update(over)
    return _memo(**base)


def test_v16_memo_records_end_to_end():
    conn = _db()
    memo.record_memo(conn, _v16_memo())
    row = conn.execute(
        "SELECT direction, conviction_tier FROM thesis_memos").fetchone()
    assert row == ("long", "B")


def test_v16_judge_seat_bad_p_voids_naming_the_seat():
    judges = [_v16_judge("opus", 0.5), _v16_judge("fable", 0.81)]
    m = _v16_memo(judge={"p_outperform": 0.81, "direction": "long",
                         "tier": "A", "judges": judges})
    with pytest.raises(memo.ContractViolation, match="judge_opus"):
        memo.record_memo(_db(), m)


def test_v16_analyst_bad_p_voids():
    a = dict(_v16_memo().analyst, p_outperform=1.2)
    with pytest.raises(memo.ContractViolation,
                       match=r"analyst.*p_outperform"):
        memo.record_memo(_db(), _v16_memo(analyst=a))


def test_v16_adversary_missing_p_voids():
    adv = {k: v for k, v in _v16_memo().adversary.items()
           if k != "p_outperform"}
    with pytest.raises(memo.ContractViolation, match="adversary"):
        memo.record_memo(_db(), _v16_memo(adversary=adv))


def test_v16_steelman_not_direction_echoing_own_p_side_voids():
    # analyst p 0.78 is long-side; a "steelman" also arguing long defeats
    # the contract (same class as the v8 echo check, now against p)
    a = dict(_v16_memo().analyst, steelman=_steelman_v16(not_direction="long"))
    with pytest.raises(memo.ContractViolation,
                       match=r"analyst.*not_direction"):
        memo.record_memo(_db(), _v16_memo(analyst=a))


def test_v16_both_conviction_steelmans_required():
    sm = _steelman_v16()
    del sm["not_lower_conviction"]
    a = dict(_v16_memo().analyst, steelman=sm)
    with pytest.raises(memo.ContractViolation, match="not_lower_conviction"):
        memo.record_memo(_db(), _v16_memo(analyst=a))
    sm2 = _steelman_v16()
    sm2["not_higher_conviction"] = {"why": "", "citations": []}
    adv = dict(_v16_memo().adversary, steelman=sm2)
    with pytest.raises(memo.ContractViolation, match="not_higher_conviction"):
        memo.record_memo(_db(), _v16_memo(adversary=adv))


def test_v16_conviction_steelman_citations_checked():
    a = dict(_v16_memo().analyst, steelman=_steelman_v16(hi=("Z9",)))
    with pytest.raises(memo.ContractViolation, match="Z9"):
        memo.record_memo(_db(), _v16_memo(analyst=a))


def test_v16_judge_mirror_guard_recomputes_aggregate():
    # judges (0.72, 0.81) recompute to 0.72/long/B; a payload claiming the
    # fable value must void (mirror-drift guard, JS is display-only)
    m = _v16_memo(judge={"p_outperform": 0.81, "direction": "long",
                         "tier": "A",
                         "judges": [_v16_judge("opus", 0.72),
                                    _v16_judge("fable", 0.81)]},
                  direction="long", conviction_tier="A")
    with pytest.raises(memo.ContractViolation, match="ensemble"):
        memo.record_memo(_db(), m)


def test_v16_from_workflow_fills_derived_columns():
    # the judge payload carries ONLY p + judges: direction and
    # conviction_tier columns are DERIVED in code, never agent-stated
    wf = {
        "ticker": "MU",
        "analyst": dict(_v16_memo().analyst,
                        mispricing_claim="market prices peak; cycle says up",
                        horizon_weeks=10,
                        catalysts=[{"date": "2026-09-24", "event": "FQ4"}],
                        tripwire={"condition": "DRAM spot < X 10 sessions",
                                  "review_by": "2026-08-15"},
                        review_date="2026-10-01"),
        "adversary": _v16_memo().adversary,
        "judge": {"p_outperform": 0.72,
                  "judges": [_v16_judge("opus", 0.72),
                             _v16_judge("fable", 0.81)]},
    }
    manifest = {"ticker": "MU", "as_of": "2026-07-07", "sha256": "b" * 64,
                "doc_ids": ["P1", "X1", "F1", "F2", "N1", "I1", "R1"],
                "forensics": {"ar_growth": 0.1, "revenue_growth": 0.2,
                              "ni_exceeds_ocf_years": 0, "dilution_rate": 0.0}}
    rec = memo.from_workflow(wf, manifest, model_alias="opus",
                             agent_hashes={"analyst": "h", "adversary": "h",
                                           "judge": "h"})
    assert rec.direction == "long"
    assert rec.conviction_tier == "B"


def test_v16_short_zone_aggregate_derives_short_column():
    judges = [_v16_judge("opus", 0.28), _v16_judge("fable", 0.31)]
    a = dict(_v16_memo().analyst, p_outperform=0.30,
             steelman=_steelman_v16(not_direction="long"))
    adv = dict(_v16_memo().adversary, p_outperform=0.25,
               steelman=_steelman_v16(not_direction="long"))
    conn = _db()
    memo.record_memo(conn, _v16_memo(
        analyst=a, adversary=adv,
        judge={"p_outperform": 0.31, "direction": "short", "tier": "B",
               "judges": judges},
        direction="short", conviction_tier="B"))
    row = conn.execute(
        "SELECT direction, conviction_tier FROM thesis_memos").fetchone()
    assert row == ("short", "B")


def test_legacy_seats_without_p_outperform_still_record():
    # the 76 v8 + v9 memos of record carry no p_outperform; re-records must
    # stay on the frozen path and never void (in-kind from the v15 pin)
    conn = _db()
    memo.record_memo(conn, _memo())
    assert conn.execute("SELECT COUNT(*) FROM thesis_memos").fetchone()[0] == 1


# --- thesis-scale-v16: p_outperform derivation helpers (U1) ---
# Boundary literals HAND-WRITTEN from the spec's bands (as amended by the
# U7 post-cap knob delta 845b314), never derived from the knobs:
# A = p >= 0.75 or p <= 0.25; B = [0.65, 0.75) or (0.25, 0.35];
# C = 0.35 < p < 0.65 (excl. 0.5, which is not a verdict).


def test_direction_from_p_sides():
    assert memo.direction_from_p(0.51) == "long"
    assert memo.direction_from_p(0.99) == "long"
    assert memo.direction_from_p(0.49) == "short"
    assert memo.direction_from_p(0.01) == "short"


def test_direction_from_p_half_raises():
    with pytest.raises(memo.ContractViolation, match="0.5"):
        memo.direction_from_p(0.5)


def test_band_from_p_boundaries_exact():
    assert memo.band_from_p(0.75) == "A"
    assert memo.band_from_p(0.749) == "B"
    assert memo.band_from_p(0.65) == "B"
    assert memo.band_from_p(0.649) == "C"
    assert memo.band_from_p(0.351) == "C"
    assert memo.band_from_p(0.35) == "B"
    assert memo.band_from_p(0.251) == "B"
    assert memo.band_from_p(0.25) == "A"


def test_band_from_p_half_raises():
    with pytest.raises(memo.ContractViolation, match="0.5"):
        memo.band_from_p(0.5)


def test_p_outside_open_interval_raises():
    for bad in (0.0, 1.0, -0.2, 1.7):
        with pytest.raises(memo.ContractViolation):
            memo.direction_from_p(bad)
        with pytest.raises(memo.ContractViolation):
            memo.band_from_p(bad)


def test_p_bool_rejected():
    # bool passes isinstance(x, float) checks' int cousin; reject explicitly
    with pytest.raises(memo.ContractViolation):
        memo.direction_from_p(True)


def test_v16_analyst_case_citations_checked():
    a = dict(_v16_memo().analyst, case="...", case_citations=["Z7"])
    with pytest.raises(memo.ContractViolation, match="Z7"):
        memo.record_memo(_db(), _v16_memo(analyst=a))


# --- thesis-rewind-eval CONTRACT assertion 5: v17 pin roles ---

def test_a5_judge_seat_roles_detects_v17_five_seat_records():
    recs = [{"ticker": "MU", "fundamentals": {}, "catalyst": {},
             "challenger": {}, "judge": {"judges": [{"seat": "opus"},
                                                    {"seat": "fable"}]}}]
    assert memo.judge_seat_roles(recs) == (
        "analyst_fundamentals", "analyst_catalyst", "challenger",
        "judge_opus", "judge_fable")


def test_a5_from_workflow_maps_v17_five_seat_record():
    wf = {
        "ticker": "MU",
        "fundamentals": {"p_outperform": 0.7, "case": "quality+price",
                         "mispricing_claim": "underpriced HBM ramp",
                         "horizon_weeks": 8, "catalysts": [],
                         "tripwire": {"condition": "x",
                                      "review_by": "2026-04-01"},
                         "review_date": "2026-04-01"},
        "catalyst": {"p_outperform": 0.6, "case": "why-now"},
        "challenger": {"p_outperform": 0.4, "case": "why-not"},
        "judge": {"p_outperform": 0.66, "judges": [
            {"seat": "opus", "p_outperform": 0.66},
            {"seat": "fable", "p_outperform": 0.7}]},
    }
    m = memo.from_workflow(wf, _V8_MANIFEST, model_alias="opus",
                           agent_hashes={"analyst_fundamentals": {}})
    assert m.analyst["case"] == "quality+price"     # fundamentals -> analyst col
    assert m.adversary["case"] == "why-not"         # challenger -> adversary col
    assert m.catalyst_seat["case"] == "why-now"     # third seat preserved
    assert m.direction == "long" and m.conviction_tier == "B"
    assert m.review_date == "2026-04-01"


def test_a5_record_memos_role_files_cover_v17_roles():
    import importlib.util
    from pathlib import Path as _P
    script = _P(__file__).resolve().parents[2] / "scripts" / "record_memos.py"
    spec = importlib.util.spec_from_file_location("record_memos", script)
    rm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rm)
    v17_roles = ("analyst_fundamentals", "analyst_catalyst", "challenger",
                 "judge_opus", "judge_fable")
    for role in v17_roles:
        assert role in rm._ROLE_FILES, role
        assert rm._ROLE_FILES[role].exists(), rm._ROLE_FILES[role]

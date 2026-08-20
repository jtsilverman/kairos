"""Memo journal (thesis-engine unit 5b): mechanical contract checks + PIT
writes for thesis-workflow output.

Agent outputs are untrusted input (hard rule): record_memo validates the
contract in code BEFORE the DB write — tripwire observable+dated, every
citation resolves to a dossier doc id, every flagged forensic ratio addressed
in the analyst's forensic_notes. A judge verdict cannot waive these; a
violation raises ContractViolation and nothing is written.

Flag thresholds mirror docs/framework-thesis-engine.md (AR growth > 1.5x
revenue growth, NI > OCF 2+ consecutive years, dilution > 5%/yr) — demoted
from screen gates 2026-07-08, enforced here as must-address-in-memo.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import sqlite3
from dataclasses import dataclass
from typing import Optional, Sequence

from kairos.thesis import ensemble

logger = logging.getLogger(__name__)

AR_VS_REVENUE = 1.5
NI_OCF_YEARS = 2
DILUTION_PER_YEAR = 0.05


class ContractViolation(Exception):
    """Memo fails a mechanical output-contract check; nothing is recorded."""


@dataclass(frozen=True)
class MemoRecord:
    ticker: str
    as_of: str
    dossier_sha256: str
    dossier_doc_ids: Sequence[str]
    forensics: dict
    analyst: dict
    adversary: dict
    judge: dict
    direction: str
    conviction_tier: str
    mispricing_claim: str
    horizon_weeks: int
    catalysts: list[dict]
    tripwire: Optional[dict]
    review_date: str
    model_alias: str
    agent_hashes: dict
    # thesis-regime-v1: the judge-only market block the run carried, journaled
    # for scorer-identity replay; None when the run had no block. NEVER a
    # citable source — it deliberately has no doc id.
    market_context_text: Optional[str] = None
    market_context_sha256: Optional[str] = None
    # thesis-rewind-eval v17: the catalyst/flow seat's payload; None on
    # pre-v17 records. fundamentals maps to the analyst column and the
    # challenger to the adversary column (nearest semantic ancestors), so
    # every pre-v17 consumer keeps reading; the third seat is additive.
    catalyst_seat: Optional[dict] = None
    # premove-cohort: which screen admission produced this memo ('rs90' |
    # 'premove'); the readout slices aggregates on it. Default = the
    # original cohort so every pre-cohort record reads consistently.
    cohort: str = "rs90"


def scorer_pin(agent_files: dict, *, efforts: dict,
               models: Optional[dict] = None) -> dict:
    """Scorer identity journaled per memo: prompt-file sha256 + effort per
    role. Effort became per-role in debate-v2 (judges xhigh, analysts max);
    an unjournaled effort would silently mix scorers across evidence
    windows, so a role without a declared effort refuses to pin. Model
    became per-role in thesis-judges-v9: the two judge seats share ONE
    prompt file (same sha), so the model alias is the only thing telling
    judge_opus from judge_fable in the pin."""
    import hashlib
    from pathlib import Path

    pin = {}
    for role, path in agent_files.items():
        if role not in efforts:
            raise ContractViolation(f"no effort declared for role: {role}")
        pin[role] = {"sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                     "effort": efforts[role]}
        if models and role in models:
            pin[role]["model"] = models[role]
    return pin


def judge_seat_roles(records: list[dict]) -> tuple[str, ...]:
    """Which pin roles a workflow-out file needs, inferred from its judge
    count (the era marker, same dispatch as ensemble.aggregate): 2 seats ->
    per-seat roles, anything else -> the single v8 judge role. A run is one
    era; mixed counts mean a corrupted rebuild and refuse to pin."""
    if not records:
        raise ContractViolation("zero records: nothing to infer pin roles from")
    v17 = {"challenger" in wf for wf in records}
    if v17 == {True}:
        return ("analyst_fundamentals", "analyst_catalyst", "challenger",
                "judge_opus", "judge_fable")
    if True in v17:
        raise ContractViolation("mixed v17/non-v17 records in one run")
    counts = {len(wf.get("judge", {}).get("judges", [])) for wf in records}
    if counts == {2}:
        return ("analyst", "adversary", "judge_opus", "judge_fable")
    if 2 in counts:
        raise ContractViolation(f"mixed judge-count eras in one run: {counts}")
    return ("analyst", "adversary", "judge")


def flagged_ratios(forensics: dict) -> list[str]:
    """Which forensic ratios breach the must-address thresholds. None values
    (insufficient series) are unmeasured, not breaches -- but notna-style
    explicit: only a real number can flag."""
    flags: list[str] = []
    ar, rev = forensics.get("ar_growth"), forensics.get("revenue_growth")
    if ar is not None and rev is not None and ar > AR_VS_REVENUE * rev:
        flags.append("ar_growth")
    dil = forensics.get("dilution_rate")
    if dil is not None and dil > DILUTION_PER_YEAR:
        flags.append("dilution_rate")
    if forensics.get("ni_exceeds_ocf_years", 0) >= NI_OCF_YEARS:
        flags.append("ni_exceeds_ocf_years")
    return sorted(flags)


def _steelman_citations(seat: dict) -> list[str]:
    """v8+: every analyst seat argues the road not taken (steelman
    contract); those citations face the same doc-id check as the case
    itself. v16 replaces not_tiers with the two conviction blocks."""
    sm = seat.get("steelman", {})
    cites = list(sm.get("not_direction_citations", []))
    for nt in sm.get("not_tiers", []):
        cites.extend(nt.get("citations", []))
    for key in ("not_higher_conviction", "not_lower_conviction"):
        cites.extend((sm.get(key) or {}).get("citations", []))
    return cites


def _all_citations(m: MemoRecord) -> list[str]:
    cites: list[str] = []
    for dim in m.analyst.get("dimensions", {}).values():
        cites.extend(dim.get("citations", []))
    for note in m.analyst.get("forensic_notes", {}).values():
        cites.extend(note.get("citations", []))
    cites.extend(m.analyst.get("case_citations", []))  # v16: analyst case
    cites.extend(m.adversary.get("case_citations", []))  # v8 rename ...
    cites.extend(m.adversary.get("bear_citations", []))  # ... but --era v7
    # re-records remain a live path; the legacy key stays checked
    for finding in m.adversary.get("findings", []):
        cites.extend(finding.get("citations", []))
    cites.extend(_steelman_citations(m.analyst))
    cites.extend(_steelman_citations(m.adversary))
    cites.extend(m.judge.get("decisive_citations", []))
    for judge in m.judge.get("judges", []):  # v7 ensemble: all three
        cites.extend(judge.get("decisive_citations", []))
    # agents cite either bare ("F1") or bracketed ("[F1]", the dossier's own
    # rendering) -- a formatting variance, not an unknown source (live: EZPW)
    return [c.strip("[]") for c in cites]


# thesis-scale-v16 threshold knobs (ONE home; the canary tuning loop may
# move these with ranking evidence — each move is a named delta in the
# spec's results table, with AC1's boundary literals amended in-kind).
ACTIONABLE_LONG = 0.65   # p >= this: actionable long thesis
ACTIONABLE_SHORT = 0.35  # p <= this: actionable short thesis
TOP_BAND_LONG = 0.75     # p >= this: legacy band A (long side). 0.80 -> 0.75
TOP_BAND_SHORT = 0.25    # p <= this: legacy band A (short side). 0.20 -> 0.25
# (U7 post-cap named delta 2026-07-15: 4 runs ceilinged the judge opus seat
# at 0.77, so a 0.80 top band was unreachable; table amended in-kind.)
# Split-panel clamp targets: just inside the no-action zone. A tuning move
# of ACTIONABLE_* must move these in the same delta or the clamp lands in
# the actionable zone and a split panel becomes actionable (the exact
# failure the clamp exists to prevent).
NO_ACTION_CLAMP_LONG = 0.64
NO_ACTION_CLAMP_SHORT = 0.36


def _check_p(p) -> float:
    """v16 scale guard: p_outperform is a real number strictly inside (0,1)
    and never exactly 0.5 (not a verdict — the prompt says pick a side).
    bool is an int subclass; reject it before the range check."""
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        raise ContractViolation(f"p_outperform not a number: {p!r}")
    if not 0.0 < p < 1.0:
        raise ContractViolation(f"p_outperform outside (0,1): {p}")
    if p == 0.5:
        raise ContractViolation("p_outperform exactly 0.5 is not a verdict")
    return float(p)


def direction_from_p(p: float) -> str:
    """Derived, never agent-stated: long above 0.5, short below."""
    return "long" if _check_p(p) > 0.5 else "short"


def band_from_p(p: float) -> str:
    """Legacy conviction band for ledger/readout continuity ONLY (agents
    never see letters): A = p >= 0.75 or p <= 0.25; B = [0.65, 0.75) or
    (0.25, 0.35]; C = the no-action middle."""
    p = _check_p(p)
    if p >= TOP_BAND_LONG or p <= TOP_BAND_SHORT:
        return "A"
    if p >= ACTIONABLE_LONG or p <= ACTIONABLE_SHORT:
        return "B"
    return "C"


def _seats(m: MemoRecord) -> list[tuple[str, dict]]:
    seats = [("analyst", m.analyst), ("adversary", m.adversary)]
    seats += [(f"judge_{j.get('seat', i)}", j)
              for i, j in enumerate(m.judge.get("judges", []))]
    return seats


def _check_v16_contract(m: MemoRecord) -> None:
    """thesis-scale-v16: every seat states p_outperform (the only verdict
    number); steelman argues the other side of 0.5 plus both conviction
    directions; the judge aggregate must recompute (mirror-drift guard,
    JS display is never trusted)."""
    for label, seat in _seats(m):
        if "p_outperform" not in seat:
            raise ContractViolation(f"{label}: p_outperform missing")
        try:
            _check_p(seat["p_outperform"])
        except ContractViolation as e:
            raise ContractViolation(f"{label}: {e}")

    for label, seat in (("analyst", m.analyst), ("adversary", m.adversary)):
        sm = seat.get("steelman")
        if sm is None:
            raise ContractViolation(f"{label}: steelman missing")
        own = direction_from_p(seat["p_outperform"])
        other = "short" if own == "long" else "long"
        if sm.get("not_direction") != other:
            raise ContractViolation(
                f"{label} steelman not_direction {sm.get('not_direction')!r} "
                f"must argue the other side of the seat's own p ({own})")
        for key in ("not_higher_conviction", "not_lower_conviction"):
            block = sm.get(key)
            if not block or not block.get("why") or not block.get("citations"):
                raise ContractViolation(
                    f"{label} steelman {key} missing why/citations")

    agg = ensemble.aggregate_v16(m.judge["judges"])
    claimed = (m.judge.get("p_outperform"), m.judge.get("direction"),
               m.judge.get("tier"))
    recomputed = (agg["p_outperform"], agg["direction"], agg["tier"])
    if claimed != recomputed:
        raise ContractViolation(
            f"ensemble mismatch: claimed {claimed}, recomputed {recomputed}")


def _check_contract(m: MemoRecord) -> None:
    known = set(m.dossier_doc_ids)
    unknown = sorted({c for c in _all_citations(m) if c not in known})
    if unknown:
        raise ContractViolation(f"citations to unknown doc ids: {unknown}")

    # Era dispatch on the judge payload: p_outperform present -> v16 scale
    # contract; absent -> the frozen v8/v9 letter path, untouched (the 76+
    # memos of record re-record through it byte-identically)
    if "p_outperform" in m.judge:
        _check_v16_contract(m)
    else:
        # v8 steelman completeness: not_tiers must be EXACTLY the two tiers
        # the seat did not pick — JSON schema can say "2 items" but not "not
        # yours", so the check lives here (spec thesis-debate-v3 non-goal b)
        for label, seat in (("analyst", m.analyst), ("adversary", m.adversary)):
            sm = seat.get("steelman")
            if sm is None:
                continue  # pre-v8 payloads carry no steelman
            if sm.get("not_direction") == seat.get("direction"):
                raise ContractViolation(
                    f"{label} steelman not_direction echoes its own direction")
            listed = sorted(nt.get("tier") for nt in sm.get("not_tiers", []))
            expected = sorted({"A", "B", "C"} - {seat.get("tier")})
            if listed != expected:
                raise ContractViolation(
                    f"{label} steelman not_tiers {listed} != unselected {expected}")

        if "judges" in m.judge:  # v7 ensemble: recorded verdict must equal
            # the code-recomputed aggregate (mirror-drift guard; JS is
            # display-only)
            agg = ensemble.aggregate(m.judge["judges"])
            claimed = (m.judge.get("tier"), m.judge.get("direction"))
            if claimed != (agg["tier"], agg["direction"]):
                raise ContractViolation(
                    f"ensemble mismatch: claimed {claimed}, recomputed "
                    f"({agg['tier']}, {agg['direction']})")

    if not m.tripwire or not m.tripwire.get("condition") \
            or not m.tripwire.get("review_by"):
        raise ContractViolation("tripwire missing, or not observable+dated")

    # review dates drive ledger close-out via lexicographic compare against
    # ISO mark dates — a non-ISO value silently strands the row open
    for field, value in (("review_date", m.review_date),
                         ("tripwire.review_by", m.tripwire["review_by"])):
        try:
            _dt.date.fromisoformat(value)
        except (TypeError, ValueError):
            raise ContractViolation(f"{field} not an ISO date: {value!r}")

    notes = m.analyst.get("forensic_notes", {})
    unaddressed = [r for r in flagged_ratios(m.forensics) if r not in notes]
    if unaddressed:
        raise ContractViolation(f"flagged forensics unaddressed: {unaddressed}")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS thesis_memos (
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
    market_context_text   TEXT,
    market_context_sha256 TEXT,
    cohort           TEXT NOT NULL DEFAULT 'rs90',
    UNIQUE (ticker, as_of, dossier_sha256)
);
"""

# Additive migration for DBs created before thesis-regime-v1 (66 live rows):
# CREATE IF NOT EXISTS skips an existing table, so new columns must be
# ALTERed in. Old rows read NULL, or the column's DEFAULT when it has one.
_ADDITIVE_COLUMNS = {
    "market_context_text": "TEXT",
    "market_context_sha256": "TEXT",
    "cohort": "TEXT NOT NULL DEFAULT 'rs90'",
    "catalyst_seat_json": "TEXT",
}


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    existing = {r[1] for r in conn.execute("PRAGMA table_info(thesis_memos)")}
    for col, ddl_type in _ADDITIVE_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE thesis_memos ADD COLUMN {col} {ddl_type}")
    conn.commit()


def from_workflow(wf: dict, manifest: dict, *, model_alias: str,
                  agent_hashes: dict,
                  market_context: Optional[dict] = None) -> MemoRecord:
    """Map one thesis-workflow record + its dossier manifest entry to a
    MemoRecord. The judge's tier AND direction are FINAL — the analysts'
    are carried inside their json for the retro loop, never as the record's.
    Execution stays long-only in v1: pool admission requires direction=long;
    a short verdict is a recorded no-trade with information.

    v16: a judge payload carrying p_outperform gets BOTH columns DERIVED
    from the number in code — agents never state direction or letters.

    v17 (thesis-rewind-eval): a record carrying `challenger` maps
    fundamentals->analyst and challenger->adversary (nearest semantic
    ancestors, pre-v17 consumers keep reading) and preserves the catalyst
    seat additively."""
    v17 = "challenger" in wf
    analyst = wf["fundamentals"] if v17 else wf["analyst"]
    judge = wf["judge"]
    if "p_outperform" in judge:
        direction = direction_from_p(judge["p_outperform"])
        conviction_tier = band_from_p(judge["p_outperform"])
    else:
        direction = judge.get("direction", "long")
        conviction_tier = judge["tier"]
    return MemoRecord(
        ticker=manifest["ticker"],
        as_of=manifest["as_of"],
        dossier_sha256=manifest["sha256"],
        dossier_doc_ids=tuple(manifest["doc_ids"]),
        forensics=manifest["forensics"],
        analyst=analyst,
        adversary=wf["challenger"] if v17 else wf["adversary"],
        catalyst_seat=wf.get("catalyst"),
        judge=judge,
        direction=direction,
        conviction_tier=conviction_tier,
        mispricing_claim=analyst["mispricing_claim"],
        horizon_weeks=analyst["horizon_weeks"],
        catalysts=analyst["catalysts"],
        tripwire=analyst["tripwire"],
        review_date=analyst["review_date"],
        model_alias=model_alias,
        agent_hashes=agent_hashes,
        market_context_text=(market_context or {}).get("text"),
        market_context_sha256=(market_context or {}).get("sha256"),
        cohort=manifest.get("cohort", "rs90"),
    )


def record_memo(conn: sqlite3.Connection, m: MemoRecord) -> None:
    _check_contract(m)
    with conn:
        conn.execute(
            "INSERT INTO thesis_memos (ticker, as_of, dossier_sha256,"
            " analyst_json, adversary_json, judge_json, direction,"
            " conviction_tier, mispricing_claim, horizon_weeks, catalysts_json,"
            " tripwire_json, review_date, model_alias, agent_hashes_json,"
            " forensics_json, recorded_at, market_context_text,"
            " market_context_sha256, cohort, catalyst_seat_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (m.ticker, m.as_of, m.dossier_sha256,
             json.dumps(m.analyst), json.dumps(m.adversary),
             json.dumps(m.judge), m.direction, m.conviction_tier,
             m.mispricing_claim, m.horizon_weeks, json.dumps(m.catalysts),
             json.dumps(m.tripwire), m.review_date, m.model_alias,
             json.dumps(m.agent_hashes), json.dumps(m.forensics),
             _dt.datetime.now(_dt.timezone.utc).isoformat(),
             m.market_context_text, m.market_context_sha256, m.cohort,
             None if m.catalyst_seat is None else json.dumps(m.catalyst_seat)),
        )
    logger.debug("record_memo: %s %s tier=%s", m.ticker, m.as_of,
                 m.conviction_tier)

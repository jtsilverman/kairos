"""Rebuild thesis records from workflow journal result lines (debate-v2
unit 3).

The workflow returns a slim summary; full agent outputs live in the run
journal, self-identified by the schema-required `ticker` and classified by
shape. Four eras: `v9` (thesis-judges-v9: 2 heterogeneous seat-keyed
judges, opus + fable), `v8` (debate-v3: risk-averse seat, case+findings,
both seats directional, 3 judges), `v7` (parallel analyst+adversary, 3
judges aggregated at rebuild) and `legacy` (v5/v6 sequential single-judge
chain — the frozen 63-memo window). v8 groups like v7; only the RA payload
shape differs. Era is caller-declared per journal (a run is one era);
shape misclassification across eras is what would silently corrupt the
frozen window, so nothing is auto-detected.

Resume re-runs duplicate agents (cache-key drift on embedded briefs,
observed live 2026-07-09). Grouping rules:
- v7/v8: first analyst; the FIRST adversary followed by >=3 judges before
  the next adversary — those judges adjudicated THAT brief; aggregate via
  ensemble.aggregate.
- v9: same window rule, but seat presence not count — first verdict PER
  SEAT (opus + fable both required); aggregate via ensemble.aggregate_v9.
- legacy: first judge, paired with the last adversary completed before it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from kairos.thesis import ensemble


@dataclass
class RebuildResult:
    records: list[dict] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


_V17_ADVOCACY_SEATS = ("fundamentals", "catalyst", "challenger")


def classify(result: dict) -> str | None:
    # v17 advocacy seats self-identify (lens-diverse trio, thesis-rewind-eval
    # A5); checked FIRST — a judge's seat values (opus/fable) never collide
    if result.get("seat") in _V17_ADVOCACY_SEATS:
        return result["seat"]
    if "dimensions" in result:
        return "analyst"
    if "bear_case" in result and "findings" in result:  # v7/legacy RA
        return "adversary"
    if "case" in result and "findings" in result:  # v8 RA: directional, but
        return "adversary"  # only adversary_adjudication marks a judge
    if "adversary_adjudication" in result:  # v16 judges carry no tier;
        # backward-safe — every v8/v9 judge also carries the adjudication
        return "judge"
    return None


# Trailing tool-call serialization residue observed in an ACCEPTED verdict's
# rationale (structured-output-parameter-swallow, PENG judge3
# wf_b4bea052-7e6): the parameter boundary got emitted inside the string, so
# '</parameter>\n</invoke>\n' reached the journal. Trailing-only — a
# mid-string mention is quoted content, not the defect.
_MARKUP_RESIDUE = re.compile(r"(?:\s*</(?:parameter|invoke)>)+\s*$")


def _strip_residue(value):
    if isinstance(value, str):
        return _MARKUP_RESIDUE.sub("", value)
    if isinstance(value, list):
        return [_strip_residue(v) for v in value]
    if isinstance(value, dict):
        return {k: _strip_residue(v) for k, v in value.items()}
    return value


def _group(lines: list[dict], problems: list[str]) -> dict[str, list]:
    by_ticker: dict[str, list[tuple[str, dict]]] = {}
    for entry in lines:
        if entry.get("type") != "result":
            continue
        result = entry.get("result")
        if not isinstance(result, dict):
            continue  # probe/non-schema agents return plain text
        role = classify(result)
        ticker = result.get("ticker")
        if role is None or not ticker:
            problems.append(f"unclassifiable result (key {entry.get('key')})")
            continue
        by_ticker.setdefault(ticker, []).append((role, _strip_residue(result)))
    return by_ticker


def _v7_record(ticker: str, events: list[tuple[str, dict]],
               out: RebuildResult) -> None:
    analyst = next((r for role, r in events if role == "analyst"), None)
    adversaries = [i for i, (role, _) in enumerate(events)
                   if role == "adversary"]
    chosen = None
    for pos, adv_at in enumerate(adversaries):
        end = adversaries[pos + 1] if pos + 1 < len(adversaries) else len(events)
        judges = [r for role, r in events[adv_at + 1:end] if role == "judge"]
        if len(judges) >= 3:
            chosen = (events[adv_at][1], judges[:3])
            break
    if analyst is None or chosen is None:
        out.incomplete.append(
            f"{ticker}: no coherent analyst + adversary + 3-judge trio in "
            f"{[role for role, _ in events]}")
        return
    adversary, judges = chosen
    out.records.append({"ticker": ticker, "analyst": analyst,
                        "adversary": adversary,
                        "judge": ensemble.aggregate(judges)})


def _seat_pair_record(ticker: str, events: list[tuple[str, dict]],
                      out: RebuildResult, aggregator) -> None:
    """2 heterogeneous seats (v9 letters or v16 p's; only the aggregator
    differs). The coherent pair is the FIRST adversary followed (before the
    next adversary) by at least one judge of EACH seat; within the window
    the first-completed verdict per seat is canonical (resume re-runs
    duplicate agents — first-completed wins, workflow-resume lesson). Seat
    presence, never count: two same-seat verdicts are a partial panel."""
    analyst = next((r for role, r in events if role == "analyst"), None)
    adversaries = [i for i, (role, _) in enumerate(events)
                   if role == "adversary"]
    chosen = None
    for pos, adv_at in enumerate(adversaries):
        end = adversaries[pos + 1] if pos + 1 < len(adversaries) else len(events)
        window = [r for role, r in events[adv_at + 1:end] if role == "judge"]
        by_seat = {}
        for j in window:
            by_seat.setdefault(j.get("seat"), j)  # first per seat wins
        if {"opus", "fable"} <= set(by_seat):
            chosen = (events[adv_at][1], [by_seat["opus"], by_seat["fable"]])
            break
    if analyst is None or chosen is None:
        out.incomplete.append(
            f"{ticker}: no coherent analyst + adversary + opus/fable judge "
            f"pair in {[role for role, _ in events]}")
        return
    adversary, judges = chosen
    out.records.append({"ticker": ticker, "analyst": analyst,
                        "adversary": adversary,
                        "judge": aggregator(judges)})


def _v9_record(ticker: str, events: list[tuple[str, dict]],
               out: RebuildResult) -> None:
    _seat_pair_record(ticker, events, out, ensemble.aggregate_v9)


def _v16_record(ticker: str, events: list[tuple[str, dict]],
                out: RebuildResult) -> None:
    _seat_pair_record(ticker, events, out, ensemble.aggregate_v16)


def _v17_record(ticker: str, events: list[tuple[str, dict]],
                out: RebuildResult) -> None:
    """Five seats, no windowing: the v17 stage-1 trio is parallel and
    independent (no adversary-anchored coherence needed). First-completed
    per seat wins (workflow-resume lesson); all five present -> record,
    else incomplete with the missing seats named."""
    first: dict[str, dict] = {}
    judges: dict[str, dict] = {}
    for role, r in events:
        if role in _V17_ADVOCACY_SEATS:
            first.setdefault(role, r)
        elif role == "judge":
            judges.setdefault(r.get("seat"), r)
    missing = [s for s in _V17_ADVOCACY_SEATS if s not in first]
    missing += [f"judge_{s}" for s in ("opus", "fable") if s not in judges]
    if missing:
        out.incomplete.append(f"{ticker}: missing seats {missing}")
        return
    out.records.append({
        "ticker": ticker,
        "fundamentals": first["fundamentals"],
        "catalyst": first["catalyst"],
        "challenger": first["challenger"],
        "judge": ensemble.aggregate_v16([judges["opus"], judges["fable"]]),
    })


def _legacy_record(ticker: str, events: list[tuple[str, dict]],
                   out: RebuildResult) -> None:
    analyst = next((r for role, r in events if role == "analyst"), None)
    judge_at = next((i for i, (role, _) in enumerate(events)
                     if role == "judge"), None)
    adversary = None
    if judge_at is not None:
        adversary = next((r for role, r in reversed(events[:judge_at])
                          if role == "adversary"), None)
    if analyst is None or adversary is None or judge_at is None:
        out.incomplete.append(
            f"{ticker}: no coherent analyst->adversary->judge chain in "
            f"{[role for role, _ in events]}")
        return
    out.records.append({"ticker": ticker, "analyst": analyst,
                        "adversary": adversary, "judge": events[judge_at][1]})


_ERA_BUILDERS = {
    "legacy": _legacy_record,
    # v8 groups exactly like v7 (parallel seats + 3 judges); only the RA
    # payload shape differs, which classify absorbs
    "v7": _v7_record,
    "v8": _v7_record,
    "v9": _v9_record,
    "v16": _v16_record,
    "v17": _v17_record,
}


def rebuild(lines: list[dict], *, era: str) -> RebuildResult:
    if era not in _ERA_BUILDERS:
        raise ValueError(f"unknown era: {era!r}")
    out = RebuildResult()
    by_ticker = _group(lines, out.problems)
    for ticker in sorted(by_ticker):
        _ERA_BUILDERS[era](ticker, by_ticker[ticker], out)
    return out

"""thesis-exemplars unit 12: layer 1's two-no triage rule.

A single sonnet pass on an identical sheet disagrees with itself 6.0% of the
time (336 names, docs/stage2-triage-2026-08.md). The PANEL rule answered that
with three passes plus an opus adjudicator, ~3.06 reads per name. The rule of
record for June and live is TWO_NO: one pass, and a NO must be confirmed by a
second pass before it cuts.

The asymmetry is the whole point, and it is what these tests pin. This layer
rules OUT: a wrong cut loses a name for good, a wrong keep costs three sonnet
reads downstream. So a yes settles on one read, a no never cuts alone, and a
seat that dies can never become a silent cut.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / "scripts" / "cascade_workflow.js"
_HARNESS = Path(__file__).resolve().parent / "cascade_harness.mjs"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def run(plan: dict, *, rule: str = "TWO_NO", tmp_path: Path) -> tuple[dict, list[str]]:
    src = _WORKFLOW.read_text()
    if rule != "TWO_NO":
        src = src.replace("const RULE = 'TWO_NO'", f"const RULE = '{rule}'")
    script = tmp_path / "cascade.js"
    script.write_text(src)
    out = subprocess.run(["node", str(_HARNESS), str(script), json.dumps(plan)],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    run.models = got["models"]
    return got["res"], got["calls"]


def _rows(res: dict) -> dict:
    return {r["slug"]: r for r in res["rows"]}


def test_a_yes_settles_on_one_read(tmp_path):
    res, calls = run({"AAA": {"passes": ["yes", "no", "no"]}}, tmp_path=tmp_path)
    assert res["keeps"] == ["AAA"]
    assert calls == ["triage:AAA:1"], "a yes must not pay for a second read"
    assert _rows(res)["AAA"]["route"] == "first-pass-yes"


def test_a_no_cuts_only_when_a_second_pass_confirms_it(tmp_path):
    res, calls = run({"AAA": {"passes": ["no", "no"]}}, tmp_path=tmp_path)
    assert res["keeps"] == []
    assert calls == ["triage:AAA:1", "triage:AAA:2"]
    assert _rows(res)["AAA"]["route"] == "two-no"


def test_the_second_pass_rescues_a_name_the_first_would_have_cut(tmp_path):
    # This is the rule's reason for existing: one pass flips 6% of the time,
    # and a wrong cut is unrecoverable.
    res, _ = run({"AAA": {"passes": ["no", "yes"]}}, tmp_path=tmp_path)
    assert res["keeps"] == ["AAA"]
    assert _rows(res)["AAA"]["route"] == "rescued"
    assert res["counts"]["rescued"] == 1


def test_a_dead_first_seat_is_dropped_not_cut(tmp_path):
    res, _ = run({"AAA": {"passes": [None]}}, tmp_path=tmp_path)
    assert res["keeps"] == []
    row = _rows(res)["AAA"]
    assert row["verdict"] is None and row["route"] == "incomplete"
    assert res["counts"]["dropped"] == 1


def test_an_unconfirmed_no_is_dropped_not_cut(tmp_path):
    # The confirming seat died. Cutting here would be a one-pass cut wearing
    # the two-no rule's name.
    res, _ = run({"AAA": {"passes": ["no", None]}}, tmp_path=tmp_path)
    row = _rows(res)["AAA"]
    assert row["verdict"] is None and row["route"] == "unconfirmed-no"
    assert res["counts"]["dropped"] == 1


def test_the_rule_costs_about_one_and_a_third_reads_per_name(tmp_path):
    # Three yes names, one confirmed no: 3 + 2 = 5 reads over 4 names.
    plan = {"AAA": {"passes": ["yes"]}, "BBB": {"passes": ["yes"]},
            "CCC": {"passes": ["yes"]}, "DDD": {"passes": ["no", "no"]}}
    res, calls = run(plan, tmp_path=tmp_path)
    assert res["counts"]["reads"] == 5 == len(calls)
    assert res["counts"]["kept"] == 3
    assert res["rule"] == "TWO_NO"


def test_no_adjudicator_ever_runs_under_the_two_no_rule(tmp_path):
    plan = {"AAA": {"passes": ["no", "yes"], "_adjudicate": "no"},
            "BBB": {"passes": ["yes"], "_adjudicate": "no"}}
    _, calls = run(plan, tmp_path=tmp_path)
    assert not any(c.startswith("adjudicate:") for c in calls)


def test_the_panel_rule_still_runs_three_passes_and_adjudicates_a_split(tmp_path):
    # The three tuning cohorts were drawn under PANEL; it must stay reproducible.
    plan = {"AAA": {"passes": ["yes", "no", "yes"], "_adjudicate": "yes"}}
    res, calls = run(plan, rule="PANEL", tmp_path=tmp_path)
    assert [c for c in calls if c.startswith("triage:")] == [
        "triage:AAA:1", "triage:AAA:2", "triage:AAA:3"]
    assert "adjudicate:AAA" in calls
    assert res["keeps"] == ["AAA"] and _rows(res)["AAA"]["route"] == "adjudicated"
    assert res["rule"] == "PANEL"


def test_the_panel_rule_drops_a_name_whose_seat_died(tmp_path):
    res, _ = run({"AAA": {"passes": ["yes", None, "yes"]}}, rule="PANEL", tmp_path=tmp_path)
    assert _rows(res)["AAA"]["route"] == "incomplete"
    assert res["counts"]["dropped"] == 1


def test_every_seat_names_a_versioned_model(tmp_path):
    # the triage frontmatter says 'sonnet', an alias that moved to Sonnet 5.5 on
    # 2026-09-28; the call site must pin the version the cohorts were tuned on
    run({"AAA": {"passes": ["no", "no", "yes"], "_adjudicate": "yes"}}, rule="PANEL", tmp_path=tmp_path)
    assert set(run.models) == {"triage=claude-sonnet-5", "adjudicate=claude-opus-4-8"}

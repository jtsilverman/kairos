"""thesis-exemplars unit 8, vision milestone 3: the five-seat funnel workflow.

`scripts/gen_funnel_workflow.py` emits the workflow of record with the five
`.claude/agents/*-seat.md` bodies embedded. Per name: bull and bear (sonnet)
in parallel, the ruler (sonnet) with both cases inline, the pass rule
applied IN CODE, then the editor (claude-opus-4-8) and the verdict on a
pass. The rule is a constant the script holds; no seat body states it.
The summary record is what `panel_collect.py` copies and
`score_exemplars.py` reads.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "gen_funnel_workflow.py"
_AGENTS = _ROOT / ".claude" / "agents"

SEATS = ("bull", "bear", "ruler", "editor", "verdict")


def _module():
    assert _SCRIPT.exists(), f"{_SCRIPT} does not exist"
    spec = importlib.util.spec_from_file_location("gen_funnel_workflow", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _generated(tmp_path: Path, *extra: str) -> str:
    out = tmp_path / "funnel.js"
    assert _module().main(["--out", str(out), *extra]) == 0
    return out.read_text()


@pytest.fixture(scope="module")
def default_script(tmp_path_factory) -> str:
    return _generated(tmp_path_factory.mktemp("funnel"))


def _block(script: str, const: str) -> str:
    m = re.search(rf"const {const} = .*?\n\}}\)?\n", script, re.S)
    assert m, f"{const} block not found"
    return m.group(0)


def _top_required(block: str) -> list[str]:
    reqs = re.findall(r"required: \[([^\]]*)\]", block, re.S)
    assert reqs
    return re.findall(r"'([a-z_]+)'", reqs[-1])


def test_five_seat_sites_bull_bear_ruler_editor_verdict(default_script):
    script = default_script
    for seat in SEATS:
        assert f"label: `{seat}:${{" in script, f"no agent site labelled {seat}:"
    # sonnet on the three middle seats, the versioned opus id on the editor,
    # and one constant for the verdict that defaults to the same opus id.
    for seat in ("bull", "bear", "ruler"):
        site = script[script.index(f"label: `{seat}:") - 400: script.index(f"label: `{seat}:")]
        assert "model: SONNET" in site, f"{seat} must run on the pinned sonnet"
    assert "const SONNET = 'claude-sonnet-5'" in script
    # no seat may name a bare alias: 'sonnet' moved to Sonnet 5.5 on 2026-09-28 unannounced to the run
    assert not re.search(r"model: '(sonnet|opus|fable|haiku)'", script)
    editor = script[script.index("label: `editor:") - 400: script.index("label: `editor:")]
    assert "model: OPUS" in editor
    assert "const OPUS = 'claude-opus-4-8'" in script
    # the verdict defaults to Fable 5 (January 2026 cutoff, blind on every tuning date; Jake 2026-09-15)
    assert "const VERDICT_MODEL = 'claude-fable-5'" in script
    verdict = script[script.index("label: `verdict:") - 400: script.index("label: `verdict:")]
    assert "model: VERDICT_MODEL" in verdict


def test_case_schemas_require_case_fact_and_cites(default_script):
    script = default_script
    block = _block(script, "CASE_TEST")
    assert _top_required(block) == ["case", "strongest_fact", "cites"]
    assert "const caseSchema" in script and script.count("schema: caseSchema(") == 2
    assert "const CASE_TESTS = perTest(CASE_TEST)" in script


def test_the_four_test_keys_come_from_one_list(default_script):
    script = default_script
    keys = '["business_case", "fundamentals", "demand_case", "positioned"]'
    assert f"const TEST_KEYS = {keys}" in script
    assert "required: TEST_KEYS" in script and script.count("enum: TEST_KEYS") == 2


def test_ruler_answers_who_won_and_whether_the_evidence_is_whole(default_script):
    # Who won and how complete the winning evidence is are different questions;
    # one word for both left no way to record a bear who lands a real blow.
    script = default_script
    block = _block(script, "RULING")
    assert "winner: { type: 'string', enum: ['bull', 'bear'] }" in block
    assert "completeness: { type: 'string', enum: ['whole', 'holed'] }" in block
    assert _top_required(block) == ["winner", "completeness", "why", "cite"]
    ruler = _block(script, "rulerSchema")
    assert "struck" in _top_required(ruler) and "overall" in _top_required(ruler)
    assert "enum: ['bull', 'bear']" in ruler
    assert "const RULINGS = perTest(RULING)" in script
    # Downstream seats and the scorer still read one word per test.
    assert "v.winner === 'bear' ? 'bear' : (v.completeness === 'holed' ? 'gap' : 'bull')" in script


def test_editor_and_verdict_schemas(default_script):
    script = default_script
    ed = _block(script, "EDITED")
    assert _top_required(ed) == ["bull", "bear", "ruling_stands"]
    assert "edit_log" in _top_required(_block(script, "editorSchema"))
    assert "const EDITED_TESTS = perTest(EDITED)" in script
    vd = _block(script, "verdictSchema")
    for key in ("thesis", "bear_case", "rating_basis", "shortlist", "p_outperform"):
        assert key in _top_required(vd), f"verdict schema must require {key}"
    assert "shortlist: { type: 'boolean' }" in vd


def test_pass_rule_is_a_constant_applied_in_code_and_no_body_states_it(tmp_path, default_script):
    script = default_script
    assert "const PASS_RULE = 'overall'" in script
    assert "const passes = (rulings, overall) =>" in script
    b = _generated(tmp_path, "--pass-rule", "B")
    assert "const PASS_RULE = 'B'" in b
    for seat in SEATS:
        body = (_AGENTS / f"{seat}-seat.md").read_text().lower()
        assert "all four" not in body and "pass rule" not in body, \
            f"{seat}-seat.md states the pass rule"


def test_summary_record_carries_ruler_pass_and_the_verdict(default_script):
    script = default_script
    for field in ("ruler_pass:", "overall,", "rulings:", "shortlist:", "p_judge:", "thesis:", "edited_cases:", "edit_log:", "bear_case:", "rating_basis:"):
        assert field in script, f"summary record must carry {field}"
    # a ruler-cut name is recorded, not dropped: shortlist false and no number
    assert "shortlist: false, p_judge: null" in script


def test_rubric_reaches_every_seat_from_one_file(tmp_path):
    script = _generated(tmp_path).replace("\\n", "\n")
    doc = (_ROOT / "docs" / "four-tests.md").read_text()
    line = next(l for l in doc.splitlines() if l.startswith("- **absent**")).strip()
    assert script.count(line) == 5, "docs/four-tests.md must be embedded once per seat"
    assert "## Thesis visible" not in doc, "the rubric file must hold the rubric alone"


def test_no_seat_reads_the_pass_rule_or_a_beat_rate(tmp_path):
    # the rubric file also holds the bar and the outcome table; neither may
    # reach a reader (a seat rules to the dossier, and a beat rate is an outcome)
    mod = _module()
    for seat in SEATS:
        prompt = mod.body(seat).lower()
        for leak in ("thesis visible", "all four", "beat rate", "strong count",
                     "2026-02-02", "2026-03-16", "2026-05-01"):
            assert leak not in prompt, f"{seat} prompt leaks {leak!r}"


def test_every_launch_checks_the_verdict_model_cutoff_against_as_of(tmp_path):
    script = _generated(tmp_path, "--verdict-model", "claude-fable-5-1")
    assert "const VERDICT_MODEL = 'claude-fable-5-1'" in script
    assert "'claude-fable-5-1': '2026-06'" in script and "'claude-opus-4-8': '2026-01'" in script
    # the cutoff table holds versioned ids only; a bare alias cannot be looked up
    assert "sonnet: '" not in script and "fable: '" not in script
    assert "'claude-fable-5': '2026-01'" in script
    assert "input.asOf.slice(0, 7) < CUTOFF[m]" in script


def test_v18_generator_and_panel_seats_are_gone():
    assert not (_ROOT / "scripts" / "gen_panel_workflow.py").exists()
    assert not list(_AGENTS.glob("panel-*.md"))
    assert not (_ROOT / "code" / "tests" / "test_gen_panel_workflow.py").exists()


_HARNESS = Path(__file__).resolve().parent / "funnel_harness.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_generated_script_runs_the_layers_and_the_cutoff_check(tmp_path):
    out = tmp_path / "funnel.js"
    assert _module().main(["--out", str(out)]) == 0
    withheld = tmp_path / "funnel-unruled.js"
    assert _module().main(["--out", str(withheld), "--withhold-rulings"]) == 0
    res = subprocess.run(["node", str(_HARNESS), str(out), str(withheld)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    got = json.loads(res.stdout)
    assert got["full"] == {"AAA": [True, True, 0.66], "BBB": [False, False, None]}
    assert got["full_calls"] == ["bull:AAA", "bear:AAA", "ruler:AAA", "editor:AAA", "verdict:AAA",
                                 "bull:BBB", "bear:BBB", "ruler:BBB"]
    assert got["middle_calls"] == ["bull:AAA", "bear:AAA", "ruler:AAA", "bull:BBB", "bear:BBB", "ruler:BBB"]
    assert got["verdict_calls"] == ["editor:AAA", "verdict:AAA", "editor:BBB", "verdict:BBB"]
    assert got["rule_b_passes_one_gap"] is True
    assert got["overall_rule"] == {"AAA": True, "BBB": False, "CCC": True}
    assert "needs names[].casesPath" in got["verdict_without_cases"]
    assert got["verdict_record_carries_path"] is True
    assert got["verdict_record_keeps_edited_cases"] is True
    assert got["editor_calls"] == ["editor:AAA", "editor:BBB"]
    assert got["editor_record"] is True
    assert "the funnel is blind" in got["blind_guard"]
    assert "not blind on 2026-02-02" in got["fable_on_a_rewind_date"]
    assert "bare alias" in got["alias_refused"]
    assert got["dossier_dirs"] == {"default": True, "live": True}
    # unit 11j: the verdict alone on stored edited cases, rulings shown or withheld
    for key in ("decide_with", "decide_without"):
        assert got[key]["calls"] == ["verdict:AAA", "verdict:BBB"]
        assert got[key]["shortlist"] == [True, True] and got[key]["cases"] is True
    assert got["decide_with"]["rulings_block"] is True and got["decide_with"]["four_rulings"] is True
    w = got["decide_without"]
    assert (w["rulings_block"], w["ruling_stands"], w["four_rulings"]) == (False, False, False)
    assert "layer decide needs names[].edited" in got["decide_without_edited"]


def test_withholding_rulings_is_off_by_default_and_changes_only_the_verdict(tmp_path):
    mod = _module()
    off = mod.generate(verdict_model="claude-fable-5")
    on = mod.generate(verdict_model="claude-fable-5", withhold_rulings=True)
    assert "const WITHHOLD_RULINGS = false" in off and "const WITHHOLD_RULINGS = true" in on
    assert "verdict_unruled: null" in off
    # the withheld run differs from the funnel of record in the flag and the second body alone
    assert off.replace("const WITHHOLD_RULINGS = false", "const WITHHOLD_RULINGS = true").replace(
        "verdict_unruled: null", "verdict_unruled: " + json.dumps(mod.unruled_body())) == on
    assert "the four rulings" not in mod.unruled_body() and "the four rulings" in mod.body("verdict")

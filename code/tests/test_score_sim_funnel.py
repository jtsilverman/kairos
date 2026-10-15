"""score_sim_funnel: the cohort walk per dossier tier, outcome kept beside it."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("score_sim_funnel", _ROOT / "scripts" / "score_sim_funnel.py")
sf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sf)

D = "2026-06-01"
STRONG = {"business_case": "strong", "fundamentals": "strong", "demand_case": "strong", "positioned": "strong"}
WEAK = dict(STRONG, fundamentals="weak")


def _setup(tmp_path, *, short_on_cut=False):
    mid = [{"slug": "GGG", "ruler_pass": True}, {"slug": "BBB", "ruler_pass": False},
           {"slug": "GG2", "ruler_pass": True}, {"slug": "UUU", "ruler_pass": False}]
    l3 = [{"slug": "GGG", "shortlist": True}, {"slug": "GG2", "shortlist": False}]
    if short_on_cut:
        l3.append({"slug": "BBB", "shortlist": True})
    (tmp_path / f"panel-results-sim-middle-{D}.json").write_text(json.dumps({"summary": mid}))
    (tmp_path / f"panel-results-sim-l3-{D}.json").write_text(json.dumps({"summary": l3}))
    rows = [{"ticker": "GGG", "grades": STRONG}, {"ticker": "GG2", "grades": STRONG}, {"ticker": "BBB", "grades": WEAK}]
    (tmp_path / f"sim-grades-{D}.json").write_text(json.dumps({"rows": rows}))
    (tmp_path / f"outcomes-{D}.json").write_text(json.dumps(
        {"GGG": {"alpha": 0.25}, "GG2": {"alpha": -0.5}, "BBB": {"alpha": -0.25}}))


def test_the_walk_counts_each_tier_through_both_layers(tmp_path):
    _setup(tmp_path)
    w = sf.walk(D, root=tmp_path)
    assert w["tiers"]["good"] == {"entered": 2, "passed": 2, "shortlisted": 1}
    assert w["tiers"]["bad"] == {"entered": 1, "passed": 0, "shortlisted": 0}
    assert w["ungraded"] == ["UUU"]
    assert w["short"] == {"n": 1, "mean_alpha": 0.25, "beat": 1}
    assert w["rest"]["n"] == 2 and w["rest"]["beat"] == 0


def test_a_shortlisted_name_the_ruler_cut_is_refused(tmp_path):
    # survivors only: the verdict never sees a cut name, so this is a broken run
    _setup(tmp_path, short_on_cut=True)
    with pytest.raises(AssertionError):
        sf.walk(D, root=tmp_path)

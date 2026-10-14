"""edited_store: one durable store of the editor's checked cases per date."""

import importlib.util
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("edited_store", _ROOT / "scripts" / "edited_store.py")
store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(store)

D = "2026-02-02"


def _ec(tag: str) -> dict:
    return {"demand_case": {"bull": f"bull {tag}", "bear": f"bear {tag}", "ruling_stands": True}}


def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def test_collect_sweeps_both_saved_shapes_and_skips_names_with_no_cases(tmp_path):
    # a verdict record (results file) and an editor-only batch (full workflow return)
    _write(tmp_path / f"panel-results-sim-l3e-{D}.json",
           {"summary": [{"slug": "AAA", "as_of": D, "edited_cases": _ec("a")},
                        {"slug": "CUT", "as_of": D, "shortlist": False}]})
    _write(tmp_path / "scratch" / f"sim-ed-out-{D}-b1.json",
           {"summary": "a description string", "result": {"summary": [{"slug": "BBB", "as_of": D, "edited_cases": _ec("b")}], "dropped": []}})
    store.collect(root=tmp_path)
    got = store.load(D, root=tmp_path)
    assert sorted(got) == ["AAA", "BBB"]
    assert got["BBB"] == _ec("b")
    assert store.missing(D, ["AAA", "BBB", "CUT"], root=tmp_path) == ["CUT"]


def test_the_first_checked_read_is_kept(tmp_path):
    # a later run that re-edits a name must not replace what every earlier comparison read
    _write(tmp_path / f"panel-results-x-{D}.json", {"summary": [{"slug": "AAA", "as_of": D, "edited_cases": _ec("first")}]})
    store.collect(root=tmp_path)
    _write(tmp_path / f"panel-results-x-{D}.json", {"summary": [{"slug": "AAA", "as_of": D, "edited_cases": _ec("second")}]})
    store.collect(root=tmp_path)
    assert store.load(D, root=tmp_path)["AAA"] == _ec("first")

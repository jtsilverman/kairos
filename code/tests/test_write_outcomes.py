"""write_outcomes: a window for every cohort name, and no window fabricated."""

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("write_outcomes", _ROOT / "scripts" / "write_outcomes.py")
wo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wo)

AS_OF = "2026-06-01"


def _days() -> dict:
    # entry 2026-06-02, exit 2026-08-31 (as_of + 91). Prices chosen exact in binary.
    return {
        "2026-06-01": {"SPY": 100.0, "AAA": 10.0},
        "2026-06-02": {"SPY": 100.0, "AAA": 10.0, "BBB": 8.0},
        "2026-08-31": {"SPY": 125.0, "AAA": 15.0},
    }


def test_alpha_is_the_names_return_less_spys_over_the_same_two_dates():
    out = wo.build(AS_OF, ["AAA"], _days())
    assert out["AAA"]["entry_date"] == "2026-06-02" and out["AAA"]["exit_date"] == "2026-08-31"
    assert out["AAA"]["ticker_return"] == 0.5 and out["AAA"]["spy_return"] == 0.25
    assert out["AAA"]["alpha"] == 0.25 and out["AAA"]["beat"] is True


def test_a_name_with_no_exit_bar_is_listed_missing_never_scored():
    out = wo.build(AS_OF, ["AAA", "BBB"], _days())
    assert "BBB" not in out
    assert out["_missing"] == ["BBB"]

"""The four tests of a thesis, as one JS schema fragment and one rubric file.

`docs/four-tests.md` is the rubric's home. `gen_sorter_workflow.py` embeds
it into the blind sorter's prompt and enforces the graded shape through this
JS fragment; `gen_funnel_workflow.py` embeds the same rubric into all five
seat prompts (the funnel's seats argue and rule, so they carry their own
shapes). One rubric on disk, however many readers.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
RUBRIC_PATH = _ROOT / "docs" / "four-tests.md"

KEYS = ("business_case", "fundamentals", "demand_case", "positioned")
GRADES = ("strong", "adequate", "weak", "absent")

#: Defines `TEST` and `TESTS` for a workflow script.
SCHEMA_JS = """\
// One graded test of the four (docs/four-tests.md). The grade names are the
// rubric's; the cite must be a doc id in the dossier.
const TEST = {
  type: 'object',
  properties: {
    grade: { type: 'string', enum: ['strong', 'adequate', 'weak', 'absent'] },
    evidence: { type: 'string', minLength: 40 },
    cite: { type: 'string' },
  },
  required: ['grade', 'evidence', 'cite'],
}
const TESTS = {
  type: 'object',
  properties: {
    business_case: TEST,
    fundamentals: TEST,
    demand_case: TEST,
    positioned: TEST,
  },
  required: ['business_case', 'fundamentals', 'demand_case', 'positioned'],
}
"""


@lru_cache(maxsize=1)
def rubric() -> str:
    """The rubric every reader sees, the whole file. The pass rule and the
    beat rates live in docs/four-tests-record.md, which no reader sees."""
    return RUBRIC_PATH.read_text().strip()

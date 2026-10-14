"""conviction-buckets unit 2: hand a 0.4 MB triage packet to a workflow.

A workflow script has no filesystem access, so the packet can only reach the
seats through `args` or through the script's own text. `args` passes through
the driving session's context, and three cohorts of anonymized fact sheets is
roughly 1.3 MB. So the packet is spliced INTO a per-cohort copy of
`cascade_workflow.js`, the same way `gen_embedded.py` splices agent bodies.

Every splice rests on a named exact-string anchor: a `cascade_workflow.js`
edit that moves a splice point errors by anchor name rather than silently
generating a script that reads an empty packet.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import gen_cascade_run  # noqa: E402

AS_OF = "2026-02-02"
SRC = (_SCRIPTS / "cascade_workflow.js").read_text()
PACKET = [{"slug": "N001", "sheet": "TICKER N001\nrevenue 100"},
          {"slug": "N002", "sheet": "TICKER N002\nrevenue 200"}]


def test_the_packet_and_the_as_of_are_spliced_into_the_script():
    out = gen_cascade_run.generate(SRC, AS_OF, PACKET)

    assert "N001" in out and "N002" in out
    assert AS_OF in out
    assert "args?.packet" not in out
    assert "args?.asOf" not in out


def test_the_generated_script_keeps_its_own_cohort_name():
    """Three cohort scripts run at once. A shared meta.name makes the three
    progress trees indistinguishable in /workflows."""
    out = gen_cascade_run.generate(SRC, AS_OF, PACKET)

    assert f"cascade-triage-{AS_OF}" in out


def test_a_moved_anchor_errors_by_name_rather_than_generating_a_stale_script():
    """The failure this prevents: a script that parses, runs, and fans out
    over an empty packet, reported as a cohort with zero keeps."""
    drifted = SRC.replace("const packet = args?.packet ?? []", "const packet = []")

    with pytest.raises(gen_cascade_run.GenError) as e:
        gen_cascade_run.generate(drifted, AS_OF, PACKET)

    assert "packet" in str(e.value)


def test_an_empty_packet_is_refused():
    """An empty packet reads downstream as `the seats rejected every name`
    rather than as `the cascade never ran`."""
    with pytest.raises(gen_cascade_run.GenError):
        gen_cascade_run.generate(SRC, AS_OF, [])


def test_a_packet_row_carrying_a_ticker_is_refused():
    """The packet is the anonymized artefact. A row that still carried its
    ticker would hand the triage seat the company it is meant to be blind to,
    and the named A/B moved 24 verdicts."""
    leaky = [{"slug": "N001", "sheet": "TICKER NVDA\nrevenue 100", "ticker": "NVDA"}]

    with pytest.raises(gen_cascade_run.GenError) as e:
        gen_cascade_run.generate(SRC, AS_OF, leaky)

    assert "ticker" in str(e.value)


def test_the_generated_script_is_valid_javascript(tmp_path):
    """A splice that produces a syntax error fails at launch, after the
    packet is built and the session has moved on."""
    out_path = tmp_path / "run.js"
    out_path.write_text(gen_cascade_run.generate(SRC, AS_OF, PACKET))

    proc = subprocess.run(["node", "--check", str(out_path)],
                          capture_output=True, text=True)

    assert proc.returncode == 0, proc.stderr


def test_the_row_count_is_reported_so_a_short_packet_is_visible(capsys, tmp_path):
    packet_path = tmp_path / f"triage-packet-{AS_OF}.json"
    packet_path.write_text(json.dumps(PACKET))
    out_path = tmp_path / "run.js"

    rc = gen_cascade_run.main(["--as-of", AS_OF, "--packet", str(packet_path),
                               "--out", str(out_path)])

    assert rc == 0
    assert "2 rows" in capsys.readouterr().out

#!/bin/bash
# The live paper run (specs/live-paper.md): the funnel of record on a LIVE as-of
# date, picks written to an append-only paper ledger. Nothing is bought.
#
#   M. mechanical layer 1 (screen, fact sheets, anonymize) -- run_cascade.py
#   T. two-no triage on claude-sonnet-5
#   C. LIVE dossiers (no --rewind: [E1]/[R1] carry real data), retried one at a time
#   2. layer 2, batches of 8; refused if any seat ran off claude-sonnet-5
#   3. layer 3 on the ruler's survivors; no cap
#   4. editor store collect; the blind sorter on every layer-2 entrant
#   5. the paper ledger, data/paper/<as_of>.json, written once
#
# One claude -p at a time. Every step skips work whose output exists and stops
# on the first failure; rerunning this script unchanged is the resume.
#
# Usage: live_paper_run.sh <as_of>
D=${1:?usage: live_paper_run.sh <as_of>}
cd "$(dirname "$0")/.." || exit 1
PY=code/.venv/bin/python
S=data/scratch/live-$D
mkdir -p "$S" data/sim-l3 data/paper
LOG=data/scratch/live-$D-chain.log
say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0
set -a; . ./.env; set +a
# Child prompts: one batch per headless `claude -p`, identical except their paths.
P=scripts/prompts
for p in $P/sim_mid.txt $P/sim_l3.txt $P/sim_sort.txt $P/triage.txt; do
  [ -s "$p" ] || { say "missing prompt template $p"; exit 1; }
done
[ -f data/ARMED ] && { say "data/ARMED exists; the paper run never trades -- refusing to run armed"; exit 1; }

# Regenerate the funnel and sorter scripts from the committed seat bodies on every
# run. A stale copy once ran a live date with every seat pointed at a dossier path
# that did not exist (the scripts predated dossierDir); the seats found the right
# file by searching, which is luck, not a guarantee.
$PY scripts/gen_funnel_workflow.py --out data/scratch/funnel-sim.js >> "$LOG" 2>&1 || { say "FAILED funnel generate"; exit 1; }
$PY scripts/gen_sorter_workflow.py --out data/scratch/sim-sorter.js >> "$LOG" 2>&1 || { say "FAILED sorter generate"; exit 1; }
grep -q 'input.dossierDir' data/scratch/funnel-sim.js && grep -q 'input.dossierDir' data/scratch/sim-sorter.js \
  || { say "FAILED generated scripts do not read dossierDir"; exit 1; }

launch() {  # $1 template, $2 args, $3 out, $4 label
  [ -f "$3" ] && { say "SKIP $4 (exists)"; return 0; }
  sed -e "s|ROOTDIR|$PWD|" -e "s|ARGSFILE|$PWD/$2|" -e "s|OUTFILE|$PWD/$3|" -e "s| Do not touch June.||" "$1" > "$S/cur.txt"
  claude -p "$(cat "$S/cur.txt")" --output-format text \
    --allowedTools Read Write Workflow Bash >> "$LOG" 2>&1
  local r=$?
  if [ $r -ne 0 ] || [ ! -f "$3" ]; then
    say "FAILED $4 (exit=$r) -- stopping; rerun this script to resume"; return 1
  fi
  say "done $4"
}
fanout() {  # $1 template, $2 batch-args prefix, $3 out prefix, $4 label
  for a in $(ls "$2"*.json 2>/dev/null | sort -V); do
    n=${a##*-b}; n=${n%.json}
    launch "$1" "$a" "$3$n.json" "$4-b$n" || exit 1
  done
}

say "=== M. mechanical layer 1 ==="
if [ ! -f data/triage-packet-$D.json ]; then
  $PY scripts/run_cascade.py $D --stage mechanical >> "$LOG" 2>&1 || { say "FAILED mechanical"; exit 1; }
  $PY scripts/run_cascade.py $D --stage packet >> "$LOG" 2>&1 || { say "FAILED packet"; exit 1; }
fi

say "=== T. triage (two-no, claude-sonnet-5) ==="
if [ ! -f data/scratch/cascade-out-$D.json ]; then
  # A Workflow script is capped at 512 KB, and a large cohort's spliced packet
  # exceeds it, so the packet is split across parts that each fit. Rows are
  # independent under TWO_NO; the merge refuses a missing or duplicated row.
  ls data/scratch/cascade-$D-p*.js >/dev/null 2>&1 || \
    $PY scripts/cascade_parts.py split --as-of $D --out-prefix data/scratch/cascade-$D-p >> "$LOG" 2>&1 || { say "FAILED cascade split"; exit 1; }
  for js in $(ls data/scratch/cascade-$D-p*.js | sort -V); do
    grep -q "const SONNET = 'claude-sonnet-5'" "$js" && grep -q "model: SONNET" "$js" || { say "FAILED pin missing in $js"; exit 1; }
    k=${js##*-p}; k=${k%.js}
    out=data/scratch/cascade-out-$D-p$k.json
    [ -f "$out" ] && { say "SKIP triage-p$k (exists)"; continue; }
    sed -e "s|SCRIPTFILE|$PWD/$js|" -e "s|OUTFILE|$PWD/$out|" $P/triage.txt > "$S/cascade_prompt.txt"
    claude -p "$(cat "$S/cascade_prompt.txt")" --output-format text \
      --allowedTools Read Write Workflow Bash >> "$LOG" 2>&1
    [ -f "$out" ] || { say "FAILED triage-p$k -- stopping; rerun this script to resume"; exit 1; }
    say "done triage-p$k"
  done
  $PY scripts/cascade_parts.py merge --as-of $D --out-prefix data/scratch/cascade-out-$D-p \
    --dest data/scratch/cascade-out-$D.json >> "$LOG" 2>&1 || { say "FAILED cascade merge"; exit 1; }
fi
if [ ! -f "$S/keeps.json" ]; then
  $PY - "$D" "$S" <<'PY' >> "$LOG" 2>&1 || { say "FAILED keeps"; exit 1; }
import json, sys
d, s = sys.argv[1:]
c = json.load(open(f'data/scratch/cascade-out-{d}.json'))
r = c if 'keeps' in c else c['result']
assert r.get('rule') == 'TWO_NO', r.get('rule')
m = json.load(open(f'data/factsheets-anon-{d}-map.json'))
keeps = sorted(m[x] for x in r['keeps'])
scr = json.load(open(f'data/ruleout-{d}.json'))[d]
json.dump({'as_of': d, 'survivors': scr['survivors']}, open(f'{s}/screen.json', 'w'))
json.dump(keeps, open(f'{s}/keeps.json', 'w'))
print(f"{d}: triage {r['counts']}; {len(keeps)} keeps")
PY
fi

say "=== C. live dossiers ==="
DD=data/dossiers/$D
compile_missing() {  # $1: one-at-a-time if set
  $PY - "$D" "$S" <<'PY' > "$S/need.txt"
import json, os, sys
d, s = sys.argv[1:]
keeps = json.load(open(f'{s}/keeps.json'))
ddir = f'data/dossiers/{d}'
have = {f[:-3] for f in os.listdir(ddir) if f.endswith('.md')} if os.path.isdir(ddir) else set()
print(','.join(t for t in keeps if t not in have))
PY
  # need.txt always ends in a newline, so -s is true even with nothing to
  # compile, and an empty --tickers recompiles EVERY survivor, overwriting the
  # dossiers the earlier layers already read. Test for content instead.
  [ -n "$(tr -d '[:space:]' < "$S/need.txt")" ] || return 0
  if [ -z "$1" ]; then
    say "compiling $(tr ',' '\n' < "$S/need.txt" | wc -l | tr -d ' ') live dossiers"
    $PY scripts/thesis_dossiers.py --screen "$S/screen.json" --tickers "$(cat "$S/need.txt")" >> "$S/compile.log" 2>&1
  else
    say "retrying one at a time: $(cat "$S/need.txt")"
    for t in $(tr ',' ' ' < "$S/need.txt"); do
      sleep 60
      $PY scripts/thesis_dossiers.py --screen "$S/screen.json" --tickers "$t" >> "$S/compile.log" 2>&1
    done
  fi
}
compile_missing
compile_missing one
$PY - "$D" "$S" <<'PY' >> "$LOG" 2>&1 || { say "FAILED dossier census"; exit 1; }
import json, os, sys
d, s = sys.argv[1:]
keeps = json.load(open(f'{s}/keeps.json'))
ddir = f'data/dossiers/{d}'
have = {f[:-3] for f in os.listdir(ddir) if f.endswith('.md')}
man = {r['ticker'] for r in json.load(open(f'{ddir}/manifest.json'))}
assert have == man, f'manifest {len(man)} vs files {len(have)}'
run = [t for t in keeps if t in have]
json.dump(run, open(f'{s}/l2-names.json', 'w'))
print(f'{d}: {len(run)} of {len(keeps)} keeps have live dossiers; never compiled: {sorted(set(keeps) - have)}')
PY

say "=== 2. layer 2 ==="
[ -f data/panel-args-real-sim-$D.json ] || \
  $PY scripts/panel_prepare.py --as-of $D --names-from $S/l2-names.json --tag sim --live >> "$LOG" 2>&1 || { say "FAILED panel_prepare"; exit 1; }
ls $S/mid-args-b*.json >/dev/null 2>&1 || \
  $PY scripts/sim_chain.py split --args data/panel-args-real-sim-$D.json --prefix $S/mid-args-b --layer middle >> "$LOG" 2>&1
fanout $P/sim_mid.txt $S/mid-args-b $S/mid-out-b mid
if cat $S/mid-out-b*.json | grep -qE '"model": ?"claude-sonnet-(5-5|[6-9])'; then
  say "FAILED a layer-2 seat ran on a model other than claude-sonnet-5"; exit 1
fi
[ -f data/panel-results-sim-middle-$D.json ] || \
  $PY scripts/sim_chain.py merge --args data/panel-args-real-sim-$D.json --prefix $S/mid-args-b --out-prefix $S/mid-out-b \
    --dest data/panel-results-sim-middle-$D.json >> "$LOG" 2>&1 || { say "FAILED layer-2 merge"; exit 1; }

say "=== 3. layer 3, survivors only ==="
if [ ! -f data/sim-l3/panel-args-verdict-$D.json ]; then
  $PY - "$D" <<'PY' >> "$LOG" 2>&1 || { say "FAILED verdict args"; exit 1; }
import json, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from verdict_prepare import prepare
d = sys.argv[1]
data = Path('data').resolve()
res = data / f'panel-results-sim-middle-{d}.json'
surv = {r['slug'] for r in json.load(open(res))['summary'] if r['ruler_pass'] is True}
pa = json.load(open(data / f'panel-args-real-sim-{d}.json'))
doc = {n['ticker']: n['docIds'] for n in pa['names']}
a = prepare(d, [res], root=data / 'sim-l3', doc_ids=doc, only=surv)
a['root'] = str(data)
a['dossierDir'] = pa['dossierDir']
assert {n['ticker'] for n in a['names']} == surv
json.dump(a, open(data / 'sim-l3' / f'panel-args-verdict-{d}.json', 'w'), indent=1)
print(f'{d}: {len(surv)} survivors to layer 3')
PY
fi
ls $S/l3-args-b*.json >/dev/null 2>&1 || \
  $PY scripts/sim_chain.py split --args data/sim-l3/panel-args-verdict-$D.json --prefix $S/l3-args-b >> "$LOG" 2>&1
fanout $P/sim_l3.txt $S/l3-args-b $S/l3-out-b l3
[ -f data/panel-results-sim-l3-$D.json ] || \
  $PY scripts/sim_chain.py merge --args data/sim-l3/panel-args-verdict-$D.json --prefix $S/l3-args-b --out-prefix $S/l3-out-b \
    --dest data/panel-results-sim-l3-$D.json >> "$LOG" 2>&1 || { say "FAILED layer-3 merge"; exit 1; }

say "=== 4. editor store, blind sorter ==="
$PY scripts/edited_store.py collect >> "$LOG" 2>&1
[ -f data/sim-sorter-args-$D.json ] || $PY scripts/sim_sorter.py prepare --as-of $D --live >> "$LOG" 2>&1 || { say "FAILED sorter prepare"; exit 1; }
ls $S/sort-args-b*.json >/dev/null 2>&1 || \
  $PY scripts/sim_chain.py split --args data/sim-sorter-args-$D.json --prefix $S/sort-args-b >> "$LOG" 2>&1
fanout $P/sim_sort.txt $S/sort-args-b $S/sort-out-b sort
if [ ! -f data/sim-grades-$D.json ]; then
  $PY scripts/sim_chain.py rows --args data/sim-sorter-args-$D.json --out-prefix $S/sort-out-b --dest $S/sort-rows.json >> "$LOG" 2>&1 \
    && $PY scripts/sim_sorter.py record --as-of $D --rows $S/sort-rows.json >> "$LOG" 2>&1 || { say "FAILED sorter record"; exit 1; }
fi

say "=== 5. paper ledger ==="
[ -f data/paper/$D.json ] || $PY scripts/score_paper.py open --as-of $D >> "$LOG" 2>&1 || { say "FAILED paper ledger"; exit 1; }
tail -3 "$LOG"
say "=== ALL DONE ==="

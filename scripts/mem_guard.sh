#!/bin/bash
# Memory guard for an unattended fan-out chain on the 16 GB Mac mini.
#
# Every 30 s it reads swap used and the system free percentage. Over the high
# mark it SIGSTOPs the chain's bash process. The batch already in flight keeps
# running and saves its output, but the chain cannot launch the next one. Once
# memory falls back under the low mark it SIGCONTs the chain. It never kills
# anything. A watchdog-timeout kernel panic hit this machine at 8.1 of 9.2 GB
# swap with about 100 MB free, so the marks sit well below that.
#
# Usage: mem_guard.sh <chain-pid> [log]
# Exits when the chain exits.
PID=$1
LOG=${2:-data/scratch/mem-guard.log}
PAUSE_SWAP_MB=${PAUSE_SWAP_MB:-5500}   # pause above this much swap used
RESUME_SWAP_MB=${RESUME_SWAP_MB:-4500}
PAUSE_FREE_PCT=${PAUSE_FREE_PCT:-10}   # or below this free percentage
RESUME_FREE_PCT=${RESUME_FREE_PCT:-20}
INTERVAL=${INTERVAL:-30}
[ -n "$PID" ] || { echo "usage: mem_guard.sh <chain-pid> [log]"; exit 2; }
say() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }
swap_mb() { ${SWAP_CMD:-sysctl -n vm.swapusage} | sed -nE 's/.*used = ([0-9]+)(\.[0-9]+)?M.*/\1/p'; }
free_pct() { ${FREE_CMD:-memory_pressure -Q} | sed -nE 's/.*free percentage: ([0-9]+)%.*/\1/p'; }
num() { [[ "$1" =~ ^[0-9]+$ ]]; }
paused=0
say "guarding pid $PID: pause at swap>${PAUSE_SWAP_MB}MB or free<${PAUSE_FREE_PCT}%, resume at swap<${RESUME_SWAP_MB}MB and free>${RESUME_FREE_PCT}%"
while kill -0 "$PID" 2>/dev/null; do
  s=$(swap_mb); f=$(free_pct)
  if ! num "$s" || ! num "$f"; then
    say "could not read memory (swap='$s' free='$f'); leaving the chain as it is"
  elif [ $paused -eq 0 ] && { [ "$s" -gt "$PAUSE_SWAP_MB" ] || [ "$f" -lt "$PAUSE_FREE_PCT" ]; }; then
    kill -STOP "$PID" && paused=1 && say "PAUSED chain (swap ${s}MB, free ${f}%)"
  elif [ $paused -eq 1 ] && [ "$s" -lt "$RESUME_SWAP_MB" ] && [ "$f" -gt "$RESUME_FREE_PCT" ]; then
    kill -CONT "$PID" && paused=0 && say "RESUMED chain (swap ${s}MB, free ${f}%)"
  fi
  [ "${QUIET:-0}" = 1 ] || say "swap ${s}MB free ${f}% paused=$paused"
  sleep "$INTERVAL"
done
say "chain $PID exited; guard stopping"

"""Split data/factsheets-<as_of>.json into one file per ticker.

The triage agent Reads its own name's sheet. A single 500KB JSON would put
335 other companies into every agent's context.

Usage: code/.venv/bin/python scripts/split_factsheets.py 2026-08-17
"""
import json, pathlib, sys

AS_OF = sys.argv[1]
sheets = json.load(open(f"data/factsheets-{AS_OF}.json"))
out = pathlib.Path(f"data/factsheets-{AS_OF}")
out.mkdir(exist_ok=True)
for ticker, row in sheets.items():
    (out / f"{ticker}.txt").write_text(row["sheet"])
print(f"wrote {len(sheets)} sheets to {out}/")

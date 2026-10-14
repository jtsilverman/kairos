"""Write each split name's three prior verdicts to its own file, so the
adjudicator Reads them rather than receiving them inline.

Usage: write_priors.py <scratch-dir> <as-of>
"""
import json, pathlib, sys
SP = sys.argv[1]
AS_OF = sys.argv[2]
amap = json.load(open(f"data/factsheets-anon-{AS_OF}-map.json"))
votes = json.load(open(f"{SP}/v2_votes.json"))
split = json.load(open(f"{SP}/v2_split_slugs.json"))
out = pathlib.Path(f"data/priors-{AS_OF}"); out.mkdir(exist_ok=True)
for slug in split:
    body = []
    for i, v in enumerate(votes[slug], 1):
        body.append(f"PASS {i}: {v['verdict'].upper()}\n"
                    f"  decisive number: {v['decisive_number']}\n"
                    f"  reason: {v['reason']}\n")
    (out / f"{slug}.txt").write_text("\n".join(body))
print(f"wrote {len(split)} prior files to {out}/")

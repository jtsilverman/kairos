"""Write an identity-stripped copy of every fact sheet, for the A/B that
asks whether the triage seat is reading the financial record or its own
memory of the company.

Only the ticker changes. The industry line and every number stay, because
removing them would remove real signal and confound the test. Industry plus
revenue scale still identifies some large companies, so this bounds the
name-recognition effect rather than eliminating it.

Usage: code/.venv/bin/python scripts/anonymize_factsheets.py 2026-08-17
"""
import json, pathlib, re, sys

AS_OF = sys.argv[1]
sheets = json.load(open(f"data/factsheets-{AS_OF}.json"))
out = pathlib.Path(f"data/factsheets-anon-{AS_OF}")
out.mkdir(exist_ok=True)

mapping = {}
leaked = []
for i, ticker in enumerate(sorted(sheets), start=1):
    slug = f"N{i:03d}"
    body = sheets[ticker]["sheet"]
    anon = body.replace(f"TICKER {ticker}", f"TICKER {slug}")
    if re.search(rf"\b{re.escape(ticker)}\b", anon):
        leaked.append(ticker)
    (out / f"{slug}.txt").write_text(anon)
    mapping[slug] = ticker

json.dump(mapping, open(f"data/factsheets-anon-{AS_OF}-map.json", "w"), indent=1)
print(f"wrote {len(mapping)} anonymized sheets to {out}/")
print(f"tickers still present in their own sheet body: {leaked or 'none'}")

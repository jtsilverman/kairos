"""Stage-2 input: one fact sheet per survivor of scripts/ruleout_screen.py.

Reads data/ruleout-<as_of>.json, writes data/factsheets-<as_of>.json as
{ticker: {"sheet": str, "mcap_b": float, "sic": int, "rs": float}}.

mcap_b and rs ride along for the score-against-size correlation check. They
are NEVER inside the sheet the agent reads (kairos.factsheet).

Usage: code/.venv/bin/python scripts/compile_factsheets.py 2026-08-17
"""
import json, sys, time
sys.path.insert(0, "code/src")
from kairos import factsheet
from kairos.data import edgar

AS_OF = sys.argv[1]
SCREEN_PATH = sys.argv[2] if len(sys.argv) > 2 else f"data/ruleout-{AS_OF}.json"
OUT = f"data/factsheets-{AS_OF}.json"

SERIES_TAGS = {
    "revenue": edgar.REVENUE_TAGS,
    "gross_profit": edgar.GROSS_PROFIT_TAGS,
    "operating_income": edgar.OPERATING_INCOME_TAGS,
    "net_income": edgar.NET_INCOME_TAGS,
    "operating_cash_flow": edgar.OPERATING_CASH_FLOW_TAGS,
    "capex": edgar.CAPEX_TAGS,
    "research": edgar.RESEARCH_TAGS,
    "total_assets": edgar.TOTAL_ASSETS_TAGS,
    "stockholders_equity": edgar.EQUITY_TAGS,
    "cash": edgar.CASH_TAGS,
    "long_term_debt": edgar.LT_DEBT_TAGS,
    "interest_expense": edgar.INTEREST_EXPENSE_TAGS,
    "shares": edgar.SHARES_TAGS,
}

survivors = json.load(open(SCREEN_PATH))[AS_OF]["survivors"]
print(f"{AS_OF}: {len(survivors)} survivors", flush=True)

out, refused = {}, []
t0 = time.time()
for i, row in enumerate(survivors):
    t = row["ticker"]
    facts = edgar.fetch_companyfacts(t)
    series = {}
    for name, tags in SERIES_TAGS.items():
        try:
            series[name] = edgar.annual_series(facts, tags, filed_lte=AS_OF)
        except Exception:
            pass
    sub = edgar.fetch_submissions(t)
    sheet = factsheet.build(t, sic_description=sub.get("sicDescription"),
                            series=series)
    if sheet is None:
        refused.append(t); continue
    out[t] = {"sheet": sheet, "mcap_b": row["mcap_b"], "sic": row["sic"],
              "rs": row["rs"]}
    if i % 50 == 0:
        print(f"  {i}/{len(survivors)} ({time.time()-t0:.0f}s)", flush=True)

json.dump(out, open(OUT, "w"), indent=1)
print(f"wrote {len(out)} sheets to {OUT}; refused {refused}")

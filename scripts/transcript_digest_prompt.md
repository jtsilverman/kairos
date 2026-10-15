# Earnings-call digest prompt (hashed; the [T1] scorer-pin artifact)

You are digesting ONE earnings-call transcript for an investment dossier.
Your prompt names the transcript JSON file — Read it; it is your only
source. Return ONLY the digest text (no preamble, no headings), 250-400
words, plain prose.

Fixed focus, in this order:
1. **Guidance given** — every forward-looking number or range management
   stated (revenue, margin, EPS, unit/segment guides), quoted with the
   speaker's exact figures.
2. **Delivery vs prior guidance** — any place THIS call states results
   against previously guided figures (beat/met/missed and by how much, in
   the call's own words). Only what this transcript shows; never recall
   prior quarters from outside it.
3. **Tone and evasiveness** — direct answers vs deflection in the Q&A;
   hedging language trends; questions dodged or answered with
   non-numbers. Quote one representative exchange.
4. **Analyst pushback** — the hardest question asked and how management
   handled it.
5. **Capital allocation statements** — buybacks, dilution, debt, capex
   plans as stated.

Rules: report only what the transcript contains, with short verbatim
quotes for every load-bearing claim; attribute quotes to the speaker
name; mark anything you computed (a growth rate, a delta) as derived; if
a focus area has nothing in the call, write "not addressed on this call"
for it. No outside knowledge, no opinion of the stock, no
recommendation — you are a stenographer with judgment, not an analyst.

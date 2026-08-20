"""prompt-tuning unit 6: strip a company's identity out of its dossier.

Why this exists: at stage 2 the triage seat's yes-rate climbed with market cap
on sheets that never state market cap (23% under $2B, 81% over $50B). The
seats were reading their own familiarity with the company. Re-running the
identical sheets anonymized moved 24 verdicts, 23 of them yes to no.

What this DOES: removes the name-recognition handle. Ticker, legal name,
former names, and the filing slugs that carry the ticker, replaced with one
stable pseudonym across every section so the text still reads as one company.

What this does NOT do, and must never be claimed: it does not defeat
identification. A 10-Q that names its own products ("Aries PCIe Retimers",
"COSMOS software suite") identifies the filer to any reader who knows the
sector. That is why the memorization probe stays the recall gate and why the
leak rate is MEASURED rather than asserted.
"""

from __future__ import annotations

import re

#: Stripped when deriving the bare trade name from a legal name. Order matters
#: only in that longer forms come first.
_SUFFIXES = (
    "incorporated", "corporation", "company", "holdings", "holding",
    "group", "limited", "public limited company", "plc", "inc", "corp",
    "ltd", "llc", "lp", "co", "nv", "sa", "ag", "se", "trust", "the",
)

#: A short token scrubbed everywhere would shred unrelated prose ("Co" inside
#: "Cost", "SA" inside a state name). The ticker is exempt: it is scrubbed on
#: a word boundary and is the whole point.
_MIN_ALIAS_LEN = 4


def _clean(text: str) -> str:
    return re.sub(r"[^\w\s&]", " ", text).strip()


#: What may sit BETWEEN two words of a name in the source text. `_clean`
#: turns every one of these into a space when it builds an alias, so an alias
#: is always spaced while the filing is not: EDGAR prints "COCA-COLA
#: CONSOLIDATED, INC." and the spaced alias never matched it. Only the first
#: word matched, on the hyphen's own word boundary, and a real dossier came
#: out as "CO-002-COLA CONSOLIDATED, INC." naming the filer to three of five
#: seats (measured 2026-08-19). Joining the alias words with this class is
#: what makes the LONGEST alias reachable.
_SEP = r"[\s\-\u2010-\u2015./\\_,]+"


def alias_pattern(alias: str) -> re.Pattern:
    """One alias, matching whatever separator the source puts between its
    words. A single-word alias keeps the plain word-boundary behaviour."""
    return re.compile(
        r"\b" + _SEP.join(re.escape(w) for w in alias.split()) + r"\b",
        re.IGNORECASE)


def aliases_for(ticker: str, *, entity_name: str | None = None,
                former_names: list[str] | None = None) -> list[str]:
    """Every string that names this company, longest first.

    Longest first matters: scrubbing "Astera" before "Astera Labs, Inc."
    leaves " Labs, Inc." behind, which still names the filer.
    """
    out: set[str] = {ticker.upper()}
    for name in [n for n in [entity_name, *(former_names or [])] if n]:
        cleaned = _clean(name)
        out.add(cleaned)
        words = cleaned.split()
        # Drop trailing corporate suffixes one at a time: "Astera Labs Inc"
        # yields "Astera Labs", then "Astera".
        while words and words[-1].lower().strip(".") in _SUFFIXES:
            words = words[:-1]
            if words:
                out.add(" ".join(words))
        while len(words) > 1:
            words = words[:-1]
            out.add(" ".join(words))

    # Spaceless variants: an IR email domain ("extremenetworks.com") carries
    # the name with the space removed, so the spaced alias never matches it.
    # Found by measurement, not by imagination: it identified a real dossier.
    for alias in list(out):
        if " " in alias:
            out.add(alias.replace(" ", ""))

    keep = {a for a in out
            if a.upper() == ticker.upper() or len(a) >= _MIN_ALIAS_LEN}
    return sorted(keep, key=lambda a: (-len(a), a))


#: Exact keys that resolve to ONE filer in a public database. Removing these
#: is cheap and kills the lookup path; it does not touch the harder leaks.
#: Every pattern here was named by an agent that identified a real dossier.
_UNIQUE_KEYS = (
    # IRS Employer Identification Number: "82-3437062"
    (re.compile(r"\b\d{2}-\d{7}\b"), "EIN-REDACTED"),
    # SEC Commission File Number: "001-41979", "000-25711", "1-5828"
    (re.compile(r"\b00[0-9]-\d{4,5}\b"), "FILE-REDACTED"),
    # US phone in the filing cover-page form: "( 408 ) 766-3806"
    (re.compile(r"\(\s?\d{3}\s?\)\s?\d{3}\s?-\s?\d{4}"), "PHONE-REDACTED"),
)


def scrub(text: str, *, ticker: str, slug: str,
          entity_name: str | None = None,
          former_names: list[str] | None = None,
          other_tickers: list[str] | None = None) -> tuple[str, int]:
    """Replace every alias with `slug`. Returns the text and the hit count.

    `other_tickers` covers EDGAR document prefixes that use a former symbol:
    a BlackBerry filing is named `bbry-20260625` while the current ticker is
    `BB`. Measured, not imagined; it identified a real dossier.
    """
    hits = 0
    out = text
    for pattern, replacement in _UNIQUE_KEYS:
        out, n = pattern.subn(replacement, out)
        hits += n
    for extra in (other_tickers or []):
        out, n = re.subn(rf"\b{re.escape(extra)}\b", slug, out, flags=re.IGNORECASE)
        hits += n
    for alias in aliases_for(ticker, entity_name=entity_name,
                             former_names=former_names):
        out, n = alias_pattern(alias).subn(slug, out)
        hits += n
    # EDGAR document slugs carry the ticker without a word boundary in front
    # of the date: "alab-20260604". The loop above misses those.
    return out, hits


def residual_leaks(text: str, *, ticker: str, entity_name: str | None = None,
                   former_names: list[str] | None = None) -> list[str]:
    """Aliases still present after a scrub.

    This is the MECHANICAL leak rate and it is the weaker of the two numbers
    that matter. It catches a variant the scrub missed. It cannot see that a
    named product line still identifies the filer, which is why the recorded
    leak rate also carries a semantic sample.
    """
    found = []
    for alias in aliases_for(ticker, entity_name=entity_name,
                             former_names=former_names):
        if alias_pattern(alias).search(text):
            found.append(alias)
    return found

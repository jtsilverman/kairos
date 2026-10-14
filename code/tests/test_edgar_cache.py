"""prompt-tuning unit 1: the EDGAR disk cache.

EDGAR is uncached across processes today (only an in-process `_cik_cache`
dict), so every re-run of the cascade repays every request. At ten as-of
dates over the screen's survivor set that is tens of thousands of requests,
and it is what stands between the build and finishing.

The cache sits on ONE seam, `_get_bytes`, which every EDGAR fetch routes
through: companyfacts, submissions, the filing index, Form 4 XML and filing
text. A per-fetch-site cache would be five places to get wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kairos.data import edgar


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Every test gets its own cache file and a clean in-process CIK map."""
    monkeypatch.setattr(edgar, "DEFAULT_CACHE_PATH", tmp_path / "edgar-cache.sqlite")
    monkeypatch.setattr(edgar, "_cik_cache", None)
    edgar.reset_cache_stats()


def _counting_fetcher(payloads: dict[str, bytes]):
    """A stand-in for the network. Counts calls per URL."""
    calls: dict[str, int] = {}

    def fetch(url: str) -> bytes:
        calls[url] = calls.get(url, 0) + 1
        try:
            return payloads[url]
        except KeyError:
            raise AssertionError(f"unexpected network fetch: {url}") from None

    return fetch, calls


def test_second_call_for_same_url_does_not_hit_the_network(monkeypatch):
    url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    fetch, calls = _counting_fetcher({url: b'{"cik": 320193}'})
    monkeypatch.setattr(edgar, "_network_get", fetch)

    first = edgar._get_bytes(url)
    second = edgar._get_bytes(url)

    assert first == second == b'{"cik": 320193}'
    assert calls[url] == 1


def test_cache_survives_a_new_process(monkeypatch, tmp_path):
    """A fresh connection against the same file serves the cached body.

    This is the property the in-process `_cik_cache` does not have, and the
    reason a cascade re-run costs full price today.
    """
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    fetch, calls = _counting_fetcher({url: b'{"filings": {}}'})
    monkeypatch.setattr(edgar, "_network_get", fetch)

    edgar._get_bytes(url)
    edgar.close_cache()          # drop the connection, as process exit would
    body = edgar._get_bytes(url)

    assert body == b'{"filings": {}}'
    assert calls[url] == 1


def test_miss_counter_reports_zero_on_a_warm_run(monkeypatch):
    """CHECK 1 asserts a warm cascade re-run reports ZERO cache misses.

    Without an exposed counter that assertion cannot be made, and an
    all-cached run is indistinguishable from a run that silently refetched.
    """
    urls = {
        "https://data.sec.gov/submissions/CIK0000320193.json": b"{}",
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json": b"{}",
    }
    fetch, _ = _counting_fetcher(urls)
    monkeypatch.setattr(edgar, "_network_get", fetch)

    for url in urls:
        edgar._get_bytes(url)
    assert edgar.cache_stats() == {"hits": 0, "misses": 2}

    edgar.reset_cache_stats()
    for url in urls:
        edgar._get_bytes(url)
    assert edgar.cache_stats() == {"hits": 2, "misses": 0}


def test_default_cache_path_is_module_relative():
    """A literal relative path writes a SECOND, stale cache.

    Two such Polygon strays (223 MB and 7.7 MB) were deleted 2026-08-17 after
    a session quoted coverage numbers off the wrong file. Same trap, same fix:
    resolve from the module, never from the working directory.
    """
    path = Path(edgar.__file__).resolve().parents[3] / "data" / "edgar-cache.sqlite"
    # Read the module's own default, not the fixture's monkeypatched one.
    import importlib

    fresh = importlib.reload(edgar)
    try:
        assert fresh.DEFAULT_CACHE_PATH == path
        assert fresh.DEFAULT_CACHE_PATH.is_absolute()
    finally:
        importlib.reload(edgar)


def test_get_json_routes_through_the_cache(monkeypatch):
    """`_get_json` must not keep its own urlopen path around the cache."""
    url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    fetch, calls = _counting_fetcher({url: json.dumps({"cik": 320193}).encode()})
    monkeypatch.setattr(edgar, "_network_get", fetch)

    assert edgar._get_json(url) == {"cik": 320193}
    assert edgar._get_json(url) == {"cik": 320193}
    assert calls[url] == 1


def test_filing_text_routes_through_the_cache(monkeypatch):
    """8-K exhibit bodies are the bulk of the dossier fetch cost."""
    url = "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/ex-99.htm"
    fetch, calls = _counting_fetcher({url: b"<html><body>Results</body></html>"})
    monkeypatch.setattr(edgar, "_network_get", fetch)

    first = edgar.fetch_filing_text(url)
    second = edgar.fetch_filing_text(url)

    assert "Results" in first
    assert first == second
    assert calls[url] == 1

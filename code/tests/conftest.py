"""Suite-wide fixtures.

The EDGAR disk cache (prompt-tuning unit 1) put a real SQLite file under every
test that touches `kairos.data.edgar`. Two things went wrong the first run:

1. Tests that monkeypatch `urllib.request.urlopen` and assert the fetch
   HAPPENED became order-dependent. The first run populated the cache, the
   second run served from it, and `urlopen` was never called.
2. Fake test URLs landed in the real cache at `code/data/edgar-cache.sqlite`,
   poisoning a live artifact with fixture bytes.

Redirecting the cache path for the whole suite fixes both. A test that wants
to exercise the cache itself overrides this with its own path.
"""

from __future__ import annotations

import pytest

from kairos.data import edgar


@pytest.fixture(autouse=True)
def _edgar_cache_is_never_the_real_one(tmp_path, monkeypatch):
    monkeypatch.setattr(edgar, "DEFAULT_CACHE_PATH", tmp_path / "edgar-cache.sqlite")
    edgar.close_cache()
    yield
    edgar.close_cache()

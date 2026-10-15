"""config re-exports the trading knobs when trading_config exists and carries the
research knobs alone when it does not (the public snapshot ships without it)."""

import subprocess
import sys
import textwrap


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True)


def test_config_reexports_the_trading_knobs():
    import pytest
    trading_config = pytest.importorskip("kairos.trading_config")   # absent in the public snapshot
    from kairos import config
    assert config.TRADING_CAPITAL == trading_config.TRADING_CAPITAL
    assert config.get_rh_account_number is trading_config.get_rh_account_number
    assert config._require_env is trading_config._require_env


def test_config_imports_without_trading_config():
    r = _run("""
        import sys
        sys.modules["kairos.trading_config"] = None   # as if the file were absent
        from kairos import config
        assert config.UNDERLYING_LIMITER is not None and config.CONTACT
        assert not hasattr(config, "TRADING_CAPITAL")
        assert not hasattr(config, "get_rh_account_number")
        print("ok")
    """)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ok"


def test_a_broken_import_inside_trading_config_is_not_swallowed():
    r = _run("""
        import sys, types
        sys.modules["kairos.data.no_such_module"] = None
        import importlib.abc, importlib.util
        src = "import kairos.data.no_such_module\\n"
        class Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
            def find_spec(self, name, path, target=None):
                return importlib.util.spec_from_loader(name, self) if name == "kairos.trading_config" else None
            def create_module(self, spec): return None
            def exec_module(self, module): exec(src, module.__dict__)
        sys.meta_path.insert(0, Finder())
        try:
            from kairos import config
        except ModuleNotFoundError as e:
            print("raised", e.name)
    """)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "raised kairos.data.no_such_module"


def test_contact_reads_the_environment():
    r = _run("""
        import os
        os.environ["KAIROS_CONTACT"] = "kairos-research someone@example.org"
        from kairos import config
        from kairos.data import edgar
        print(edgar._ua()["User-Agent"])
    """)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "kairos-research someone@example.org"

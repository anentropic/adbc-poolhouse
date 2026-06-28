"""
Subprocess-isolated regression tests for the PEP 562 import guard (PKG-02/03).

The lazy ``__getattr__`` guard in ``src/adbc_poolhouse/__init__.py`` already
ships (Phase 24/25, CONTEXT D-01): ``import adbc_poolhouse`` is anyio-free, and
accessing an async entry point (e.g. ``create_async_pool``) without anyio raises
an ``ImportError`` naming the ``[async]`` extra. These tests *prove* that guard;
they do not rewrite it.

Each test spawns a fresh child interpreter that installs an
``importlib.abc.MetaPathFinder`` at the front of ``sys.meta_path`` which raises
``ImportError`` for any ``anyio`` import --- simulating anyio-absent without
uninstalling it. A subprocess is mandatory rather than an in-process
monkeypatch: ``sys.modules`` may already cache ``anyio`` /
``adbc_poolhouse._async`` from an earlier test in the same worker, so the
guard's ``try: import _async`` would hit the cache and the negative branch would
never fire (RESEARCH Pitfall 2). A clean child process guarantees a fresh module
table, and each child prints a sentinel so we can prove the asserted branch
actually executed.

This module is anyio-free at collection time (only ``subprocess``, ``sys``,
``textwrap``; no ``@pytest.mark.anyio``) so it collects under the no-anyio CI job
(Plan 04).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

# Child script: block anyio via a meta-path finder, then exercise the guard.
# It prints distinct sentinels for the sync-import (PKG-02) and async-access
# (PKG-03) branches so each test can assert its own branch ran.
_CHILD = textwrap.dedent(
    """
    import importlib.abc
    import sys


    class _Blocker(importlib.abc.MetaPathFinder):
        \"\"\"Raise ImportError for any anyio import, simulating anyio-absent.\"\"\"

        def find_spec(self, name, path, target=None):
            if name == "anyio" or name.startswith("anyio."):
                raise ImportError(f"No module named {name!r} (simulated absent)")
            return None


    sys.meta_path.insert(0, _Blocker())

    # PKG-02: the sync import surface must succeed with anyio absent.
    import adbc_poolhouse

    assert "create_pool" in dir(adbc_poolhouse), dir(adbc_poolhouse)
    print("SYNC_IMPORT_OK")

    # PKG-03: accessing an async entry point must raise an ImportError whose
    # message names the [async] extra (not a bare "No module named 'anyio'").
    try:
        adbc_poolhouse.create_async_pool
    except ImportError as exc:
        assert "[async]" in str(exc), str(exc)
        print("ASYNC_GUARD_OK")
    else:
        raise AssertionError("expected ImportError accessing create_async_pool")
    """
)


def _run_child() -> subprocess.CompletedProcess[str]:
    """Run the anyio-blocked guard child in a fresh interpreter."""
    return subprocess.run(
        [sys.executable, "-c", _CHILD],
        capture_output=True,
        text=True,
        check=True,
    )


def test_sync_import_without_anyio() -> None:
    """PKG-02: `import adbc_poolhouse` succeeds and `create_pool` is present anyio-absent."""
    result = _run_child()
    assert "SYNC_IMPORT_OK" in result.stdout, result.stderr


def test_async_access_without_anyio_raises() -> None:
    """PKG-03: accessing an async symbol anyio-absent raises ImportError naming `[async]`."""
    result = _run_child()
    assert "ASYNC_GUARD_OK" in result.stdout, result.stderr

"""
Sync self-tests for the D-05 AST source-scan guard + the real `_async/` scan.

The `TestAsyncGuard` class exercises ``scan_async_package`` against *synthetic*
source strings written into ``tmp_path``. The `TestRealAsyncPackage` class
(added in Phase 24, now that ``src/adbc_poolhouse/_async/`` exists) scans the REAL
shipped package: it asserts the guard finds zero banned-asyncio / bare-to_thread
violations AND --- via an AST identifier scan --- that none of the 13 backend
config class names appear in executable code (D-24-04 structural genericity; names
in docstring Example blocks are fine because the scan ignores string literals).
The guard is pure stdlib and needs no event loop, so every test here is plain
sync: no ``@pytest.mark.anyio``.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from tests._async_harness.guard import scan_async_package

if TYPE_CHECKING:
    from collections.abc import Iterable

# Repo-relative path to the shipped async package.
_ASYNC_PKG = "src/adbc_poolhouse/_async"

# The 13 backend config class names that must NOT appear in executable _async/
# code (D-24-04). They may appear in docstring Example blocks --- those are string
# literals, which the AST identifier scan below does not see.
_BACKEND_CONFIG_NAMES = frozenset(
    {
        "DuckDBConfig",
        "SnowflakeConfig",
        "BigQueryConfig",
        "ClickHouseConfig",
        "DatabricksConfig",
        "FlightSQLConfig",
        "MSSQLConfig",
        "MySQLConfig",
        "PostgreSQLConfig",
        "QuackConfig",
        "RedshiftConfig",
        "SQLiteConfig",
        "TrinoConfig",
    }
)


def _executable_identifiers(source: str) -> set[str]:
    """
    Return every identifier used in EXECUTABLE code (not in string literals).

    Walks the AST and collects `ast.Name`/`ast.Attribute`/`ast.alias` identifiers.
    Crucially, string literals (including docstrings) are `ast.Constant` nodes, so
    a backend name mentioned only inside a docstring Example block is never
    collected --- which is exactly the D-24-04 distinction (genericity in code,
    examples allowed in prose).
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[0])
            if node.asname:
                names.add(node.asname)
    return names


def _backend_names_in_code(py_files: Iterable[Path]) -> dict[str, list[str]]:
    """Map each scanned file to any backend config names found in its EXECUTABLE code."""
    hits: dict[str, list[str]] = {}
    for py in py_files:
        identifiers = _executable_identifiers(py.read_text(encoding="utf-8"))
        found = sorted(_BACKEND_CONFIG_NAMES & identifiers)
        if found:
            hits[str(py)] = found
    return hits


class TestAsyncGuard:
    """Behaviour of the ``scan_async_package`` import-lint guard (D-05)."""

    def test_bans_asyncio_import(self, tmp_path: Path) -> None:
        """`import asyncio` and `from asyncio import ...` each raise a finding."""
        (tmp_path / "a.py").write_text("import asyncio\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("from asyncio import sleep\n", encoding="utf-8")
        findings = scan_async_package(tmp_path)
        rules = [f.rule for f in findings]
        assert rules.count("banned-asyncio-import") == 2

    def test_to_thread_without_limiter_flagged(self, tmp_path: Path) -> None:
        """A bare `to_thread.run_sync(fn)` is flagged; the `limiter=` form is clean."""
        (tmp_path / "bad.py").write_text(
            "import anyio\nanyio.to_thread.run_sync(fn)\n", encoding="utf-8"
        )
        bad = scan_async_package(tmp_path)
        assert [f.rule for f in bad] == ["to_thread-without-limiter"]

        (tmp_path / "bad.py").unlink()
        (tmp_path / "good.py").write_text(
            "import anyio\nanyio.to_thread.run_sync(fn, limiter=L)\n", encoding="utf-8"
        )
        assert scan_async_package(tmp_path) == []

    def test_noop_absent_dir(self, tmp_path: Path) -> None:
        """An absent root returns [] (D-05 graceful no-op)."""
        assert scan_async_package(tmp_path / "does_not_exist") == []

    def test_noop_empty_dir(self, tmp_path: Path) -> None:
        """An existing-but-empty root returns []."""
        assert scan_async_package(tmp_path) == []

    def test_alias_limitation_documented(self, tmp_path: Path) -> None:
        """A fully-aliased `run_sync` re-import is a known, accepted gap (Pitfall 3)."""
        (tmp_path / "aliased.py").write_text(
            "from anyio.to_thread import run_sync as rs\nrs(fn)\n", encoding="utf-8"
        )
        # Documented limitation: aliased re-import slips past the attribute-chain
        # match, so no `to_thread-without-limiter` finding is produced here.
        assert scan_async_package(tmp_path) == []

    def test_name_based_false_positive_documented(self, tmp_path: Path) -> None:
        """A non-anyio `*.to_thread.run_sync` chain is also flagged (IN-01, name-based)."""
        (tmp_path / "unrelated.py").write_text(
            "my_executor.to_thread.run_sync(fn)\n", encoding="utf-8"
        )
        # The matcher is name-based: any `<x>.to_thread.run_sync(...)` is flagged
        # regardless of what `to_thread` resolves to. Documented, not a bug.
        assert [f.rule for f in scan_async_package(tmp_path)] == ["to_thread-without-limiter"]

    def test_unparseable_file_emits_finding_not_crash(self, tmp_path: Path) -> None:
        """A malformed .py file yields an `unparseable-source` finding, not a crash (IN-02)."""
        (tmp_path / "broken.py").write_text("def oops(:\n", encoding="utf-8")
        (tmp_path / "ok.py").write_text("import asyncio\n", encoding="utf-8")
        findings = scan_async_package(tmp_path)
        rules = sorted(f.rule for f in findings)
        # The broken file does not mask the asyncio ban in its sibling.
        assert rules == ["banned-asyncio-import", "unparseable-source"]

    def test_non_utf8_file_emits_finding_not_crash(self, tmp_path: Path) -> None:
        """A non-UTF-8 .py file yields an `unparseable-source` finding, not a crash (IN-02)."""
        (tmp_path / "latin1.py").write_bytes(b"x = '\xff\xfe'\n")
        findings = scan_async_package(tmp_path)
        assert [f.rule for f in findings] == ["unparseable-source"]


class TestRealAsyncPackage:
    """The guard scans the SHIPPED `_async/` package clean (EDGE-25 static + D-24-04)."""

    def test_scan_real_async_package_is_clean(self) -> None:
        """`scan_async_package("src/adbc_poolhouse/_async") == []` (no asyncio / bare to_thread)."""
        # The guard tolerates an absent root, so this is only meaningful now that
        # the package exists --- assert it does, then assert it is clean.
        assert Path(_ASYNC_PKG).is_dir(), "the _async/ package must exist by Phase 24"
        assert scan_async_package(_ASYNC_PKG) == []

    def test_no_backend_config_names_in_executable_code(self) -> None:
        """
        None of the 13 backend config names appear in executable `_async/` code.

        D-24-04 structural genericity: the async layer touches only the
        `WarehouseConfig` Protocol and the sync `QueuePool`, never a concrete
        backend config class. An AST identifier scan (which ignores string literals,
        so docstring Example blocks naming `DuckDBConfig` are fine) must find zero
        backend config names used as real code.
        """
        py_files = sorted(Path(_ASYNC_PKG).rglob("*.py"))
        assert py_files, "expected .py files under the _async/ package"
        hits = _backend_names_in_code(py_files)
        assert hits == {}, f"backend config names leaked into _async/ executable code: {hits}"

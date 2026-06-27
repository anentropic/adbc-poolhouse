"""
Sync self-tests for the D-05 AST source-scan guard.

These exercise ``scan_async_package`` against *synthetic* source strings written
into ``tmp_path`` -- they never scan the real ``src/adbc_poolhouse/_async/``
package (which does not exist until Phase 24). The guard is pure stdlib and needs
no event loop, so every test here is plain sync: no ``@pytest.mark.anyio``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests._async_harness.guard import scan_async_package

if TYPE_CHECKING:
    from pathlib import Path


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

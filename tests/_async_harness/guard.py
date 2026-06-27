"""
Pure-stdlib AST source-scan guard for the async package (D-05).

This module is deliberately third-party-free: it imports only the standard
library (`ast`, `dataclasses`, `pathlib`). It never imports `anyio`, `trio`,
or `adbc_poolhouse`, and it never executes the source it inspects -- it parses
with `ast.parse` and walks the tree, so scanning is read-only.

It backs the EDGE meta-guards in later phases (EDGE-25/27/28): those tests assert
that [`scan_async_package`][tests._async_harness.guard.scan_async_package] returns
an empty list against the real `src/adbc_poolhouse/_async/` package. Two rules are
enforced:

- `banned-asyncio-import`: any `import asyncio` / `from asyncio import ...`.
- `to_thread-without-limiter`: a `to_thread.run_sync(...)` call missing an
  explicit `limiter=` keyword.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    """
    A single guard violation located in a scanned source file.

    Attributes:
        path: The file in which the violation was found.
        lineno: The 1-based line number of the offending node.
        rule: The rule id -- `"banned-asyncio-import"`,
            `"to_thread-without-limiter"`, or `"unparseable-source"` (a file that
            could not be parsed; see `scan_async_package`).
        message: A human-readable description of the violation.
    """

    path: str
    lineno: int
    rule: str
    message: str


class _GuardVisitor(ast.NodeVisitor):
    """Collects [`Finding`][tests._async_harness.guard.Finding]s for one file."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        """Flag `import asyncio` and `import asyncio.<sub>`."""
        for alias in node.names:
            if alias.name == "asyncio" or alias.name.startswith("asyncio."):
                self.findings.append(
                    Finding(
                        self.path,
                        node.lineno,
                        "banned-asyncio-import",
                        f"`import {alias.name}` is banned in _async/",
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        """Flag `from asyncio import ...` and `from asyncio.<sub> import ...`."""
        module = node.module or ""
        if module == "asyncio" or module.startswith("asyncio."):
            self.findings.append(
                Finding(
                    self.path,
                    node.lineno,
                    "banned-asyncio-import",
                    "`from asyncio import ...` is banned in _async/",
                )
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """Flag `to_thread.run_sync(...)` calls lacking a `limiter=` keyword."""
        if self._is_to_thread_run_sync(node.func):
            has_limiter = any(kw.arg == "limiter" for kw in node.keywords)
            if not has_limiter:
                self.findings.append(
                    Finding(
                        self.path,
                        node.lineno,
                        "to_thread-without-limiter",
                        "`to_thread.run_sync(...)` must pass an explicit `limiter=`",
                    )
                )
        self.generic_visit(node)

    @staticmethod
    def _is_to_thread_run_sync(func: ast.expr) -> bool:
        """
        Return True for `to_thread.run_sync` / `anyio.to_thread.run_sync`.

        Matches on the attribute-chain tail: a `.run_sync` attribute whose value
        is itself an attribute or name resolving to `to_thread`. This catches both
        `anyio.to_thread.run_sync(...)` and a `from anyio import to_thread;
        to_thread.run_sync(...)` form, but NOT a fully-aliased re-import (see
        `scan_async_package`).
        """
        if isinstance(func, ast.Attribute) and func.attr == "run_sync":
            value = func.value
            return (isinstance(value, ast.Attribute) and value.attr == "to_thread") or (
                isinstance(value, ast.Name) and value.id == "to_thread"
            )
        return False


def scan_async_package(root: str | Path) -> list[Finding]:
    """
    Scan every `.py` file under `root` for banned async patterns.

    The scan is read-only: each file is parsed with `ast.parse` and walked; the
    source is never imported or executed. Two rules are enforced -- a literal
    `import asyncio` ban and a requirement that every `to_thread.run_sync(...)`
    call passes an explicit `limiter=` keyword.

    If `root` does not exist, an empty list is returned (D-05 graceful no-op):
    the real `src/adbc_poolhouse/_async/` package is not created until Phase 24,
    so this guard must tolerate its absence and stay green until then.

    The scan is also tolerant of an individual unparseable file (IN-02): a
    `SyntaxError` or `UnicodeDecodeError` from `ast.parse` is captured as an
    `"unparseable-source"` Finding and the scan continues, so one bad file does
    not abort the whole scan or mask violations in its siblings.

    `root` should point at the in-repo async package (e.g.
    `src/adbc_poolhouse/_async/`). It is read with `ast.parse`, never executed,
    so a repo-scoped path carries no code-execution risk; do not pass an
    untrusted or remote path.

    Args:
        root: Directory to scan recursively for `*.py` files. May be absent.

    Returns:
        A list of [`Finding`][tests._async_harness.guard.Finding]s, one per
        violation, in file-then-source order. Empty when `root` is absent, empty,
        or fully compliant -- an EDGE meta-guard asserts exactly this empty list.

    Note:
        Accepted limitation: a fully-aliased re-import such as
        `from anyio.to_thread import run_sync as rs; rs(...)` slips past the
        attribute-chain match and is NOT flagged. The canonical
        `anyio.to_thread.run_sync(...)` form IS caught. This gap is locked by a
        self-test as expected behaviour rather than treated as a bug.

        The matcher is name-based, so the symmetric FALSE-POSITIVE also holds: any
        `<x>.to_thread.run_sync(...)` attribute chain is flagged regardless of what
        `to_thread` resolves to. An unrelated user object named `to_thread` with a
        `run_sync` method (e.g. `my_executor.to_thread.run_sync(...)`) would be
        flagged even though it has nothing to do with `anyio.to_thread`. This is
        acceptable for the in-repo `_async/` target (no such names exist) but is
        called out so a future maintainer is not surprised if the guard fires on a
        non-anyio call.

    Example:
        ```python
        from tests._async_harness.guard import scan_async_package

        findings = scan_async_package("src/adbc_poolhouse/_async/")
        assert findings == []  # the async package is clean
        ```
    """
    root = Path(root)
    if not root.exists():
        return []
    findings: list[Finding] = []
    for py in sorted(root.rglob("*.py")):
        try:
            source = py.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py))
        except (SyntaxError, UnicodeDecodeError) as exc:
            # Tolerant scan (D-05 "graceful"): one malformed or non-UTF-8 file
            # emits a Finding rather than aborting the whole scan with a
            # traceback, so it cannot mask violations in sibling files (IN-02).
            lineno = exc.lineno if isinstance(exc, SyntaxError) and exc.lineno else 0
            findings.append(
                Finding(
                    str(py),
                    lineno,
                    "unparseable-source",
                    f"could not parse source: {type(exc).__name__}: {exc}",
                )
            )
            continue
        visitor = _GuardVisitor(str(py))
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings

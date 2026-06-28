"""
Pure-stdlib AST source-scan guard for the async package (D-05).

This module is deliberately third-party-free: it imports only the standard
library (`ast`, `dataclasses`, `pathlib`). It never imports `anyio`, `trio`,
or `adbc_poolhouse`, and it never executes the source it inspects -- it parses
with `ast.parse` and walks the tree, so scanning is read-only.

It backs the EDGE meta-guards in later phases (EDGE-25/27/28): those tests assert
that [`scan_async_package`][tests._async_harness.guard.scan_async_package] returns
an empty list against the real `src/adbc_poolhouse/_async/` package. Three rules are
enforced:

- `banned-asyncio-import`: any `import asyncio` / `from asyncio import ...`.
- `to_thread-without-limiter`: a `to_thread.run_sync(...)` call missing an
  explicit `limiter=` keyword.
- `banned-asyncio-cancelled-error`: any `asyncio.CancelledError` attribute
  access (EDGE-28, D-25-06; use `anyio.get_cancelled_exc_class()` instead).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class Finding:
    """
    A single guard violation located in a scanned source file.

    Attributes:
        path: The file in which the violation was found.
        lineno: The 1-based line number of the offending node.
        rule: The rule id -- `"banned-asyncio-import"`,
            `"to_thread-without-limiter"`, `"banned-asyncio-cancelled-error"`,
            `"unparseable-source"` (a file that could not be parsed; see
            `scan_async_package`), `"banned-pytest-asyncio-marker"` and
            `"async-test-missing-anyio-marker"` (the test-hygiene rules emitted by
            `scan_async_test_hygiene`), or `"positive-sleep-literal"` (emitted by
            `scan_for_positive_sleep`).
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

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        """Flag `asyncio.CancelledError` attribute access (EDGE-28, D-25-06)."""
        if (
            node.attr == "CancelledError"
            and isinstance(node.value, ast.Name)
            and node.value.id == "asyncio"
        ):
            self.findings.append(
                Finding(
                    self.path,
                    node.lineno,
                    "banned-asyncio-cancelled-error",
                    "`asyncio.CancelledError` is banned in _async/; "
                    "use anyio.get_cancelled_exc_class()",
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
    source is never imported or executed. Three rules are enforced -- a literal
    `import asyncio` ban, a requirement that every `to_thread.run_sync(...)`
    call passes an explicit `limiter=` keyword, and a ban on
    `asyncio.CancelledError` attribute access (use
    `anyio.get_cancelled_exc_class()` instead).

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


def _scan_with(root: str | Path, visitor_factory: Callable[[str], _BaseVisitor]) -> list[Finding]:
    """
    Walk `*.py` files under `root`, applying `visitor_factory` to each parsed tree.

    Factors the pure-stdlib `rglob` + tolerant `ast.parse` + absent-root → `[]`
    machinery shared by `scan_async_test_hygiene` and `scan_for_positive_sleep`,
    so each scanner only supplies its visitor. Matches `scan_async_package`'s
    behaviour exactly: an absent root returns `[]`, and one malformed or non-UTF-8
    file emits an `"unparseable-source"` Finding rather than aborting the scan.

    Args:
        root: Directory to scan recursively for `*.py` files. May be absent.
        visitor_factory: A callable taking the file path and returning a fresh
            `ast.NodeVisitor` whose `findings` list is collected after `visit`.

    Returns:
        A flat list of [`Finding`][tests._async_harness.guard.Finding]s in
        file-then-source order.
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
        visitor = visitor_factory(str(py))
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


class _BaseVisitor(ast.NodeVisitor):
    """A node visitor that accumulates [`Finding`][tests._async_harness.guard.Finding]s."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []


def _is_pytest_mark(decorator: ast.expr, mark: str) -> bool:
    """
    Return True for a `pytest.mark.<mark>` decorator, plain or called.

    Matches both the bare `@pytest.mark.anyio` attribute chain and the called
    `@pytest.mark.asyncio()` form by unwrapping an `ast.Call` to its `.func`. The
    chain is matched structurally: a `.<mark>` attribute whose value is the `mark`
    segment, which may be either an `ast.Attribute` (the full `pytest.mark.<mark>`
    chain) OR an `ast.Name` (the `from pytest import mark; @mark.<mark>` form).
    Matching both forms avoids a false negative on a banned `@mark.asyncio` and a
    false positive on a legitimate `@mark.anyio` written via the imported name.
    """
    node = decorator.func if isinstance(decorator, ast.Call) else decorator
    if not (isinstance(node, ast.Attribute) and node.attr == mark):
        return False
    base = node.value
    return (isinstance(base, ast.Attribute) and base.attr == "mark") or (
        isinstance(base, ast.Name) and base.id == "mark"
    )


class _TestHygieneVisitor(_BaseVisitor):
    """Collects EDGE-27 / D-27-01 test-hygiene findings for one async test file."""

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        """Flag `import asyncio` / `import asyncio.<sub>` in a test module."""
        for alias in node.names:
            if alias.name == "asyncio" or alias.name.startswith("asyncio."):
                self.findings.append(
                    Finding(
                        self.path,
                        node.lineno,
                        "banned-asyncio-import",
                        f"`import {alias.name}` is banned in async tests; "
                        "drive the loop via anyio + @pytest.mark.anyio",
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        """Flag `from asyncio import ...` in a test module."""
        module = node.module or ""
        if module == "asyncio" or module.startswith("asyncio."):
            self.findings.append(
                Finding(
                    self.path,
                    node.lineno,
                    "banned-asyncio-import",
                    "`from asyncio import ...` is banned in async tests; "
                    "drive the loop via anyio + @pytest.mark.anyio",
                )
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """Flag a `@pytest.mark.asyncio` decorator on a sync test function."""
        self._check_decorators(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """Flag `@pytest.mark.asyncio` and missing `@pytest.mark.anyio` on async tests."""
        self._check_decorators(node)
        if node.name.startswith("test_"):
            has_anyio = any(_is_pytest_mark(d, "anyio") for d in node.decorator_list)
            if not has_anyio:
                self.findings.append(
                    Finding(
                        self.path,
                        node.lineno,
                        "async-test-missing-anyio-marker",
                        f"`async def {node.name}` must be decorated "
                        "`@pytest.mark.anyio` to run on the dual-backend axis",
                    )
                )
        self.generic_visit(node)

    def _check_decorators(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Flag any `@pytest.mark.asyncio` decorator (the pytest-asyncio plugin is banned)."""
        for decorator in node.decorator_list:
            if _is_pytest_mark(decorator, "asyncio"):
                self.findings.append(
                    Finding(
                        self.path,
                        node.lineno,
                        "banned-pytest-asyncio-marker",
                        "`@pytest.mark.asyncio` is banned; use `@pytest.mark.anyio` "
                        "so the test runs under both asyncio and trio",
                    )
                )


class _PositiveSleepVisitor(_BaseVisitor):
    """Collects EDGE-30 findings for positive-duration `sleep(...)` literals in one file."""

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """Flag `sleep(<positive literal>)`; allow `sleep(0)` and non-literal args."""
        if self._is_sleep_call(node.func) and node.args:
            first = node.args[0]
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, (int, float))
                and not isinstance(first.value, bool)
                and first.value > 0
            ):
                self.findings.append(
                    Finding(
                        self.path,
                        node.lineno,
                        "positive-sleep-literal",
                        f"`sleep({first.value!r})` introduces real wall-clock time; "
                        "use `sleep(0)` to yield, or gate on an event instead",
                    )
                )
        self.generic_visit(node)

    @staticmethod
    def _is_sleep_call(func: ast.expr) -> bool:
        """Return True for `<mod>.sleep(...)` (e.g. `anyio.sleep`) and bare `sleep(...)`."""
        if isinstance(func, ast.Attribute):
            return func.attr == "sleep"
        return isinstance(func, ast.Name) and func.id == "sleep"


def scan_async_test_hygiene(root: str | Path) -> list[Finding]:
    """
    Scan async test files under `root` for backend-axis hygiene violations.

    Like `scan_async_package`, the scan is read-only (`ast.parse` + walk, never
    imported or executed) and tolerant: an absent `root` returns `[]` (D-05
    graceful no-op) and a single malformed or non-UTF-8 file yields one
    `"unparseable-source"` Finding rather than aborting the scan.

    Three hygiene rules enforce that every async test runs on the dual-backend
    (asyncio + trio) axis rather than being pinned to asyncio (EDGE-27, D-27-01):

    - `banned-asyncio-import`: any `import asyncio` / `from asyncio import ...`.
    - `banned-pytest-asyncio-marker`: any `@pytest.mark.asyncio` decorator (the
      pytest-asyncio plugin pins a test to asyncio; use `@pytest.mark.anyio`).
    - `async-test-missing-anyio-marker`: any `async def test_*` lacking a
      `@pytest.mark.anyio` decorator.

    The anyio-parametrized signal is the PRESENCE of `@pytest.mark.anyio`, NOT a
    literal `anyio_backend` argument: many hardened tests get the backend axis via
    the marker plus a plain async fixture, so requiring the literal argument would
    false-positive. Only `async def` functions whose name starts with `test_` are
    checked for the missing-marker rule.

    `root` should point at the in-repo async test tree (e.g. `tests/async/`). It is
    parsed, never executed, so a repo-scoped path carries no code-execution risk;
    do not pass an untrusted or remote path.

    Args:
        root: Directory to scan recursively for `*.py` files. May be absent.

    Returns:
        A list of [`Finding`][tests._async_harness.guard.Finding]s, one per
        violation, in file-then-source order. Empty when `root` is absent, empty,
        or fully compliant -- a Wave 3 meta-test asserts exactly this empty list.

    Example:
        ```python
        from tests._async_harness.guard import scan_async_test_hygiene

        findings = scan_async_test_hygiene("tests/async/")
        assert findings == []  # every async test rides the dual-backend axis
        ```
    """
    return _scan_with(root, _TestHygieneVisitor)


def scan_for_positive_sleep(root: str | Path) -> list[Finding]:
    """
    Scan files under `root` for positive-duration `sleep(...)` literals (EDGE-30).

    Like `scan_async_package`, the scan is read-only (`ast.parse` + walk, never
    imported or executed) and tolerant: an absent `root` returns `[]` (D-05
    graceful no-op) and a single malformed or non-UTF-8 file yields one
    `"unparseable-source"` Finding rather than aborting the scan.

    A real-time sleep makes a test slow and flaky; under the trio `MockClock` a
    `sleep(0)` yields without advancing wall-clock time, and a worker is better
    gated on an event than on a timer. The rule flags any `sleep(...)` call whose
    first positional argument is a numeric literal strictly greater than zero,
    matching both `<mod>.sleep(...)` (e.g. `anyio.sleep`, `time.sleep`) and a bare
    `sleep(...)`. It ALLOWS (emits no finding for) `sleep(0)`, `sleep(0.0)`, and
    any non-literal argument such as `sleep(deadline)` --- those carry no fixed
    wall-clock cost the scanner can see.

    `root` should point at the in-repo async test tree (e.g. `tests/async/`). It is
    parsed, never executed, so a repo-scoped path carries no code-execution risk;
    do not pass an untrusted or remote path.

    Args:
        root: Directory to scan recursively for `*.py` files. May be absent.

    Returns:
        A list of [`Finding`][tests._async_harness.guard.Finding]s with the rule id
        `"positive-sleep-literal"`, one per offending call, in file-then-source
        order. Empty when `root` is absent, empty, or free of positive sleep
        literals -- a Wave 3 meta-test asserts exactly this empty list.

    Example:
        ```python
        from tests._async_harness.guard import scan_for_positive_sleep

        findings = scan_for_positive_sleep("tests/async/")
        assert findings == []  # no real-time sleeps in the async suite
        ```
    """
    return _scan_with(root, _PositiveSleepVisitor)

"""
Packaging-metadata assertions for the optional-dependency extras (PKG-01).

This module is deliberately anyio-free at import time — it imports only
`importlib.metadata`, carries no `@pytest.mark.anyio`, and never touches the
`adbc_poolhouse._async` surface. That keeps it collectable under the no-anyio
CI guard job (Plan 04), where it acts as a belt-and-suspenders check beside the
`uv sync --locked` lockfile-coherence gate: it proves the installed package
metadata actually advertises the `async` extra and aggregates it into `all`.
"""

from __future__ import annotations

import importlib.metadata


def test_async_extra_is_declared() -> None:
    """The installed package metadata declares the `async` optional extra."""
    meta = importlib.metadata.metadata("adbc-poolhouse")
    provides = meta.get_all("Provides-Extra") or []
    assert "async" in provides, f"`async` extra missing from {provides!r}"


def test_all_extra_is_declared() -> None:
    """The `all` aggregate extra is also advertised in package metadata."""
    meta = importlib.metadata.metadata("adbc-poolhouse")
    provides = meta.get_all("Provides-Extra") or []
    assert "all" in provides, f"`all` extra missing from {provides!r}"

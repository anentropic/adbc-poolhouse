"""
STREAM-06 two-tier connection guard --- unit tests for the plan 29-02 deliverable.

Plan 29-02 adds the ONE new bit of production machinery this phase introduces: a
persistent `_reader_open` lifetime flag on `AsyncConnection` plus a two-tier
`from_reader` entry guard (D-29-08/09/10). The end-to-end STREAM-06 assertions
(`test_reader_busy.py`) drive this guard through `cursor.fetch_record_batch()`,
which does not exist until plan 29-03, so those stay RED until then.

This file exercises the guard machinery DIRECTLY at the `_enter_offload` /
`_offloading` boundary --- the exact surface plan 29-02 ships --- so the plan's own
deliverable has a GREEN gate independent of the not-yet-existing reader. It sets
`_reader_open` / `_in_use` by hand (the reader that owns them lands in plan 03) and
asserts the two tiers:

- **Foreign tier:** a foreign caller (`_offloading()` / `_enter_offload()`) is
  rejected with `ConnectionBusyError` while `_reader_open` is True.
- **Reentrancy exemption:** the reader's own pull (`from_reader=True`) is exempt
  from the `_reader_open` tier but STILL takes the per-call `_in_use` C-access tier.
- **`_exit_offload` clears `_in_use` only** --- it never touches `_reader_open`.

The guard is synchronous check-and-set on the single-threaded loop, so these need
no event loop, no `@pytest.mark.anyio`, and no `concurrency_marks`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from adbc_poolhouse import ConnectionBusyError

if TYPE_CHECKING:
    from collections.abc import Callable

    from adbc_poolhouse._async._connection import AsyncConnection
    from tests._async_harness.stubs import BlockingStubConnection

    _StubFactory = Callable[[], tuple[AsyncConnection, BlockingStubConnection]]


class TestReaderOpenFlagDefault:
    """`_reader_open` is a persistent bool, distinct from `_in_use`, defaulting False."""

    def test_reader_open_defaults_false(self, make_stub_async_connection: _StubFactory) -> None:
        """A fresh `AsyncConnection` has `_reader_open is False` (and `_in_use is False`)."""
        conn, _ = make_stub_async_connection()
        assert conn._reader_open is False  # noqa: SLF001
        assert conn._in_use is False  # noqa: SLF001

    def test_reader_open_is_independent_of_in_use(
        self, make_stub_async_connection: _StubFactory
    ) -> None:
        """The two flags are separate attributes --- setting one leaves the other alone."""
        conn, _ = make_stub_async_connection()
        conn._reader_open = True  # noqa: SLF001
        assert conn._in_use is False  # noqa: SLF001 --- reader lifetime tier only


class TestForeignTierRejected:
    """STREAM-06: a foreign caller is rejected while a reader is live (`_reader_open`)."""

    def test_enter_offload_foreign_raises_while_reader_open(
        self, make_stub_async_connection: _StubFactory
    ) -> None:
        """
        `_enter_offload()` (foreign, `from_reader` defaults False) raises busy.

        With `_reader_open=True` and `_in_use=False`, a foreign caller hits the
        reader-lifetime tier and gets `ConnectionBusyError`; `_in_use` is NOT set
        (the body never claims the connection).
        """
        conn, _ = make_stub_async_connection()
        conn._reader_open = True  # noqa: SLF001 --- simulate a live reader (set by plan 03)
        with pytest.raises(ConnectionBusyError):
            conn._enter_offload()  # noqa: SLF001
        assert conn._in_use is False  # noqa: SLF001 --- rejected before the claim

    def test_offloading_foreign_raises_while_reader_open(
        self, make_stub_async_connection: _StubFactory
    ) -> None:
        """The `_offloading()` context manager rejects a foreign caller the same way."""
        conn, _ = make_stub_async_connection()
        conn._reader_open = True  # noqa: SLF001
        entered = False
        with pytest.raises(ConnectionBusyError), conn._offloading():  # noqa: SLF001
            entered = True
        assert entered is False  # the guarded body never ran
        assert conn._in_use is False  # noqa: SLF001


class TestReentrancyExemption:
    """STREAM-06: the reader's own pull (`from_reader=True`) is exempt from the reader tier."""

    def test_enter_offload_from_reader_exempt_from_reader_tier(
        self, make_stub_async_connection: _StubFactory
    ) -> None:
        """
        `_enter_offload(from_reader=True)` succeeds while `_reader_open=True`.

        The reader's own pull skips ONLY the `_reader_open` tier and still claims
        the per-call `_in_use` C-access tier (sets `_in_use=True`).
        """
        conn, _ = make_stub_async_connection()
        conn._reader_open = True  # noqa: SLF001
        conn._enter_offload(from_reader=True)  # noqa: SLF001 --- must NOT raise
        assert conn._in_use is True  # noqa: SLF001 --- still took the C-access tier

    def test_offloading_from_reader_still_takes_in_use_tier(
        self, make_stub_async_connection: _StubFactory
    ) -> None:
        """
        The reader's pull still takes `_in_use`, so a NESTED foreign call is rejected.

        Inside a `from_reader=True` span (`_in_use` held), even another
        `from_reader=True` caller is rejected by the unconditional `_in_use` tier
        --- the C-access guard is never bypassed.
        """
        conn, _ = make_stub_async_connection()
        conn._reader_open = True  # noqa: SLF001
        with conn._offloading(from_reader=True):  # noqa: SLF001
            assert conn._in_use is True  # noqa: SLF001
            with pytest.raises(ConnectionBusyError):
                conn._enter_offload(from_reader=True)  # noqa: SLF001 --- _in_use tier
        assert conn._in_use is False  # noqa: SLF001 --- released on span exit


class TestInUseTierUnconditional:
    """The per-call `_in_use` tier is unconditional --- `from_reader` never bypasses it."""

    def test_in_use_rejects_even_from_reader(
        self, make_stub_async_connection: _StubFactory
    ) -> None:
        """
        With `_in_use=True`, both a foreign caller AND a `from_reader=True` caller raise.

        The `_in_use` check is FIRST and unconditional (Pitfall 5 ordering); the
        reentrancy exemption applies only to the `_reader_open` tier.
        """
        conn, _ = make_stub_async_connection()
        conn._in_use = True  # noqa: SLF001 --- a call already in flight
        with pytest.raises(ConnectionBusyError):
            conn._enter_offload()  # noqa: SLF001 --- foreign
        with pytest.raises(ConnectionBusyError):
            conn._enter_offload(from_reader=True)  # noqa: SLF001 --- reader too


class TestExitOffloadNeverClearsReaderOpen:
    """`_exit_offload` clears `_in_use` ONLY; `_reader_open` survives the span (D-29-11)."""

    def test_exit_offload_clears_in_use_only(
        self, make_stub_async_connection: _StubFactory
    ) -> None:
        """After a `from_reader=True` span exits, `_in_use` is False, `_reader_open` stays True."""
        conn, _ = make_stub_async_connection()
        conn._reader_open = True  # noqa: SLF001
        with conn._offloading(from_reader=True):  # noqa: SLF001
            assert conn._in_use is True  # noqa: SLF001
        assert conn._in_use is False  # noqa: SLF001 --- cleared by _exit_offload
        assert conn._reader_open is True  # noqa: SLF001 --- untouched by the offload span

    def test_direct_exit_offload_leaves_reader_open(
        self, make_stub_async_connection: _StubFactory
    ) -> None:
        """A bare `_exit_offload()` call never writes `_reader_open`."""
        conn, _ = make_stub_async_connection()
        conn._reader_open = True  # noqa: SLF001
        conn._in_use = True  # noqa: SLF001
        conn._exit_offload()  # noqa: SLF001
        assert conn._in_use is False  # noqa: SLF001
        assert conn._reader_open is True  # noqa: SLF001

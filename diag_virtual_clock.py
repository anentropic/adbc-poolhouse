"""
TEMPORARY diagnostic (PR #32 CI investigation) — repo-root so basedpyright skips it.

Distinguishes two hypotheses for the Linux-only Phase-25 cancel-test failures:

  A. pure-async deadline   : `fail_after(5)` over `anyio.sleep(3600)` (no thread)
  B. thread deadline       : `fail_after(5)` over a blocked `to_thread` worker
                             with abandon_on_cancel=True (isolates "does the
                             virtual clock autojump past a blocked worker?")

If A works (real~0, timed_out) but B does not on Linux => the virtual clock does
NOT advance past a pending to_thread worker on Linux => H1 (clock frozen). If both
work on Linux => autojump is fine and the real failure is the adbc_cancel->release
path => H2.

Run: `.venv/bin/python diag_virtual_clock.py`
"""

from __future__ import annotations

import threading
import time
from typing import Any

import aiotools
import anyio

DEADLINE = 5.0
WORKER_REAL_CAP = 8.0  # orphaned/abandoned worker self-releases; never hangs CI


async def _case_pure_async() -> dict[str, Any]:
    t0 = time.monotonic()
    v0 = anyio.current_time()
    timed_out = False
    try:
        with anyio.fail_after(DEADLINE):
            await anyio.sleep(3600)
    except TimeoutError:
        timed_out = True
    return {
        "real": round(time.monotonic() - t0, 3),
        "virtual": round(anyio.current_time() - v0, 3),
        "timed_out": timed_out,
    }


async def _case_thread() -> dict[str, Any]:
    ev = threading.Event()

    def _block() -> str:
        ev.wait(timeout=WORKER_REAL_CAP)
        return "done"

    t0 = time.monotonic()
    v0 = anyio.current_time()
    timed_out = False
    try:
        with anyio.fail_after(DEADLINE):
            await anyio.to_thread.run_sync(_block, abandon_on_cancel=True)
    except TimeoutError:
        timed_out = True
    finally:
        ev.set()
    return {
        "real": round(time.monotonic() - t0, 3),
        "virtual": round(anyio.current_time() - v0, 3),
        "timed_out": timed_out,
    }


def _run(backend: str) -> None:
    out: dict[str, dict[str, Any]] = {}

    async def _main() -> None:
        if backend == "asyncio":
            with aiotools.VirtualClock().patch_loop():
                out["pure"] = await _case_pure_async()
                out["thread"] = await _case_thread()
        else:
            out["pure"] = await _case_pure_async()
            out["thread"] = await _case_thread()

    if backend == "trio":
        import trio
        import trio.testing

        trio.run(_main, clock=trio.testing.MockClock(autojump_threshold=0))
    else:
        anyio.run(_main, backend="asyncio")

    for case, r in out.items():
        autojump = bool(r["real"] < 1.0 and r["timed_out"])
        print(
            f"[DIAG {backend}/{case}] real={r['real']}s virtual={r['virtual']}s "
            f"timed_out={r['timed_out']} => autojump_works={autojump}"
        )


if __name__ == "__main__":
    _run("asyncio")
    _run("trio")

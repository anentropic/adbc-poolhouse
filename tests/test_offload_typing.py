"""
Static-typing regression pinning the PKG-05 offload tightening (D-03).

Phase 26 replaced the loose `Callable[..., _T]` + `*args: object` signature on
`offload` / `cancellable_offload` with the PEP 646 `TypeVarTuple` / `Unpack`
variadic forwarder, so a wrong-typed positional argument at the dispatch boundary
is now a basedpyright error instead of being silently accepted.

This module is the expect-error fixture that locks that win in: the
`reveal-the-error` calls below are annotated with
`# pyright: ignore[reportArgumentType]`. basedpyright reports `0 errors` on this
file ONLY while the tightened signature is in place --- if the offload signature
ever regressed to `*args: object`, the suppressed `reportArgumentType` would stop
firing and basedpyright would flag the ignore as *unnecessary*
(`reportUnnecessaryTypeIgnoreComment`), turning this fixture red. The positive
`assert_type(...)` calls additionally pin that a correctly-typed call still
returns the callable's exact return type.

The module is anyio-free at import time: the real `offload` /
`cancellable_offload` symbols are imported only under `TYPE_CHECKING`, so pytest
can collect this file in the no-anyio environment. The single runtime test is a
trivial sentinel --- the real assertion is performed statically by basedpyright
(`.venv/bin/basedpyright tests/test_offload_typing.py` must report `0 errors`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_type

if TYPE_CHECKING:
    from adbc_poolhouse._async._cancel import cancellable_offload
    from adbc_poolhouse._async._offload import offload

    # A typed stand-in callable mirroring a real bound driver method: it takes an
    # `int` positionally and returns a `str`. The offload boundary must now check
    # the forwarded positional against this signature.
    def _takes_int(value: int) -> str:
        return str(value)

    def _adbc_cancel() -> None:  # the leading param of cancellable_offload
        return None

    async def _offload_typing_probe() -> None:
        """Static probe --- never executed; basedpyright type-checks the body."""
        from anyio import CapacityLimiter

        limiter = CapacityLimiter(1)

        # --- offload: positive (correct positional type-checks, return preserved) ---
        good = await offload(_takes_int, 7, limiter=limiter)
        assert_type(good, str)

        # --- offload: NEGATIVE (the PKG-05 win) -------------------------------
        # A `str` given where `_takes_int` expects an `int` is now rejected. The
        # ignore is REQUIRED: drop it and basedpyright flags the line, proving the
        # checker bites. If the signature regressed to `*args: object` the error
        # would vanish and this ignore would become unnecessary (also red).
        bad = await offload(
            _takes_int,
            "not-an-int",  # pyright: ignore[reportArgumentType]
            limiter=limiter,
        )
        assert_type(bad, str)

        # --- cancellable_offload: same tightening, leading adbc_cancel intact ---
        good_c = await cancellable_offload(_adbc_cancel, _takes_int, 7, limiter=limiter)
        assert_type(good_c, str)

        bad_c = await cancellable_offload(
            _adbc_cancel,
            _takes_int,
            "not-an-int",  # pyright: ignore[reportArgumentType]
            limiter=limiter,
        )
        assert_type(bad_c, str)

    # Reference the probe so it is not reported unused; it is never executed
    # (the assertions it carries are checked statically by basedpyright).
    _ = _offload_typing_probe


def test_offload_typing_fixture_is_static() -> None:
    """Sentinel: the real PKG-05 assertion is static (basedpyright, 0 errors)."""
    assert True

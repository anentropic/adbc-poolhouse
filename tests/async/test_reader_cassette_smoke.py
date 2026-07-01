"""
Snowflake cassette streaming smoke (assumption A1) --- Wave-0 probe.

Resolves research assumption A1: *can the checked-in Snowflake cassette
(`snowflake_arrow_round_trip`) replay a streaming `fetch_record_batch`?* The answer
gates how much of the Snowflake EDGE-33 leg can run offline in CI.

**Outcome (recorded in 29-01-SUMMARY.md):** NO. The `pytest-adbc-replay` replay
cursor implements only `fetch_arrow_table` (a materialized `pyarrow.Table`) plus
the row-based `fetchall`/`fetchone`/`fetchmany`; it has NO `fetch_record_batch`
method. In replay mode a `fetch_record_batch()` call therefore cannot be served
from the cassette --- the recorded interaction is a single materialized Arrow
result, not a streaming reader. Consequently BOTH Snowflake reader legs in
`test_reader_lifetime.py` are scoped out of the offline cassette run: they carry
`@pytest.mark.snowflake` (recording-only, skipped in CI) and are documented as
manual-only re-record follow-ups per `29-VALIDATION.md` §Manual-Only Verifications.
DuckDB carries the mandatory EDGE-33 coverage and is NOT gated on this result.

This smoke asserts the A1 fact directly against the installed replay plugin, so a
future plugin version that DOES gain `fetch_record_batch` replay support will make
this test fail loudly --- the signal to re-enable the offline Snowflake reader
legs. It never opens a live connection and never hangs.
"""

from __future__ import annotations

import importlib.util

import pytest


class TestA1CassetteStreamingSupport:
    """A1 probe: whether the replay plugin supports streaming `fetch_record_batch`."""

    def test_replay_cursor_lacks_fetch_record_batch(self) -> None:
        """
        The `pytest-adbc-replay` replay cursor exposes no `fetch_record_batch`.

        This is the mechanism behind A1: the cassette stores a single materialized
        Arrow result and the replay cursor serves it via `fetch_arrow_table`, with no
        streaming-reader method. If a future plugin version adds
        `fetch_record_batch`, this assertion fails --- re-enable the offline Snowflake
        reader legs in `test_reader_lifetime.py` and re-record the cassette with a
        streaming interaction.
        """
        if importlib.util.find_spec("pytest_adbc_replay") is None:
            pytest.skip("pytest-adbc-replay not installed")
        from pytest_adbc_replay import _cursor as replay_cursor

        replay_cursor_cls = replay_cursor.ReplayCursor
        assert not hasattr(replay_cursor_cls, "fetch_record_batch"), (
            "Replay cursor gained fetch_record_batch: re-enable the offline Snowflake "
            "reader legs and re-record the streaming cassette (A1 changed)."
        )
        # The materialized-table method IS present --- proving the cassette serves a
        # table, not a streaming reader.
        assert hasattr(replay_cursor_cls, "fetch_arrow_table")

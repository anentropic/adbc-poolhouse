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

**Update (pytest-adbc-replay >= 1.1):** the plugin now exposes `fetch_record_batch`,
so the plugin half of A1 has changed. The cassette half has not --- the checked-in
`snowflake_arrow_round_trip` cassette still records a materialized result, not a
streaming interaction, so the Snowflake reader legs cannot run offline until the
cassette is re-recorded against the live driver (needs Snowflake credentials). This
smoke keeps a two-way signal without blocking CI: on the older plugin it re-asserts
A1, and on >= 1.1 it skips with the remaining re-record follow-up. It never opens a
live connection and never hangs.
"""

from __future__ import annotations

import importlib.util

import pytest


class TestA1CassetteStreamingSupport:
    """A1 probe: whether the replay plugin supports streaming `fetch_record_batch`."""

    def test_cassette_streaming_replay_support(self) -> None:
        """
        Track whether the replay plugin can serve a streaming `fetch_record_batch`.

        A1 (recorded at Phase 29) was that `pytest-adbc-replay` exposed no
        `fetch_record_batch`, so the cassette --- a single materialized Arrow result
        served via `fetch_arrow_table` --- could not replay a streaming reader, and
        both Snowflake reader legs in `test_reader_lifetime.py` were skipped.

        `pytest-adbc-replay` >= 1.1 adds a `fetch_record_batch` method, so the plugin
        half of A1 has changed. The *cassette* half has not: the checked-in
        `snowflake_arrow_round_trip` cassette records a materialized result, not a
        streaming interaction, so the Snowflake reader legs still cannot run offline
        until the cassette is re-recorded against the live driver (needs Snowflake
        credentials). That re-record + re-enable is tracked as a follow-up (ROADMAP
        Backlog / PROJECT.md Active candidates); it is not a hard failure here.

        This smoke keeps a signal in both directions without blocking CI: on the older
        plugin it re-asserts A1 (no streaming method); on >= 1.1 it skips with the
        remaining re-record follow-up.
        """
        if importlib.util.find_spec("pytest_adbc_replay") is None:
            pytest.skip("pytest-adbc-replay not installed")
        from pytest_adbc_replay import _cursor as replay_cursor

        replay_cursor_cls = replay_cursor.ReplayCursor
        # The materialized-table method is always present --- the cassette serves a
        # table, which is the standing constraint regardless of plugin version.
        assert hasattr(replay_cursor_cls, "fetch_arrow_table")

        if hasattr(replay_cursor_cls, "fetch_record_batch"):
            pytest.skip(
                "pytest-adbc-replay >= 1.1 exposes fetch_record_batch, but the "
                "snowflake_arrow_round_trip cassette records a materialized result, "
                "not a streaming interaction. Re-record the cassette against the live "
                "driver (needs Snowflake credentials) and re-enable the Snowflake "
                "reader legs in test_reader_lifetime.py. Follow-up tracked in ROADMAP "
                "Backlog."
            )
        # Older plugin: A1 holds unchanged --- no streaming replay, legs stay skipped.

"""
Snowflake cassette streaming smoke (assumption A1).

Research assumption A1: *can the checked-in Snowflake cassette
(`snowflake_arrow_round_trip`) replay a streaming `fetch_record_batch`?* The answer
gates how much of the Snowflake EDGE-33 leg can run offline in CI.

**Original outcome (Phase 29, `pytest-adbc-replay` 1.0.x):** NO. The replay cursor
implemented only `fetch_arrow_table` plus row-based fetches --- it had no
`fetch_record_batch`, so a streaming pull could not be served from the cassette and
both Snowflake reader legs in `test_reader_lifetime.py` were skipped offline.

**Resolved (`pytest-adbc-replay` >= 1.1):** the replay cursor now exposes
`fetch_record_batch` and streams it from the recorded Arrow result. The drain leg
(`test_drain_then_checkin_rows_snowflake`) therefore runs offline against the existing
cassette with no re-record --- the recorded result is served as a `RecordBatchReader`.
The dev-dependency floor is pinned to `pytest-adbc-replay >= 1.1.0` to guarantee it.

The read-after-checkin leg (`test_read_after_checkin_raises_arrow_invalid_snowflake`)
stays live-driver-only: its native closed-stream `ArrowInvalid` is a property of the
live C-level stream being invalidated on checkin, which a file-backed replay reader
cannot model --- no cassette (re-recorded or otherwise) reproduces it. DuckDB's
`test_read_after_checkin_raises_arrow_invalid_duckdb` carries that coverage offline.

This smoke guards the standing dependency: the drain leg needs both a materialized
`fetch_arrow_table` and a streaming `fetch_record_batch` on the replay cursor. It never
opens a live connection and never hangs.
"""

from __future__ import annotations

import importlib.util

import pytest


class TestA1CassetteStreamingSupport:
    """A1 guard: the replay plugin exposes the streaming reader the drain leg depends on."""

    def test_replay_cursor_supports_streaming(self) -> None:
        """
        The `pytest-adbc-replay` cursor exposes both materialized and streaming reads.

        `fetch_arrow_table` serves the cassette's materialized result; `fetch_record_batch`
        (added in `pytest-adbc-replay` >= 1.1, the pinned floor) streams that same result
        as a `RecordBatchReader`. Together they let `test_drain_then_checkin_rows_snowflake`
        run offline. If a future pin dropped the plugin below 1.1, this guard fails ---
        the signal that the offline Snowflake drain leg lost its streaming replay.
        """
        if importlib.util.find_spec("pytest_adbc_replay") is None:
            pytest.skip("pytest-adbc-replay not installed")
        from pytest_adbc_replay import _cursor as replay_cursor

        replay_cursor_cls = replay_cursor.ReplayCursor
        assert hasattr(replay_cursor_cls, "fetch_arrow_table")
        assert hasattr(replay_cursor_cls, "fetch_record_batch"), (
            "pytest-adbc-replay < 1.1 has no fetch_record_batch: the offline Snowflake "
            "drain leg in test_reader_lifetime.py cannot replay streaming. Pin "
            "pytest-adbc-replay >= 1.1.0."
        )

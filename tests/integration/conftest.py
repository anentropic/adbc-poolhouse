"""Fixtures for Snowflake integration tests (TEST-03)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa  # type: ignore[import-untyped]
import pytest
from dotenv import load_dotenv
from syrupy.extensions.json import JSONSnapshotExtension

from adbc_poolhouse import SnowflakeConfig, create_pool

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion
    from syrupy.types import PropertyFilter, PropertyMatcher, SerializableData, SerializedData

# Keys to strip from Arrow schema-level metadata.
# Roadmap-specified: queryId, elapsedTime, timestamps.
# Stripped defensively even if current driver (adbc-driver-snowflake==1.10.0) does not emit them.
_NON_DETERMINISTIC_META_KEYS: frozenset[bytes] = frozenset(
    [
        b"queryId",
        b"elapsedTime",
        b"elapsed_time",
        b"timestamp",
        b"statementId",
        b"queryTime",
    ]
)


class SnowflakeArrowSnapshotSerializer(JSONSnapshotExtension):
    """
    Syrupy extension that serializes Arrow tables to stable JSON.

    Strips non-deterministic schema-level metadata before serialization.
    Schema fields include Arrow type, name, nullable, and Snowflake type metadata.
    Rows are serialized as a list of row dicts via pyarrow.Table.to_pylist().
    """

    file_extension = "json"

    def serialize(
        self,
        data: SerializableData,
        *,
        exclude: PropertyFilter | None = None,
        include: PropertyFilter | None = None,
        matcher: PropertyMatcher | None = None,
    ) -> SerializedData:
        """Serialize an Arrow table to stable JSON."""
        if not isinstance(data, pa.Table):  # type: ignore[misc]
            return super().serialize(data, exclude=exclude, include=include, matcher=matcher)

        # Strip non-deterministic schema-level metadata
        raw_meta: dict[bytes, bytes] = data.schema.metadata or {}  # type: ignore[union-attr]
        clean_meta: dict[bytes, bytes] = {
            k: v for k, v in raw_meta.items() if k not in _NON_DETERMINISTIC_META_KEYS
        }

        schema_repr: dict[str, Any] = {
            "fields": [
                {
                    "name": field.name,  # type: ignore[union-attr]
                    "type": str(field.type),  # type: ignore[union-attr]
                    "nullable": field.nullable,  # type: ignore[union-attr]
                    "metadata": {
                        k.decode(): v.decode()  # type: ignore[union-attr]
                        for k, v in (field.metadata or {}).items()  # type: ignore[union-attr]
                    },
                }
                for field in data.schema  # type: ignore[union-attr]
            ],
            "metadata": {k.decode(): v.decode() for k, v in clean_meta.items()},
        }

        result: dict[str, Any] = {
            "schema": schema_repr,
            "rows": data.to_pylist(),  # type: ignore[union-attr]
        }
        return json.dumps(result, indent=2, ensure_ascii=False) + "\n"


@pytest.fixture
def snowflake_snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Snapshot fixture pre-configured with SnowflakeArrowSnapshotSerializer."""
    return snapshot.use_extension(SnowflakeArrowSnapshotSerializer)


@pytest.fixture(scope="session")
def snowflake_pool():
    """Session-scoped Snowflake pool. Skips if SNOWFLAKE_ACCOUNT is absent."""
    dotenv_path = Path(__file__).parent.parent.parent / ".env.snowflake"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)

    if not os.environ.get("SNOWFLAKE_ACCOUNT"):
        pytest.skip("SNOWFLAKE_ACCOUNT not set — skipping Snowflake integration tests")

    config = SnowflakeConfig()  # type: ignore[call-arg]  # reads SNOWFLAKE_* env vars
    pool = create_pool(config)
    yield pool
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]

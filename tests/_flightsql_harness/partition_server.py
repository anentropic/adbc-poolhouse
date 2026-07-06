"""
A minimal in-process Arrow Flight SQL server that returns partitioned result sets.

Flight SQL is the only ADBC driver that implements partitioned execution
(`adbc_execute_partitions` / `adbc_read_partition`) --- partitions map to Flight
`FlightEndpoint`s. No free local backend (DuckDB, SQLite, ...) supports it, so to
give the async partition wrappers *live* coverage this module stands up a tiny
Flight server the `adbc_driver_flightsql` driver can execute against.

pyarrow ships no Flight SQL server base class (only plain `FlightServerBase`), so
this server hand-implements just enough of the Flight SQL protocol for one query
path. The `adbc_driver_flightsql` handshake it must satisfy, in order:

1. `GetFlightInfo(CommandGetSqlInfo)` on connect --- answered with a single endpoint
   yielding an EMPTY SqlInfo table (correct schema, no rows) so the driver falls
   back to defaults instead of panicking on a type mismatch.
2. `DoAction(CreatePreparedStatement)` --- the dbapi `adbc_execute_partitions`
   prepares before executing; answered with an `Any`-wrapped
   `ActionCreatePreparedStatementResult` carrying a handle and the result schema.
3. `GetFlightInfo(CommandPreparedStatementQuery)` --- answered with TWO endpoints,
   each a distinct partition ticket and no location (== "read from this same
   server").
4. `DoGet(ticket)` per partition --- streams that partition's rows.
5. `DoAction(ClosePreparedStatement / CloseSession)` on cleanup --- no-ops.

The Flight SQL protobufs are not importable in Python, so the two messages the
server must emit (`ActionCreatePreparedStatementResult` and its `Any` envelope) are
hand-encoded from the protobuf wire format --- see `_pb_bytes` / `_pb_any`.
"""

from __future__ import annotations

# pyarrow.flight is an untyped C-extension surface (FlightServerBase and friends are
# unexported / unknown-typed under basedpyright-strict). This whole module is Flight
# glue over that surface, so the reportUnknown*/private-import noise is relaxed here
# and nowhere else; the typed `serve_partitions` boundary keeps callers strict-clean.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownParameterType=false, reportPrivateImportUsage=false
# pyright: reportUntypedBaseClass=false, reportMissingParameterType=false
# pyright: reportUnknownArgumentType=false
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.flight as fl

if TYPE_CHECKING:
    from collections.abc import Generator

# The result set the server serves, split across two partitions. Rows are fixed so
# tests can assert exact values after reassembling the partitions.
RESULT_SCHEMA = pa.schema([("id", pa.int64()), ("name", pa.string())])
PARTITION_BATCHES: dict[bytes, pa.RecordBatch] = {
    b"partition-0": pa.record_batch([[1, 2], ["a", "b"]], schema=RESULT_SCHEMA),
    b"partition-1": pa.record_batch([[3, 4], ["c", "d"]], schema=RESULT_SCHEMA),
}

# The spec-defined Flight SQL GetSqlInfo response schema. The driver probes this on
# connect; an empty table with this exact schema makes it fall back to defaults.
_SQLINFO_VALUE = pa.dense_union(
    [
        pa.field("string_value", pa.string()),
        pa.field("bool_value", pa.bool_()),
        pa.field("bigint_value", pa.int64()),
        pa.field("int32_bitmask", pa.int32()),
        pa.field("string_list", pa.list_(pa.string())),
        pa.field("int32_to_int32_list_map", pa.map_(pa.int32(), pa.list_(pa.int32()))),
    ]
)
_SQLINFO_SCHEMA = pa.schema(
    [
        pa.field("info_name", pa.uint32(), nullable=False),
        pa.field("value", _SQLINFO_VALUE, nullable=False),
    ]
)
_SQLINFO_TICKET = b"__sqlinfo__"
_PREPARED_HANDLE = b"prepared-statement-handle"


def _varint(value: int) -> bytes:
    """Encode a non-negative int as a protobuf base-128 varint."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _pb_bytes(field_num: int, data: bytes) -> bytes:
    """Encode one length-delimited (wire type 2) protobuf field."""
    return bytes([(field_num << 3) | 2]) + _varint(len(data)) + data


def _pb_any(type_name: str, message: bytes) -> bytes:
    """Wrap a serialized message in a `google.protobuf.Any` (type_url=1, value=2)."""
    type_url = f"type.googleapis.com/{type_name}".encode()
    return _pb_bytes(1, type_url) + _pb_bytes(2, message)


def _schema_ipc(schema: pa.Schema) -> bytes:
    """Serialize an Arrow schema to its IPC encapsulated-message bytes."""
    return schema.serialize().to_pybytes()


# ActionCreatePreparedStatementResult { handle=1, dataset_schema=2, parameter_schema=3 },
# Any-wrapped as recent arrow-go Flight SQL expects the DoAction result body to be.
_CREATE_PREPARED_RESULT = _pb_any(
    "arrow.flight.protocol.sql.ActionCreatePreparedStatementResult",
    _pb_bytes(1, _PREPARED_HANDLE)
    + _pb_bytes(2, _schema_ipc(RESULT_SCHEMA))
    + _pb_bytes(3, _schema_ipc(pa.schema([]))),
)


class PartitionFlightServer(fl.FlightServerBase):
    """A Flight SQL server whose every query returns a fixed two-partition result."""

    def get_flight_info(self, context: object, descriptor: fl.FlightDescriptor) -> fl.FlightInfo:
        """Route the driver's capability probe vs. its query to the right endpoints."""
        del context
        if b"GetSqlInfo" in descriptor.command:
            endpoint = fl.FlightEndpoint(_SQLINFO_TICKET, [])
            return fl.FlightInfo(_SQLINFO_SCHEMA, descriptor, [endpoint], -1, -1)
        # Any real query (CommandStatementQuery or CommandPreparedStatementQuery):
        # hand back one endpoint per partition, no location (read from this server).
        endpoints = [fl.FlightEndpoint(ticket, []) for ticket in PARTITION_BATCHES]
        return fl.FlightInfo(RESULT_SCHEMA, descriptor, endpoints, -1, -1)

    def do_get(self, context: object, ticket: fl.Ticket) -> fl.RecordBatchStream:
        """Stream the SqlInfo probe (empty) or one partition's rows."""
        del context
        if ticket.ticket == _SQLINFO_TICKET:
            return fl.RecordBatchStream(_SQLINFO_SCHEMA.empty_table())
        batch = PARTITION_BATCHES[ticket.ticket]
        return fl.RecordBatchStream(pa.Table.from_batches([batch]))

    def do_action(self, context: object, action: fl.Action) -> object:
        """Answer CreatePreparedStatement with a handle; no-op every other action."""
        del context
        if action.type == "CreatePreparedStatement":
            return iter([_CREATE_PREPARED_RESULT])
        # ClosePreparedStatement / CloseSession / anything else: empty result.
        return iter(())


@contextmanager
def serve_partitions() -> Generator[str, None, None]:
    """
    Run a `PartitionFlightServer` in a background thread; yield its `grpc://` URI.

    Binds an ephemeral localhost port, serves on a daemon thread, and shuts the
    server down (joining the thread) on exit. The typed `str` return keeps callers
    clear of the untyped `pyarrow.flight` surface this module wraps.

    Yields:
        The `grpc://127.0.0.1:<port>` URI a Flight SQL client can connect to.
    """
    import threading

    server = PartitionFlightServer("grpc://127.0.0.1:0")
    uri = f"grpc://127.0.0.1:{server.port}"
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    try:
        yield uri
    finally:
        server.shutdown()
        thread.join(timeout=5)

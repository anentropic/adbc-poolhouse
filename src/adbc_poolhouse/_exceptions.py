"""Custom exceptions for adbc-poolhouse."""


class PoolhouseError(Exception):
    """
    Base exception for all adbc-poolhouse errors.

    All library-specific exceptions inherit from this class.
    Consumers can use ``except PoolhouseError`` to catch any library error.
    """


class ConfigurationError(PoolhouseError, ValueError):
    """
    Raised when a config model contains invalid field values.

    Inherits from both PoolhouseError (library hierarchy) and ValueError
    (pydantic model_validator compatibility). When raised inside a pydantic
    @model_validator, pydantic wraps it in ValidationError --- which itself
    inherits from ValueError --- satisfying 'raises ValueError' test expectations.

    Example:
        ```python
        DuckDBConfig(database=":memory:", pool_size=2)
        # raises pydantic.ValidationError (wraps ConfigurationError)
        ```
    """


class ConnectionBusyError(PoolhouseError):
    """
    Raised when one async connection is used concurrently from two tasks.

    An ADBC connection permits *serialized* access (one call at a time) but not
    *concurrent* access. Each `AsyncConnection` belongs to exactly one task for
    its lifetime; sharing it across tasks in a task group is a bug. Rather than
    silently serialize the calls --- which would still let two tasks' statements
    interleave inside one transaction (driver-safe, logically corrupt) and hide
    the bug --- the async layer rejects the second concurrent caller with this
    error. The fix is to check out a separate connection per task from the pool.

    Unlike `ConfigurationError`, this inherits `PoolhouseError` only (not
    `ValueError`): it signals a runtime misuse of the connection, not an invalid
    value.

    Example:
        ```python
        # FORBIDDEN --- aliasing one connection across tasks
        async with await pool.connect() as conn:
            cur = conn.cursor()
            async with anyio.create_task_group() as tg:
                tg.start_soon(run_query, cur)  # task A
                tg.start_soon(run_query, cur)  # task B --- raises ConnectionBusyError
        ```
    """

    _MESSAGE = (
        "This connection is already executing in another task; an ADBC "
        "connection allows serialized but not concurrent access. Check out a "
        "separate connection per task."
    )

    def __init__(self, message: str | None = None) -> None:
        """
        Initialize with the canonical message, or an override.

        Args:
            message: Custom error text. Defaults to the canonical
                connection-aliasing message.
        """
        super().__init__(message if message is not None else self._MESSAGE)

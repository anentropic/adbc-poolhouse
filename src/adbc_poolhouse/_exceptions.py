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
    @model_validator, pydantic wraps it in ValidationError — which itself
    inherits from ValueError — satisfying 'raises ValueError' test expectations.

    Example::

        DuckDBConfig(database=":memory:", pool_size=2)
        # raises pydantic.ValidationError (which wraps ConfigurationError,
        # and ValidationError itself inherits from ValueError)
    """

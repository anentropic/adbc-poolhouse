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


class RegistryError(PoolhouseError):
    """
    Base exception for all registry-related errors.

    All backend registration and lookup errors inherit from this class.
    Consumers can use ``except RegistryError`` to catch any registry error.
    """


class BackendAlreadyRegisteredError(RegistryError):
    """
    Raised when attempting to register a backend name that already exists.

    Args:
        name: The backend name that was already registered.

    Example::

        register_backend("my_backend", MyConfig, "driver_path")
        register_backend("my_backend", OtherConfig, "path")
        # raises BackendAlreadyRegisteredError("my_backend")
    """

    def __init__(self, name: str) -> None:
        super().__init__(f"Backend '{name}' is already registered")


class BackendNotRegisteredError(RegistryError):
    """
    Raised when looking up a backend that has not been registered.

    Args:
        config_name: The name of the config type that has no registered backend.

    Example::

        create_pool(UnregisteredConfig())
        # raises BackendNotRegisteredError("UnregisteredConfig")
    """

    def __init__(self, config_name: str) -> None:
        super().__init__(
            f"Backend for config type '{config_name}' is not registered. "
            f"Call register_backend() to register a custom backend."
        )

"""Quack warehouse configuration."""

from __future__ import annotations

import importlib.util
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig
from adbc_poolhouse._exceptions import ConfigurationError  # noqa: TC001


class QuackConfig(BaseWarehouseConfig):
    """
    Quack warehouse configuration.

    Targets the DuckDB Quack remote protocol via the
    [adbc-driver-quack](https://github.com/gizmodata/adbc-driver-quack) PyPI
    driver. The driver is on an alpha release track, so install with the
    `--pre` flag (the version constraint is in `pyproject.toml`):

        pip install --pre adbc-poolhouse[quack]

    Two connection modes are supported:

    - URI mode: set `uri` to a full `quack://host[:port]` string.
    - Decomposed mode: set `host` and optionally `port`. The URI is
      rebuilt as `quack://{host}:{port}` when `port` is set, or
      `quack://{host}` when `port` is `None`.

    Exactly one mode must be specified. Setting both `uri` and `host`,
    or neither, raises `ConfigurationError` (wrapped as a
    pydantic `ValidationError`).

    The driver's URI cannot embed credentials, so `uri` is a plain
    `str` (not `SecretStr`). The `token` field passes via the
    `adbc.quack.token` kwarg and is never embedded in the URI. The
    `tls` flag emits `adbc.quack.tls` only when `True` — when `False`
    (the default), the kwarg is omitted entirely so the driver's own
    default applies.

    Pool tuning fields are inherited and loaded from `QUACK_*` env vars.

    Example:
        ```python
        from adbc_poolhouse import QuackConfig, create_pool

        # URI mode
        config = QuackConfig(uri="quack://example.com:1234", token="secret", tls=True)

        # Decomposed mode
        config = QuackConfig(host="example.com", port=1234, token="secret")

        pool = create_pool(config)
        ```

    See [create_pool][adbc_poolhouse.create_pool] for pool creation.
    """

    model_config = SettingsConfigDict(env_prefix="QUACK_")

    uri: str | None = None
    """Full connection URI `quack://host[:port]`. The driver's URI cannot
    embed credentials, so this is a plain str (not SecretStr). Env: QUACK_URI."""

    host: str | None = None
    """Quack server hostname. Alternative to URI mode. Env: QUACK_HOST."""

    port: int | None = None
    """Quack server port. Optional even in decomposed mode. Env: QUACK_PORT."""

    token: SecretStr | None = None
    """Bearer token. Passes via `adbc.quack.token` kwarg, never embedded
    in the URI, never URL-encoded. Env: QUACK_TOKEN."""

    tls: bool = False
    """Enable TLS. When False (default), the `adbc.quack.tls` kwarg is
    omitted entirely (driver default is "false"). Env: QUACK_TLS."""

    @model_validator(mode="after")
    def check_connection_spec(self) -> Self:
        """Raise ConfigurationError when both modes are set or neither is set."""
        has_uri = self.uri is not None
        has_host = self.host is not None
        if has_uri and has_host:
            raise ConfigurationError("QuackConfig accepts either 'uri' or 'host', not both.")
        if not has_uri and not has_host:
            raise ConfigurationError("QuackConfig requires either 'uri' or 'host'. Got neither.")
        return self

    def _driver_path(self) -> str:
        return self._resolve_driver_path("adbc_driver_quack")

    def _dbapi_module(self) -> str | None:
        if importlib.util.find_spec("adbc_driver_quack") is not None:
            return "adbc_driver_quack.dbapi"
        return None

    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Convert config to ADBC driver connection kwargs.

        Returns:
            A dict with `uri` always set. `adbc.quack.token` is included
            when `token` is set; `adbc.quack.tls` is included only when
            `tls=True` (omitted on False — driver default is "false").
        """
        if self.uri is not None:
            uri = self.uri
        else:
            assert self.host is not None  # model_validator guarantees
            uri = (
                f"quack://{self.host}:{self.port}"
                if self.port is not None
                else f"quack://{self.host}"
            )

        result: dict[str, str] = {"uri": uri}
        if self.token is not None:
            result["adbc.quack.token"] = self.token.get_secret_value()  # pragma: allowlist secret
        if self.tls:
            result["adbc.quack.tls"] = "true"
        return result

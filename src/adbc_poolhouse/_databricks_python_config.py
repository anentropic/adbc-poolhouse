"""Databricks warehouse configuration using the Python connector (non-ADBC)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._backend import NativeConnectorBackend
from adbc_poolhouse._base_config import BaseWarehouseConfig
from adbc_poolhouse._exceptions import ConfigurationError  # noqa: TC001

if TYPE_CHECKING:
    from adbc_poolhouse._backend import ConnectionBackend


class DatabricksPythonConfig(BaseWarehouseConfig):
    """
    Databricks configuration backed by the Python connector (not ADBC).

    Uses `databricks-sql-connector` with ``use_kernel=True`, which connects over
    the Statement Execution ("kernel") path instead of Thrift. Prefer
    [`DatabricksConfig`][adbc_poolhouse.DatabricksConfig] (the ADBC driver) for
    normal SQL warehouses; reach for this config only when you need the
    non-Thrift path — notably **Lakehouse//RT**, which rejects Thrift and does not
    support ADBC.

    Requires the ``databricks-python`` extra:

    ```bash
    pip install "adbc-poolhouse[databricks-python]"
    ```

    Supports the same auth methods as `DatabricksConfig`:

    - **PAT**: set ``token``.
    - **OAuth U2M** (browser): set ``auth_type="OAuthU2M"``.
    - **OAuth M2M** (service principal): set ``auth_type="OAuthM2M"`` with
      ``client_id`` and ``client_secret``.
    - **Custom**: pass a ``credentials_provider`` callable (e.g. Azure SP).

    Downstream code sees the ADBC DBAPI cursor surface (``fetch_arrow_table`` etc.);
    ADBC-only methods (``adbc_ingest``, ``adbc_execute_partitions``,
    ``fetch_arrow``, ...) raise ``NotSupportedError``.

    Pool tuning fields are inherited and loaded from DATABRICKS_PYTHON_* env vars.

    Example:
        ```python
        from adbc_poolhouse import DatabricksPythonConfig, create_pool, close_pool

        config = DatabricksPythonConfig(
            host="adb-xxx.azuredatabricks.net",
            http_path="/sql/1.0/warehouses/abc123",
            token="dapi...",  # pragma: allowlist secret
        )
        pool = create_pool(config)
        with pool.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            table = cur.fetch_arrow_table()
        close_pool(pool)
        ```
    """

    model_config = SettingsConfigDict(env_prefix="DATABRICKS_PYTHON_", arbitrary_types_allowed=True)

    host: str | None = None
    """Databricks workspace hostname (e.g. 'adb-xxx.azuredatabricks.net').
    Env: DATABRICKS_PYTHON_HOST."""

    http_path: str | None = None
    """SQL warehouse HTTP path (e.g. '/sql/1.0/warehouses/abc123').
    Env: DATABRICKS_PYTHON_HTTP_PATH."""

    token: SecretStr | None = None
    """Personal access token for PAT auth. Env: DATABRICKS_PYTHON_TOKEN."""

    auth_type: str | None = None
    """OAuth auth type: 'OAuthU2M' (browser) or 'OAuthM2M' (service principal).
    Omit for PAT auth. Env: DATABRICKS_PYTHON_AUTH_TYPE."""

    client_id: str | None = None
    """OAuth M2M service principal client ID. Env: DATABRICKS_PYTHON_CLIENT_ID."""

    client_secret: SecretStr | None = None
    """OAuth M2M service principal client secret. Env: DATABRICKS_PYTHON_CLIENT_SECRET."""

    credentials_provider: Any = Field(default=None, exclude=True)
    """Optional callable returning a connector credentials provider (bring-your-own
    auth, e.g. Azure service principal). Passed to the connector verbatim. Not
    loaded from the environment."""

    catalog: str | None = None
    """Default Unity Catalog. Env: DATABRICKS_PYTHON_CATALOG."""

    schema_: str | None = Field(default=None, validation_alias="schema", alias="schema")
    """Default schema. Python attribute is schema_ to avoid Pydantic conflicts.
    Env: DATABRICKS_PYTHON_SCHEMA."""

    use_kernel: bool = True
    """Use the connector's Statement Execution ("kernel") path instead of Thrift.
    Required for Lakehouse//RT. Env: DATABRICKS_PYTHON_USE_KERNEL."""

    @model_validator(mode="after")
    def check_connection_spec(self) -> Self:
        """Raise ConfigurationError unless host, http_path, and one auth method are set."""
        if self.host is None or self.http_path is None:
            raise ConfigurationError("DatabricksPythonConfig requires 'host' and 'http_path'.")
        has_pat = self.token is not None
        has_u2m = self.auth_type == "OAuthU2M"
        has_m2m = (
            self.auth_type == "OAuthM2M"
            and self.client_id is not None
            and self.client_secret is not None
        )
        has_custom = self.credentials_provider is not None
        if not (has_pat or has_u2m or has_m2m or has_custom):
            raise ConfigurationError(
                "DatabricksPythonConfig requires one auth method: 'token' (PAT), "
                "auth_type='OAuthU2M', auth_type='OAuthM2M' with 'client_id' and "
                "'client_secret', or an explicit 'credentials_provider'."
            )
        return self

    def _driver_path(self) -> str | None:
        return None

    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Not applicable: this config uses the native connector, not ADBC.

        Raises:
            NotImplementedError: Always. The pool factory routes this config
                through `_make_backend` instead of the ADBC path.
        """
        raise NotImplementedError(
            "DatabricksPythonConfig uses the Databricks Python connector, not ADBC; "
            "it is pooled via _make_backend(), not to_adbc_kwargs()."
        )

    def to_connect_kwargs(self) -> dict[str, Any]:
        """
        Build ``databricks.sql.connect()`` kwargs from this config.

        Maps the auth fields onto the connector's surface: PAT to ``access_token``,
        ``OAuthU2M`` to ``auth_type="databricks-oauth"``, and ``OAuthM2M`` to a
        ``credentials_provider`` built from ``client_id`` / ``client_secret`` via
        ``databricks-sdk``. An explicit ``credentials_provider`` is passed through.

        Returns:
            Keyword arguments for ``databricks.sql.connect()``.
        """
        kwargs: dict[str, Any] = {
            "server_hostname": self.host,
            "http_path": self.http_path,
            "use_kernel": self.use_kernel,
        }
        if self.catalog is not None:
            kwargs["catalog"] = self.catalog
        if self.schema_ is not None:
            kwargs["schema"] = self.schema_

        if self.credentials_provider is not None:
            kwargs["credentials_provider"] = self.credentials_provider
        elif self.token is not None:
            kwargs["access_token"] = self.token.get_secret_value()
        elif self.auth_type == "OAuthU2M":
            kwargs["auth_type"] = "databricks-oauth"
        elif self.auth_type == "OAuthM2M":
            kwargs["credentials_provider"] = self._m2m_credentials_provider()
        return kwargs

    def _m2m_credentials_provider(self) -> Any:
        """
        Build an OAuth M2M credentials provider from client_id/client_secret.

        Returns a zero-arg callable that constructs the ``databricks-sdk`` config
        and provider lazily, when the connector invokes it at connect time.
        Deferring the SDK ``Config`` construction is deliberate: building it
        eagerly triggers auth/metadata resolution (network) before any pool is
        even used.
        """
        assert self.client_id is not None
        assert self.client_secret is not None
        host = self.host
        client_id = self.client_id
        client_secret = self.client_secret.get_secret_value()

        def _provider() -> Any:
            from databricks.sdk.core import Config  # noqa: PLC0415  (lazy: only M2M needs the SDK)
            from databricks.sdk.credentials_provider import (  # noqa: PLC0415
                oauth_service_principal,
            )

            sdk_config = Config(
                host=f"https://{host}",
                client_id=client_id,
                client_secret=client_secret,
            )
            return oauth_service_principal(sdk_config)

        return _provider

    def _make_backend(self) -> ConnectionBackend:
        """Return a `NativeConnectorBackend` carrying this config's connect kwargs."""
        return NativeConnectorBackend(self.to_connect_kwargs())

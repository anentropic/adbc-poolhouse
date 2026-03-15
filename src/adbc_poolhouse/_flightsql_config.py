"""FlightSQL warehouse configuration."""

from __future__ import annotations

import importlib.util

from pydantic import SecretStr  # noqa: TC002
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


class FlightSQLConfig(BaseWarehouseConfig):
    """
    FlightSQL warehouse configuration.

    Connects to any Apache Arrow Flight SQL server (e.g. Dremio, InfluxDB,
    DuckDB server mode, custom Flight SQL implementations).

    Pool tuning fields are inherited and loaded from FLIGHTSQL_* env vars.
    """

    model_config = SettingsConfigDict(env_prefix="FLIGHTSQL_")

    uri: str | None = None
    """gRPC endpoint URI. Env: FLIGHTSQL_URI.
    Format: grpc://host:port (plaintext) or grpc+tls://host:port (TLS)."""

    # --- Authentication ---
    username: str | None = None
    """Username for HTTP-style basic auth. Env: FLIGHTSQL_USERNAME."""

    password: SecretStr | None = None
    """Password for HTTP-style basic auth. Env: FLIGHTSQL_PASSWORD."""

    authorization_header: SecretStr | None = None
    """Custom authorization header value (overrides username/password if set).
    Env: FLIGHTSQL_AUTHORIZATION_HEADER."""

    # --- mTLS ---
    mtls_cert_chain: str | None = None
    """mTLS certificate chain (PEM). Env: FLIGHTSQL_MTLS_CERT_CHAIN."""

    mtls_private_key: SecretStr | None = None
    """mTLS private key (PEM). Env: FLIGHTSQL_MTLS_PRIVATE_KEY."""

    # --- TLS ---
    tls_root_certs: str | None = None
    """Root CA certificate(s) in PEM format. Env: FLIGHTSQL_TLS_ROOT_CERTS."""

    tls_skip_verify: bool = False
    """Disable TLS certificate verification. Env: FLIGHTSQL_TLS_SKIP_VERIFY."""

    tls_override_hostname: str | None = None
    """Override the TLS hostname for SNI. Env: FLIGHTSQL_TLS_OVERRIDE_HOSTNAME."""

    # --- Timeouts (float seconds) ---
    connect_timeout: float | None = None
    """Connection timeout in seconds. Env: FLIGHTSQL_CONNECT_TIMEOUT."""

    query_timeout: float | None = None
    """Query execution timeout in seconds. Env: FLIGHTSQL_QUERY_TIMEOUT."""

    fetch_timeout: float | None = None
    """Result fetch timeout in seconds. Env: FLIGHTSQL_FETCH_TIMEOUT."""

    update_timeout: float | None = None
    """DML update timeout in seconds. Env: FLIGHTSQL_UPDATE_TIMEOUT."""

    # --- gRPC options ---
    authority: str | None = None
    """Override gRPC authority header. Env: FLIGHTSQL_AUTHORITY."""

    max_msg_size: int | None = None
    """Maximum gRPC message size in bytes (driver default: 16 MiB).
    Env: FLIGHTSQL_MAX_MSG_SIZE."""

    with_cookie_middleware: bool = False
    """Enable gRPC cookie middleware (required by some servers for session
    management). Env: FLIGHTSQL_WITH_COOKIE_MIDDLEWARE."""

    def _driver_path(self) -> str:
        return self._resolve_driver_path("adbc_driver_flightsql")

    def _dbapi_module(self) -> str | None:
        if importlib.util.find_spec("adbc_driver_flightsql") is not None:
            return "adbc_driver_flightsql.dbapi"
        return None

    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Convert config to ADBC driver connection kwargs.

        Maps FlightSQL config fields to their ``adbc.flight.sql.*`` key
        equivalents. Boolean defaults (``tls_skip_verify``,
        ``with_cookie_middleware``) are always included as ``'true'``/
        ``'false'`` strings. Optional fields are omitted when ``None``.

        Returns:
            Dict of ADBC driver kwargs for ``adbc_driver_manager.dbapi.connect()``.
        """
        kwargs: dict[str, str] = {}

        # Connection endpoint
        if self.uri is not None:
            kwargs["uri"] = self.uri

        # Authentication
        if self.username is not None:
            kwargs["username"] = self.username
        if self.password is not None:
            kwargs["password"] = self.password.get_secret_value()  # pragma: allowlist secret
        if self.authorization_header is not None:
            kwargs["adbc.flight.sql.authorization_header"] = (
                self.authorization_header.get_secret_value()
            )

        # mTLS
        if self.mtls_cert_chain is not None:
            kwargs["adbc.flight.sql.client_option.mtls_cert_chain"] = self.mtls_cert_chain
        if self.mtls_private_key is not None:
            kwargs["adbc.flight.sql.client_option.mtls_private_key"] = (
                self.mtls_private_key.get_secret_value()
            )

        # TLS
        if self.tls_root_certs is not None:
            kwargs["adbc.flight.sql.client_option.tls_root_certs"] = self.tls_root_certs
        kwargs["adbc.flight.sql.client_option.tls_skip_verify"] = str(self.tls_skip_verify).lower()
        if self.tls_override_hostname is not None:
            kwargs["adbc.flight.sql.client_option.tls_override_hostname"] = (
                self.tls_override_hostname
            )

        # Timeouts
        if self.connect_timeout is not None:
            kwargs["adbc.flight.sql.rpc.timeout_seconds.connect"] = str(self.connect_timeout)
        if self.query_timeout is not None:
            kwargs["adbc.flight.sql.rpc.timeout_seconds.query"] = str(self.query_timeout)
        if self.fetch_timeout is not None:
            kwargs["adbc.flight.sql.rpc.timeout_seconds.fetch"] = str(self.fetch_timeout)
        if self.update_timeout is not None:
            kwargs["adbc.flight.sql.rpc.timeout_seconds.update"] = str(self.update_timeout)

        # gRPC options
        if self.authority is not None:
            kwargs["adbc.flight.sql.client_option.authority"] = self.authority
        if self.max_msg_size is not None:
            kwargs["adbc.flight.sql.client_option.with_max_msg_size"] = str(self.max_msg_size)
        kwargs["adbc.flight.sql.rpc.with_cookie_middleware"] = str(
            self.with_cookie_middleware
        ).lower()

        return kwargs

"""FlightSQL warehouse configuration."""

from __future__ import annotations

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

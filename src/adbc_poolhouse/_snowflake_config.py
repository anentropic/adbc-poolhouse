"""Snowflake warehouse configuration."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


class SnowflakeConfig(BaseWarehouseConfig):
    """
    Snowflake warehouse configuration.

    Supports all authentication methods provided by adbc-driver-snowflake:
    password, JWT (private_key_path / private_key_pem), external browser,
    OAuth, MFA, Okta, PAT, and workload identity federation (WIF).

    Pool tuning fields (pool_size, max_overflow, timeout, recycle) are
    inherited and loaded from SNOWFLAKE_* environment variables.
    """

    model_config = SettingsConfigDict(env_prefix="SNOWFLAKE_")

    # --- Identity ---
    account: str
    """Snowflake account identifier (e.g. 'myorg-myaccount'). Env: SNOWFLAKE_ACCOUNT."""
    user: str | None = None
    """Username. Required for most auth methods. Env: SNOWFLAKE_USER."""

    # --- Password auth ---
    password: SecretStr | None = None
    """Password for basic auth. Env: SNOWFLAKE_PASSWORD."""

    # --- Auth method selector ---
    auth_type: str | None = None
    """Auth method: auth_jwt, auth_ext_browser, auth_oauth, auth_mfa, auth_okta, auth_pat, auth_wif.
    Env: SNOWFLAKE_AUTH_TYPE."""

    # --- JWT / private key auth ---
    private_key_path: Path | None = None
    """File path to a PKCS1 or PKCS8 private key file. Mutually exclusive with private_key_pem.
    Env: SNOWFLAKE_PRIVATE_KEY_PATH."""
    private_key_pem: SecretStr | None = None
    """Inline PEM-encoded PKCS8 private key (encrypted or unencrypted). Mutually exclusive with
    private_key_path. Env: SNOWFLAKE_PRIVATE_KEY_PEM."""
    private_key_passphrase: SecretStr | None = None
    """Passphrase to decrypt an encrypted PKCS8 key. Env: SNOWFLAKE_PRIVATE_KEY_PASSPHRASE."""
    jwt_expire_timeout: str | None = None
    """JWT expiry duration (e.g. '300ms', '1m30s'). Env: SNOWFLAKE_JWT_EXPIRE_TIMEOUT."""

    # --- OAuth ---
    oauth_token: SecretStr | None = None
    """Bearer token for auth_oauth. Env: SNOWFLAKE_OAUTH_TOKEN."""

    # --- Okta ---
    okta_url: str | None = None
    """Okta server URL required for auth_okta. Env: SNOWFLAKE_OKTA_URL."""

    # --- WIF ---
    identity_provider: str | None = None
    """Identity provider for auth_wif. Env: SNOWFLAKE_IDENTITY_PROVIDER."""

    # --- Session / scope ---
    database: str | None = None
    """Default database. Env: SNOWFLAKE_DATABASE."""
    schema_: str | None = Field(default=None, validation_alias="schema", alias="schema")
    """Default schema. Python attribute is schema_ to avoid Pydantic conflicts;
    env var is SNOWFLAKE_SCHEMA. Env: SNOWFLAKE_SCHEMA."""
    warehouse: str | None = None
    """Snowflake virtual warehouse. Env: SNOWFLAKE_WAREHOUSE."""
    role: str | None = None
    """Snowflake role. Env: SNOWFLAKE_ROLE."""
    region: str | None = None
    """Snowflake region (if not embedded in account). Env: SNOWFLAKE_REGION."""

    # --- Connection ---
    host: str | None = None
    """Explicit hostname (alternative to account-derived URI). Env: SNOWFLAKE_HOST."""
    port: int | None = None
    """Connection port. Env: SNOWFLAKE_PORT."""
    protocol: str | None = None
    """Protocol: 'http' or 'https'. Env: SNOWFLAKE_PROTOCOL."""

    # --- Timeouts ---
    login_timeout: str | None = None
    """Login retry timeout duration string. Env: SNOWFLAKE_LOGIN_TIMEOUT."""
    request_timeout: str | None = None
    """Request retry timeout duration string. Env: SNOWFLAKE_REQUEST_TIMEOUT."""
    client_timeout: str | None = None
    """Network roundtrip timeout duration string. Env: SNOWFLAKE_CLIENT_TIMEOUT."""

    # --- Security ---
    tls_skip_verify: bool = False
    """Disable TLS certificate verification. Env: SNOWFLAKE_TLS_SKIP_VERIFY."""
    ocsp_fail_open_mode: bool = True
    """OCSP fail-open mode (True = allow connection on OCSP errors).
    Env: SNOWFLAKE_OCSP_FAIL_OPEN_MODE."""

    # --- Session behaviour ---
    keep_session_alive: bool = False
    """Prevent session expiry during long operations. Env: SNOWFLAKE_KEEP_SESSION_ALIVE."""

    # --- Telemetry / misc ---
    app_name: str | None = None
    """Application identifier sent to Snowflake. Env: SNOWFLAKE_APP_NAME."""
    disable_telemetry: bool = False
    """Disable Snowflake usage telemetry. Env: SNOWFLAKE_DISABLE_TELEMETRY."""
    cache_mfa_token: bool = False
    """Cache MFA token for subsequent connections. Env: SNOWFLAKE_CACHE_MFA_TOKEN."""
    store_temp_creds: bool = False
    """Cache ID token for SSO. Env: SNOWFLAKE_STORE_TEMP_CREDS."""

    @model_validator(mode="after")
    def check_private_key_exclusion(self) -> Self:
        """Raise ValidationError if both private_key_path and private_key_pem are set."""
        if self.private_key_path is not None and self.private_key_pem is not None:
            raise ValueError(
                "Provide only one of private_key_path (path to a PKCS1/PKCS8 "
                "private key file) or private_key_pem (inline PEM-encoded key "
                "content), not both. Use private_key_path for a key file, or "
                "private_key_pem for inline PEM content."
            )
        return self

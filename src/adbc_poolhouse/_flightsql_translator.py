"""FlightSQL ADBC driver kwargs translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._flightsql_config import FlightSQLConfig


def translate_flightsql(config: FlightSQLConfig) -> dict[str, str]:
    """
    Translate FlightSQLConfig to ADBC driver kwargs.

    All keys verified from installed adbc_driver_flightsql.DatabaseOptions enum,
    except connect_timeout which uses a raw string key.

    Note:
        connect_timeout uses raw string key 'adbc.flight.sql.rpc.timeout_seconds.connect'
        which is documented in ADBC FlightSQL docs but absent from the Python
        DatabaseOptions enum.

    Only non-None fields are included in the output dict. Boolean fields with
    default values (tls_skip_verify, with_cookie_middleware) are included only
    when not None — they are always set on the config object so will always appear,
    but the guard future-proofs against Optional typing changes.
    """
    kwargs: dict[str, str] = {}

    # Connection endpoint
    if config.uri is not None:
        kwargs["uri"] = config.uri

    # Authentication
    if config.username is not None:
        kwargs["username"] = config.username
    if config.password is not None:
        kwargs["password"] = config.password.get_secret_value()
    if config.authorization_header is not None:
        kwargs["adbc.flight.sql.authorization_header"] = (
            config.authorization_header.get_secret_value()
        )

    # mTLS
    if config.mtls_cert_chain is not None:
        kwargs["adbc.flight.sql.client_option.mtls_cert_chain"] = config.mtls_cert_chain
    if config.mtls_private_key is not None:
        kwargs["adbc.flight.sql.client_option.mtls_private_key"] = (
            config.mtls_private_key.get_secret_value()
        )

    # TLS
    if config.tls_root_certs is not None:
        kwargs["adbc.flight.sql.client_option.tls_root_certs"] = config.tls_root_certs
    # tls_skip_verify has a bool default (False) — always include as "true"/"false" string
    kwargs["adbc.flight.sql.client_option.tls_skip_verify"] = str(config.tls_skip_verify).lower()
    if config.tls_override_hostname is not None:
        kwargs["adbc.flight.sql.client_option.tls_override_hostname"] = config.tls_override_hostname

    # Timeouts — raw string keys (connect_timeout not in DatabaseOptions enum, see docstring)
    if config.connect_timeout is not None:
        kwargs["adbc.flight.sql.rpc.timeout_seconds.connect"] = str(config.connect_timeout)
    if config.query_timeout is not None:
        kwargs["adbc.flight.sql.rpc.timeout_seconds.query"] = str(config.query_timeout)
    if config.fetch_timeout is not None:
        kwargs["adbc.flight.sql.rpc.timeout_seconds.fetch"] = str(config.fetch_timeout)
    if config.update_timeout is not None:
        kwargs["adbc.flight.sql.rpc.timeout_seconds.update"] = str(config.update_timeout)

    # gRPC options
    if config.authority is not None:
        kwargs["adbc.flight.sql.client_option.authority"] = config.authority
    if config.max_msg_size is not None:
        kwargs["adbc.flight.sql.client_option.with_max_msg_size"] = str(config.max_msg_size)
    # with_cookie_middleware has a bool default (False) — always include as "true"/"false" string
    kwargs["adbc.flight.sql.rpc.with_cookie_middleware"] = str(
        config.with_cookie_middleware
    ).lower()

    return kwargs

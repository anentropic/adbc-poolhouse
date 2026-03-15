"""Integration tests for create_pool() factory (POOL-01..05, TEST-01, TEST-07)."""

import importlib
from pathlib import Path

import pytest
import sqlalchemy.pool

from adbc_poolhouse import (
    ConfigurationError,
    DuckDBConfig,
    PoolhouseError,
    SQLiteConfig,
    create_pool,
    managed_pool,
)


class TestCreatePoolDuckDB:
    """POOL-01, POOL-02, POOL-03, TEST-01."""

    def test_create_pool_returns_queuepool(self, tmp_path: Path) -> None:
        """POOL-01: create_pool returns a QueuePool instance."""
        cfg = DuckDBConfig(database=str(tmp_path / "test.db"))
        pool = create_pool(cfg)
        try:
            assert isinstance(pool, sqlalchemy.pool.QueuePool)
        finally:
            pool.dispose()
            pool._adbc_source.close()  # type: ignore[attr-defined]

    def test_default_pool_settings(self, tmp_path: Path) -> None:
        """POOL-02: default pool settings are pool_size=5, max_overflow=3, timeout=30."""
        cfg = DuckDBConfig(database=str(tmp_path / "test.db"))
        pool = create_pool(cfg)
        try:
            assert pool.size() == 5
            assert pool._max_overflow == 3
            assert pool._timeout == 30
        finally:
            pool.dispose()
            pool._adbc_source.close()  # type: ignore[attr-defined]

    def test_pool_size_override(self, tmp_path: Path) -> None:
        """POOL-03: create_pool kwargs override defaults."""
        cfg = DuckDBConfig(database=str(tmp_path / "test.db"))
        pool = create_pool(cfg, pool_size=10, recycle=7200)
        try:
            assert pool.size() == 10
        finally:
            pool.dispose()
            pool._adbc_source.close()  # type: ignore[attr-defined]

    def test_checkout_query_checkin_dispose(self, tmp_path: Path) -> None:
        """TEST-01: full lifecycle — checkout, query, checkin, dispose."""
        cfg = DuckDBConfig(database=str(tmp_path / "test.db"))
        pool = create_pool(cfg)
        try:
            conn = pool.connect()
            cur = conn.cursor()
            cur.execute("SELECT 42 AS answer")
            row = cur.fetchone()
            assert row == (42,)
            cur.close()
            conn.close()
            assert pool.checkedin() == 1
        finally:
            pool.dispose()
            pool._adbc_source.close()  # type: ignore[attr-defined]


class TestArrowAllocatorCleanup:
    """POOL-04, TEST-07: Arrow allocator cleanup via reset event."""

    def test_no_cursor_accumulation_after_checkin_cycles(self, tmp_path: Path) -> None:
        """TEST-07: N checkout/checkin cycles with unclosed cursors — no accumulation."""
        cfg = DuckDBConfig(database=str(tmp_path / "leak_test.db"))
        pool = create_pool(cfg)
        try:
            n = 10
            for i in range(n):
                conn = pool.connect()
                cur = conn.cursor()
                cur.execute(f"SELECT {i} AS val")
                # Intentionally do NOT close cursor before checkin.
                # reset event listener must close it on return.
                conn.close()

            # Pool must still function after N unclosed-cursor cycles.
            conn = pool.connect()
            cur = conn.cursor()
            cur.execute("SELECT 999")
            assert cur.fetchone() == (999,)
            cur.close()
            conn.close()
        finally:
            pool.dispose()
            pool._adbc_source.close()  # type: ignore[attr-defined]


class TestNoGlobalState:
    """POOL-05: importing adbc_poolhouse creates no pool or connection."""

    def test_import_creates_no_pool_or_connection(self) -> None:
        """POOL-05: import adbc_poolhouse produces no module-level pool/connection."""
        import adbc_poolhouse

        # Inspect module namespace — no QueuePool or Connection attributes
        for name in dir(adbc_poolhouse):
            val = getattr(adbc_poolhouse, name)
            assert not isinstance(val, sqlalchemy.pool.QueuePool), (
                f"Module-level QueuePool found: {name}"
            )

    def test_reimport_creates_no_pool(self) -> None:
        """POOL-05: re-importing module does not create pools."""
        importlib.reload(importlib.import_module("adbc_poolhouse"))
        import adbc_poolhouse

        for name in dir(adbc_poolhouse):
            val = getattr(adbc_poolhouse, name)
            assert not isinstance(val, sqlalchemy.pool.QueuePool)


class TestDatabricksPoolFactory:
    """Mock pool-factory wiring tests for Databricks decomposed-field mode."""

    def test_decomposed_fields_wiring(self) -> None:
        """Decomposed Databricks config passes URL-encoded URI to create_adbc_connection."""
        from unittest.mock import MagicMock, patch

        from pydantic import SecretStr

        from adbc_poolhouse import DatabricksConfig, create_pool

        config = DatabricksConfig(
            host="host",
            http_path="/sql/1.0/warehouses/abc",
            token=SecretStr("dapi+test=value/path"),  # pragma: allowlist secret
        )
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_poolhouse._pool_factory.create_adbc_connection",
            return_value=mock_conn,
        ) as mock_factory:
            pool = create_pool(config)
            pool.dispose()

        expected_uri = "databricks://token:dapi%2Btest%3Dvalue%2Fpath@host:443/sql/1.0/warehouses/abc"  # pragma: allowlist secret  # noqa: E501
        mock_factory.assert_called_once()
        call_args = mock_factory.call_args
        # create_adbc_connection(driver_path, kwargs, entrypoint=entrypoint)
        # kwargs is the second positional argument (index 1)
        actual_kwargs = call_args.args[1]
        assert actual_kwargs.get("uri") == expected_uri


class TestMySQLPoolFactory:
    """Mock pool-factory wiring tests for MySQLConfig decomposed-field mode."""

    def test_decomposed_fields_wiring(self) -> None:
        """Decomposed MySQLConfig passes correct Go DSN URI to create_adbc_connection."""
        from unittest.mock import MagicMock, patch

        from pydantic import SecretStr

        from adbc_poolhouse import MySQLConfig, create_pool

        config = MySQLConfig(
            host="localhost",
            user="root",
            password=SecretStr("my-secret-pw"),  # pragma: allowlist secret
            database="demo",
        )
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_poolhouse._pool_factory.create_adbc_connection",
            return_value=mock_conn,
        ) as mock_factory:
            pool = create_pool(config)
            pool.dispose()

        expected_uri = "root:my-secret-pw@tcp(localhost:3306)/demo"  # pragma: allowlist secret
        mock_factory.assert_called_once()
        call_args = mock_factory.call_args
        actual_kwargs = call_args.args[1]
        assert actual_kwargs.get("uri") == expected_uri


class TestClickHousePoolFactory:
    """Mock pool-factory wiring tests for ClickHouseConfig."""

    def test_decomposed_fields_wiring(self) -> None:
        """Decomposed ClickHouseConfig passes username/host/port directly to ADBC."""
        from unittest.mock import MagicMock, patch

        from pydantic import SecretStr

        from adbc_poolhouse import ClickHouseConfig, create_pool

        config = ClickHouseConfig(
            host="localhost",
            username="default",
            password=SecretStr("secret"),  # pragma: allowlist secret
            database="mydb",
        )
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_poolhouse._pool_factory.create_adbc_connection",
            return_value=mock_conn,
        ) as mock_factory:
            pool = create_pool(config)
            pool.dispose()

        mock_factory.assert_called_once()
        actual_kwargs = mock_factory.call_args.args[1]
        assert actual_kwargs.get("username") == "default"
        assert actual_kwargs.get("host") == "localhost"
        assert "uri" not in actual_kwargs, "ClickHouse decomposed mode must not emit uri kwarg"

    def test_uri_mode_wiring(self) -> None:
        """URI ClickHouseConfig passes uri kwarg to create_adbc_connection."""
        from unittest.mock import MagicMock, patch

        from pydantic import SecretStr

        from adbc_poolhouse import ClickHouseConfig, create_pool

        config = ClickHouseConfig(
            uri=SecretStr("http://user:pass@localhost:8123/db")
        )  # pragma: allowlist secret
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_poolhouse._pool_factory.create_adbc_connection",
            return_value=mock_conn,
        ) as mock_factory:
            pool = create_pool(config)
            pool.dispose()

        mock_factory.assert_called_once()
        actual_kwargs = mock_factory.call_args.args[1]
        _expected = "http://user:pass@localhost:8123/db"  # pragma: allowlist secret
        assert actual_kwargs.get("uri") == _expected


class TestExceptionHierarchy:
    """Exception hierarchy: PoolhouseError, ConfigurationError, DuckDBConfig bounds."""

    def test_poolhouse_error_importable(self) -> None:
        assert issubclass(PoolhouseError, Exception)

    def test_configuration_error_hierarchy(self) -> None:
        assert issubclass(ConfigurationError, PoolhouseError)
        assert issubclass(ConfigurationError, ValueError)

    def test_duckdb_memory_raises_configuration_error(self) -> None:
        """TEST-02: DuckDBConfig(:memory:, pool_size=2) raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DuckDBConfig(database=":memory:", pool_size=2)

    def test_pool_size_zero_raises_configuration_error(self) -> None:
        """pool_size=0 is rejected (must be > 0)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            DuckDBConfig(pool_size=0)
        assert "pool_size" in str(exc_info.value)
        assert "0" in str(exc_info.value)

    def test_pool_size_negative_raises_configuration_error(self) -> None:
        """pool_size=-1 is rejected (must be > 0)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            DuckDBConfig(pool_size=-1)
        assert "pool_size" in str(exc_info.value)
        assert "-1" in str(exc_info.value)

    def test_max_overflow_negative_raises_configuration_error(self) -> None:
        """max_overflow=-1 is rejected (must be >= 0)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            DuckDBConfig(max_overflow=-1)
        assert "max_overflow" in str(exc_info.value)
        assert "-1" in str(exc_info.value)

    def test_timeout_zero_raises_configuration_error(self) -> None:
        """timeout=0 is rejected (must be > 0)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            DuckDBConfig(timeout=0)
        assert "timeout" in str(exc_info.value)
        assert "0" in str(exc_info.value)

    def test_recycle_zero_raises_configuration_error(self) -> None:
        """recycle=0 is rejected (must be > 0)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            DuckDBConfig(recycle=0)
        assert "recycle" in str(exc_info.value)
        assert "0" in str(exc_info.value)

    def test_database_empty_string_raises_configuration_error(self) -> None:
        """database='' is rejected (must be a non-empty string)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DuckDBConfig(database="")


class TestRawDriverPath:
    """RAW-01: Tests for the driver_path overload."""

    def test_raw_driver_path_creates_pool(self) -> None:
        """create_pool(driver_path=...) calls create_adbc_connection with correct args."""
        from unittest.mock import MagicMock, patch

        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_poolhouse._pool_factory.create_adbc_connection",
            return_value=mock_conn,
        ) as mock_factory:
            pool = create_pool(driver_path="test_driver", db_kwargs={"path": "/tmp/db"})
            try:
                assert isinstance(pool, sqlalchemy.pool.QueuePool)
            finally:
                pool.dispose()

        mock_factory.assert_called_once_with(
            "test_driver",
            {"path": "/tmp/db"},
            entrypoint=None,
            dbapi_module=None,
        )

    def test_raw_driver_path_with_entrypoint(self) -> None:
        """create_pool(driver_path=..., entrypoint=...) passes entrypoint through."""
        from unittest.mock import MagicMock, patch

        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_poolhouse._pool_factory.create_adbc_connection",
            return_value=mock_conn,
        ) as mock_factory:
            pool = create_pool(
                driver_path="test_driver",
                db_kwargs={},
                entrypoint="my_init",
            )
            pool.dispose()

        mock_factory.assert_called_once_with(
            "test_driver",
            {},
            entrypoint="my_init",
            dbapi_module=None,
        )

    def test_raw_driver_path_pool_tuning(self) -> None:
        """Pool tuning kwargs are applied to the QueuePool."""
        from unittest.mock import MagicMock, patch

        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_poolhouse._pool_factory.create_adbc_connection",
            return_value=mock_conn,
        ):
            pool = create_pool(
                driver_path="d",
                db_kwargs={},
                pool_size=10,
                max_overflow=5,
                timeout=60,
                recycle=1800,
                pre_ping=True,
            )
            try:
                assert pool.size() == 10
                assert pool._max_overflow == 5
                assert pool._timeout == 60
            finally:
                pool.dispose()


class TestRawDbApiModule:
    """RAW-02: Tests for the dbapi_module overload."""

    def test_raw_dbapi_module_creates_pool(self) -> None:
        """create_pool(dbapi_module=...) calls create_adbc_connection with correct args."""
        from unittest.mock import MagicMock, patch

        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_poolhouse._pool_factory.create_adbc_connection",
            return_value=mock_conn,
        ) as mock_factory:
            pool = create_pool(
                dbapi_module="my.custom.dbapi",
                db_kwargs={"host": "localhost"},
            )
            try:
                assert isinstance(pool, sqlalchemy.pool.QueuePool)
            finally:
                pool.dispose()

        mock_factory.assert_called_once_with(
            "",
            {"host": "localhost"},
            entrypoint=None,
            dbapi_module="my.custom.dbapi",
        )


class TestManagedPoolRaw:
    """RAW-03: Tests for managed_pool raw variants."""

    def test_managed_raw_driver_path(self) -> None:
        """managed_pool(driver_path=...) yields pool and closes on exit."""
        from unittest.mock import MagicMock, patch

        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with (
            patch(
                "adbc_poolhouse._pool_factory.create_adbc_connection",
                return_value=mock_conn,
            ),
            managed_pool(driver_path="d", db_kwargs={}) as pool,
        ):
            assert isinstance(pool, sqlalchemy.pool.QueuePool)

    def test_managed_raw_dbapi_module(self) -> None:
        """managed_pool(dbapi_module=...) yields pool and closes on exit."""
        from unittest.mock import MagicMock, patch

        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with (
            patch(
                "adbc_poolhouse._pool_factory.create_adbc_connection",
                return_value=mock_conn,
            ),
            managed_pool(dbapi_module="m.dbapi", db_kwargs={}) as pool,
        ):
            assert isinstance(pool, sqlalchemy.pool.QueuePool)


class TestRawCreatePoolErrors:
    """RAW-04, RAW-05: Tests for error conditions."""

    def test_missing_args_raises_type_error(self) -> None:
        """create_pool() with no args raises TypeError."""
        with pytest.raises(TypeError, match="requires one of"):
            create_pool()  # type: ignore[call-overload]

    def test_pool_tuning_only_raises_type_error(self) -> None:
        """create_pool(pool_size=10) with only pool tuning raises TypeError."""
        with pytest.raises(TypeError, match="requires one of"):
            create_pool(pool_size=10)  # type: ignore[call-overload]

    def test_mutual_exclusive_raises_type_error(self) -> None:
        """create_pool(driver_path=..., dbapi_module=...) raises TypeError."""
        with pytest.raises(TypeError, match="driver_path or dbapi_module, not both"):
            create_pool(driver_path="x", dbapi_module="y", db_kwargs={})  # type: ignore[call-overload]

    def test_driver_path_without_db_kwargs_raises_type_error(self) -> None:
        """create_pool(driver_path=...) without db_kwargs raises TypeError."""
        with pytest.raises(TypeError, match="db_kwargs is required"):
            create_pool(driver_path="x")  # type: ignore[call-overload]

    def test_dbapi_module_without_db_kwargs_raises_type_error(self) -> None:
        """create_pool(dbapi_module=...) without db_kwargs raises TypeError."""
        with pytest.raises(TypeError, match="db_kwargs is required"):
            create_pool(dbapi_module="m")  # type: ignore[call-overload]


class TestSQLitePoolFactory:
    """Mock wiring and integration tests for SQLite via create_pool()."""

    def test_in_memory_wiring(self) -> None:
        """Mock: create_pool(SQLiteConfig()) passes correct kwargs to create_adbc_connection."""
        from unittest.mock import MagicMock, patch

        config = SQLiteConfig()  # database=":memory:", pool_size=1
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_poolhouse._pool_factory.create_adbc_connection",
            return_value=mock_conn,
        ) as mock_factory:
            pool = create_pool(config)
            pool.dispose()

        mock_factory.assert_called_once()
        call_args = mock_factory.call_args
        actual_kwargs = call_args.args[1]
        assert actual_kwargs == {"uri": ":memory:"}

    def test_sqlite_in_memory_query(self) -> None:
        """Integration: create_pool(SQLiteConfig()) executes SELECT 42 via real SQLite driver."""
        cfg = SQLiteConfig(database=":memory:", pool_size=1)
        pool = create_pool(cfg)
        try:
            conn = pool.connect()
            cur = conn.cursor()
            cur.execute("SELECT 42 AS answer")
            row = cur.fetchone()
            assert row == (42,)
            cur.close()
            conn.close()
        finally:
            pool.dispose()
            pool._adbc_source.close()  # type: ignore[attr-defined]


class TestRawDuckDBIntegration:
    """RAW-09: End-to-end test using raw driver_path with real DuckDB driver."""

    def test_raw_duckdb_driver_path_query(self, tmp_path: Path) -> None:
        """create_pool(driver_path=...) creates a working pool with real DuckDB."""
        import adbc_driver_duckdb  # type: ignore[reportMissingTypeStubs]

        pool = create_pool(
            driver_path=adbc_driver_duckdb.driver_path(),
            db_kwargs={"path": str(tmp_path / "raw_test.db")},
            entrypoint="duckdb_adbc_init",
            pool_size=1,
        )
        try:
            conn = pool.connect()
            cur = conn.cursor()
            cur.execute("SELECT 42 AS answer")
            row = cur.fetchone()
            assert row == (42,)
            cur.close()
            conn.close()
        finally:
            pool.dispose()
            pool._adbc_source.close()  # type: ignore[attr-defined]

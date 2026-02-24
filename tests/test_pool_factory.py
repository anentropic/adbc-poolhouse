"""Integration tests for create_pool() factory (POOL-01..05, TEST-01, TEST-07)."""

import importlib
from pathlib import Path

import pytest
import sqlalchemy.pool

from adbc_poolhouse import ConfigurationError, DuckDBConfig, PoolhouseError, create_pool


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

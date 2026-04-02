"""Unit tests for DuckDB schema migration runner."""

from stockfeed.cache.connection import close_connection, get_connection
from stockfeed.cache.schema import run_migrations


class TestRunMigrations:
    def test_creates_tables(self, tmp_db_path: str) -> None:
        conn = get_connection(tmp_db_path)
        run_migrations(conn)
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        assert "ohlcv" in tables
        assert "rate_limit_state" in tables
        assert "provider_health_log" in tables
        assert "schema_version" in tables
        close_connection(tmp_db_path)

    def test_idempotent(self, tmp_db_path: str) -> None:
        conn = get_connection(tmp_db_path)
        run_migrations(conn)
        run_migrations(conn)  # Should not raise
        rows = conn.execute("SELECT version FROM schema_version").fetchall()
        versions = [r[0] for r in rows]
        assert versions.count(1) == 1  # Version 1 applied exactly once
        close_connection(tmp_db_path)

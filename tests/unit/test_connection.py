"""Unit tests for DuckDB connection management."""

from __future__ import annotations

from stockfeed.cache.connection import close_all_connections, close_connection, get_connection


class TestConnection:
    def test_get_connection_returns_connection(self, tmp_db_path: str) -> None:
        conn = get_connection(tmp_db_path)
        assert conn is not None

    def test_get_connection_returns_same_instance(self, tmp_db_path: str) -> None:
        conn1 = get_connection(tmp_db_path)
        conn2 = get_connection(tmp_db_path)
        assert conn1 is conn2

    def test_close_connection_removes_it(self, tmp_db_path: str) -> None:
        get_connection(tmp_db_path)
        close_connection(tmp_db_path)
        # After close, a new connection is created fresh
        conn = get_connection(tmp_db_path)
        assert conn is not None

    def test_close_connection_noop_if_not_open(self, tmp_db_path: str) -> None:
        # Should not raise
        close_connection("/tmp/nonexistent_test_db_xyz.db")

    def test_close_all_connections(self, tmp_db_path: str) -> None:
        get_connection(tmp_db_path)
        close_all_connections()
        # Can still get a new connection after closing all
        conn = get_connection(tmp_db_path)
        assert conn is not None

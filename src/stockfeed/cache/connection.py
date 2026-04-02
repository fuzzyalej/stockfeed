"""DuckDB connection manager — single connection per process, thread-safe."""

import threading
from pathlib import Path

import duckdb

_lock = threading.Lock()
_connections: dict[str, duckdb.DuckDBPyConnection] = {}


def get_connection(db_path: str = "~/.stockfeed/cache.db") -> duckdb.DuckDBPyConnection:
    """Return the shared DuckDB connection for the given path.

    Creates a new connection if one does not already exist. Thread-safe.

    Parameters
    ----------
    db_path : str
        Path to the DuckDB database file. Supports ``~`` expansion.
    """
    resolved = str(Path(db_path).expanduser().resolve())
    with _lock:
        if resolved not in _connections:
            Path(resolved).parent.mkdir(parents=True, exist_ok=True)
            conn = duckdb.connect(resolved)
            _connections[resolved] = conn
        return _connections[resolved]


def close_connection(db_path: str = "~/.stockfeed/cache.db") -> None:
    """Close and remove the connection for the given path.

    Parameters
    ----------
    db_path : str
        Path to the DuckDB database file.
    """
    resolved = str(Path(db_path).expanduser().resolve())
    with _lock:
        conn = _connections.pop(resolved, None)
        if conn is not None:
            conn.close()


def close_all_connections() -> None:
    """Close all managed DuckDB connections."""
    with _lock:
        for conn in _connections.values():
            conn.close()
        _connections.clear()

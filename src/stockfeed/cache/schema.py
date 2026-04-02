"""DuckDB schema DDL and lightweight migration runner."""

import duckdb

CURRENT_SCHEMA_VERSION = 1

_CREATE_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version  INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT now()
);
"""

_MIGRATIONS: dict[int, str] = {
    1: """
CREATE TABLE IF NOT EXISTS ohlcv (
    ticker       VARCHAR NOT NULL,
    timestamp    TIMESTAMPTZ NOT NULL,
    interval     VARCHAR NOT NULL,
    open         DECIMAL(18,6),
    high         DECIMAL(18,6),
    low          DECIMAL(18,6),
    close_raw    DECIMAL(18,6),
    close_adj    DECIMAL(18,6),
    volume       BIGINT,
    vwap         DECIMAL(18,6),
    trade_count  INTEGER,
    provider     VARCHAR NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ticker, timestamp, interval)
);

CREATE TABLE IF NOT EXISTS rate_limit_state (
    provider         VARCHAR PRIMARY KEY,
    requests_made    INTEGER DEFAULT 0,
    window_start     TIMESTAMPTZ,
    window_seconds   INTEGER,
    limit_per_window INTEGER,
    updated_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provider_health_log (
    id           INTEGER PRIMARY KEY,
    provider     VARCHAR NOT NULL,
    healthy      BOOLEAN,
    latency_ms   FLOAT,
    error        VARCHAR,
    checked_at   TIMESTAMPTZ DEFAULT now()
);
""",
}


def run_migrations(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply any pending schema migrations to the database.

    Parameters
    ----------
    conn : duckdb.DuckDBPyConnection
        Active DuckDB connection to apply migrations on.
    """
    conn.execute(_CREATE_SCHEMA_VERSION)

    applied: set[int] = set()
    rows = conn.execute("SELECT version FROM schema_version").fetchall()
    for row in rows:
        applied.add(row[0])

    for version in sorted(_MIGRATIONS):
        if version not in applied:
            conn.execute(_MIGRATIONS[version])
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", [version])

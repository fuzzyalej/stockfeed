# Changelog

All notable changes to `stockfeed` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2026-04-03

### Added

**Core infrastructure (Phase 1)**
- `StockFeedSettings` via `pydantic-settings` with `STOCKFEED_` env prefix
- Full exception hierarchy: `StockFeedError`, `ProviderError`, `CacheError`, and all subtypes
- Pydantic v2 canonical models: `OHLCVBar`, `Quote`, `TickerInfo`, `HealthStatus`, `Interval`, `StockFeedResponse[T]`
- `structlog` setup with correlation IDs and bound `provider`/`ticker`/`interval` fields
- DuckDB schema (`ohlcv_bars`, `rate_limit_state`, `provider_health_log`) with migration runner
- Thread-safe DuckDB connection pool
- GitHub Actions CI workflow (`ci.yml`) with lint, typecheck, and coverage gate

**Provider abstraction layer (Phase 2)**
- `AbstractProvider` ABC with sync and async method surfaces
- `BaseNormalizer` ABC for raw-response → canonical-model mapping
- `ProviderRegistry` with entry-point discovery (`stockfeed.providers` group)
- `RateLimiter` persisted to DuckDB; tracks `X-RateLimit-*` and `Retry-After` headers
- `HealthChecker` with latency probes and history log
- `ProviderSelector` with ordered failover: preferred → auth'd → yfinance
- `YFinanceProvider` (fully implemented) — both `close_raw` and `close_adj` via dual `history()` calls
- Provider stubs for Tiingo, Finnhub, Twelve Data, Alpaca, Tradier, CoinGecko

**Cache layer (Phase 3)**
- `CacheManager`: `read`, `write`, `read_partial`, `invalidate`, `stats`
- Partial cache hit detection — fetches only missing date ranges
- `MarketHoursChecker` via `exchange_calendars` — bypasses cache during open market hours for intraday intervals
- Cache CLI (`python -m stockfeed.cache`) with `stats`, `clear`, `export`, `inspect` subcommands
- Full implementations for Tiingo, Finnhub, Twelve Data, Alpaca, Tradier (OHLCV, quote, ticker_info, health)
- CoinGecko scaffold (all methods raise `NotImplementedError`)

**Client API (Phase 4)**
- `StockFeedClient` (sync) — automatic provider selection, cache-first access, failover with exponential backoff
- `AsyncStockFeedClient` (async) — identical method surface using `asyncio.to_thread`
- `ProviderInfo` frozen dataclass and `list_providers()` method
- Ergonomic inputs: `"YYYY-MM-DD"` string dates and `"1d"` string intervals accepted everywhere
- `parse_dt` and `parse_interval` utility helpers (`_utils.py`)

**Streaming & dev tools (Phase 5)**
- `AsyncStockFeedClient.stream_quote()` — async generator that polls `get_quote()` at a configurable interval; handles transient errors with configurable `max_errors`
- `AsyncStockFeedClient.simulate()` — replays historical bars as an async stream with configurable `speed`; raises `DevModeError` outside dev mode
- `AsyncStockFeedClient(dev_mode=True)` convenience constructor kwarg

**Test suite (Phase 6)**
- 500 tests across unit, integration, and E2E layers
- Provider contract tests parametrized over all 7 providers
- Integration tests: failover chain, auth short-circuit, market hours bypass, cache write-back
- E2E tests: `StockFeedClient`, `AsyncStockFeedClient`, `stream_quote`, `simulate`
- Shared `conftest.py` fixtures and model factories
- 91% test coverage (≥90% gate enforced in CI)

**Documentation (Phase 7)**
- MkDocs Material site with provider pages, API reference, streaming guide, dev tools guide
- `CONTRIBUTING.md` with provider addition checklist and code template
- `README.md` with badges, provider support matrix, and updated examples
- GitHub Actions `release.yml` for automated PyPI publish on version tags

### Fixed

- `RateLimiter`: guard against adding `tzinfo` to an already-aware `datetime` from DuckDB `TIMESTAMPTZ`
- `provider_health_log.id`: changed from bare `INTEGER PRIMARY KEY` to `BIGINT DEFAULT nextval(...)` for correct DuckDB auto-increment
- `CoingeckoProvider`: added `__init__(api_key: str = "")` so `ProviderSelector._instantiate()` can pass credentials

---

[0.1.0]: https://github.com/fuzzyalej/stockfeed/releases/tag/v0.1.0

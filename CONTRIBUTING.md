# Contributing to stockfeed

Thank you for your interest in contributing! This guide covers everything you need to add a new provider, fix a bug, or improve the docs.

## Development setup

```bash
git clone https://github.com/your-org/stockfeed
cd stockfeed
uv sync          # installs all dev dependencies
```

Run the full check suite:

```bash
uv run ruff check src/ tests/   # lint
uv run ruff format src/ tests/  # format
uv run mypy src/                # type check
uv run pytest --cov=stockfeed --cov-fail-under=90  # tests + coverage
```

## Adding a new provider

Follow this checklist in order. Every step is required before a provider can be merged.

### 1. Create the provider package

```
src/stockfeed/providers/<name>/
├── __init__.py       # re-exports ProviderClass and NormalizerClass
├── provider.py       # inherits AbstractProvider
└── normalizer.py     # inherits BaseNormalizer
```

### 2. Implement AbstractProvider

```python
from stockfeed.providers.base import AbstractProvider

class MyProvider(AbstractProvider):
    name = "myprovider"
    supported_intervals = [Interval.ONE_DAY, Interval.ONE_HOUR, ...]
    requires_auth = True

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def get_ohlcv(self, ticker, interval, start, end) -> list[OHLCVBar]: ...
    def get_quote(self, ticker) -> Quote: ...
    def get_ticker_info(self, ticker) -> TickerInfo: ...
    def health_check(self) -> HealthStatus: ...

    # Async variants — wrap sync with asyncio.to_thread
    async def async_get_ohlcv(self, ticker, interval, start, end):
        return await asyncio.to_thread(self.get_ohlcv, ticker, interval, start, end)
    # ... etc.
```

### 3. Implement BaseNormalizer

```python
from stockfeed.normalizer.base import BaseNormalizer

class MyNormalizer(BaseNormalizer):
    def normalize_ohlcv(self, raw) -> list[OHLCVBar]: ...
    def normalize_quote(self, raw) -> Quote: ...
    def normalize_ticker_info(self, raw) -> TickerInfo: ...
```

If the raw data is malformed, raise `stockfeed.exceptions.ValidationError` with a useful message.

### 4. Add configuration

In `src/stockfeed/config.py`, add the API key field:

```python
class StockFeedSettings(BaseSettings):
    myprovider_api_key: str | None = None
```

### 5. Register the provider

In `src/stockfeed/providers/selector.py`, add:

```python
# In _has_auth():
"myprovider": getattr(s, "myprovider_api_key", None),

# In _instantiate():
if name == "myprovider":
    return cls(api_key=getattr(s, "myprovider_api_key", "") or "")
```

In `src/stockfeed/providers/__init__.py`, import and register:

```python
from stockfeed.providers.myprovider.provider import MyProvider
_default_registry.register(MyProvider)
```

### 6. Add configuration docs

Update `docs/configuration.md` and create `docs/providers/myprovider.md`.

### 7. Add fixtures

Create JSON fixture files in `tests/fixtures/providers/myprovider/`:

- `ohlcv.json` — sample OHLCV API response
- `quote.json` — sample quote API response
- `ticker_info.json` — sample ticker info response

### 8. Add unit tests

Create `tests/unit/providers/test_myprovider.py` covering:

- Normalizer: correct field mapping from fixture JSON
- Provider: HTTP responses mocked with `respx`; auth errors, 404, rate limits
- Health check

### 9. Verify contract tests pass

```bash
uv run pytest tests/unit/providers/test_contract.py -v -k myprovider
```

All classes in `_ALL_PROVIDER_CLASSES` are tested automatically. Add your class to that list in `test_contract.py`.

---

## Third-party providers (entry points)

You can distribute a provider as a separate package without modifying `stockfeed`:

```toml
# in your pyproject.toml
[project.entry-points."stockfeed.providers"]
myprovider = "mypkg.provider:MyProvider"
```

`ProviderRegistry.discover_entry_points()` loads all registered providers automatically on startup.

---

## Pull request guidelines

- One feature or fix per PR
- All CI checks must pass (lint, mypy, pytest ≥90% coverage)
- Add or update tests for every changed behaviour
- Update `docs/` and `CHANGELOG.md` for user-visible changes
- Squash commits to a logical history before merge

## Reporting bugs

Open an issue at [github.com/your-org/stockfeed/issues](https://github.com/your-org/stockfeed/issues) with:

- `stockfeed` version (`pip show stockfeed`)
- Python version
- Minimal reproduction script
- Full traceback

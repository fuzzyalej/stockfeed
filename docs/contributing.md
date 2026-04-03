# Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full guide.

## Quick links

- [Add a new provider](#adding-a-new-provider)
- [Run tests](#running-tests)
- [Code standards](#code-standards)

## Adding a new provider

Providers can be added to the `stockfeed` core or distributed as third-party packages via entry points.

### Core provider checklist

1. Create `src/stockfeed/providers/<name>/` with `__init__.py`, `provider.py`, `normalizer.py`
2. Inherit `AbstractProvider` in `provider.py`
3. Inherit `BaseNormalizer` in `normalizer.py`
4. Add a config key to `StockFeedSettings` in `config.py`
5. Add `_instantiate` logic in `ProviderSelector._instantiate()`
6. Add `_has_auth` mapping in `ProviderSelector._has_auth()`
7. Register in `src/stockfeed/providers/__init__.py`
8. Add JSON fixtures to `tests/fixtures/providers/<name>/`
9. Add unit tests to `tests/unit/providers/test_<name>.py`
10. Verify provider contract tests pass: `pytest tests/unit/providers/test_contract.py`

### Third-party provider (entry points)

```toml
# in your provider package's pyproject.toml
[project.entry-points."stockfeed.providers"]
myprovider = "myprovider.provider:MyProvider"
```

`ProviderRegistry.discover_entry_points()` loads all registered entry points on startup.

## Running tests

```bash
uv run pytest --cov=stockfeed --cov-fail-under=90
```

Run only provider contract tests:

```bash
uv run pytest tests/unit/providers/test_contract.py -v
```

## Code standards

- **Linting:** `uv run ruff check src/ tests/`
- **Formatting:** `uv run ruff format src/ tests/`
- **Type checking:** `uv run mypy src/`
- **Docstrings:** NumPy style on all public methods
- **Coverage gate:** 90% enforced in CI

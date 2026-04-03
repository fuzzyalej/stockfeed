# Exceptions API Reference

All exceptions inherit from `StockFeedError` and support optional `provider`, `ticker`, and `suggestion` fields for actionable error messages.

## Exception hierarchy

```
StockFeedError
├── ProviderError
│   ├── ProviderAuthError          # Invalid/missing API key
│   ├── ProviderRateLimitError     # Rate limit hit (.retry_after: float | None)
│   ├── ProviderUnavailableError   # Provider down or timeout
│   └── TickerNotFoundError        # Ticker doesn't exist on provider
├── CacheError
│   ├── CacheReadError
│   └── CacheWriteError
├── ValidationError                # Bad user input
├── UnsupportedIntervalError       # Provider doesn't support the interval
├── ConfigurationError             # Missing/invalid config
└── DevModeError                   # Dev-only feature used outside dev mode
```

## Reference

::: stockfeed.exceptions
    options:
      show_root_heading: false
      members:
        - StockFeedError
        - ProviderError
        - ProviderAuthError
        - ProviderRateLimitError
        - ProviderUnavailableError
        - TickerNotFoundError
        - CacheError
        - CacheReadError
        - CacheWriteError
        - ValidationError
        - UnsupportedIntervalError
        - ConfigurationError
        - DevModeError

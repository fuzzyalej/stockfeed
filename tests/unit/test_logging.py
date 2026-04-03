"""Unit tests for stockfeed.logging — configure_logging, get_logger, bind/clear context."""

from __future__ import annotations

from stockfeed.logging import bind_context, clear_context, configure_logging, get_logger


class TestLogging:
    def test_configure_logging_console(self) -> None:
        # Should not raise
        configure_logging(log_level="WARNING", log_format="console")

    def test_configure_logging_json(self) -> None:
        configure_logging(log_level="DEBUG", log_format="json")

    def test_configure_logging_invalid_level_falls_back(self) -> None:
        # getattr on logging with invalid level returns INFO
        configure_logging(log_level="NOTAREALEVEL", log_format="console")

    def test_get_logger_returns_logger(self) -> None:
        logger = get_logger("stockfeed.test")
        assert logger is not None

    def test_bind_and_clear_context(self) -> None:
        bind_context(ticker="AAPL", provider="yfinance")
        clear_context()  # Should not raise

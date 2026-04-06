from decimal import Decimal

from stockfeed.config import StockFeedSettings


def test_options_risk_free_rate_default():
    s = StockFeedSettings()
    assert s.options_risk_free_rate == Decimal("0.05")


def test_options_risk_free_rate_from_env(monkeypatch):
    monkeypatch.setenv("STOCKFEED_OPTIONS_RISK_FREE_RATE", "0.045")
    s = StockFeedSettings()
    assert s.options_risk_free_rate == Decimal("0.045")

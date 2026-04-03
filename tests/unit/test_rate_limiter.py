"""Unit tests for RateLimiter."""

from __future__ import annotations

from stockfeed.providers.rate_limiter import RateLimiter


class TestRateLimiterAvailability:
    def test_unknown_provider_is_available(self, tmp_db_path: str) -> None:
        rl = RateLimiter(db_path=tmp_db_path)
        assert rl.is_available("unknown_provider") is True

    def test_provider_within_limit_is_available(self, tmp_db_path: str) -> None:
        rl = RateLimiter(db_path=tmp_db_path)
        rl.update_from_headers(
            "tiingo",
            {
                "X-RateLimit-Remaining": "5",
                "X-RateLimit-Limit": "10",
                "X-RateLimit-Reset": "60",
            },
        )
        assert rl.is_available("tiingo") is True

    def test_provider_at_zero_remaining_not_available(self, tmp_db_path: str) -> None:
        rl = RateLimiter(db_path=tmp_db_path)
        rl.update_from_headers(
            "tiingo",
            {
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Limit": "10",
                "X-RateLimit-Reset": "9999",
            },
        )
        assert rl.is_available("tiingo") is False

    def test_no_limit_set_is_always_available(self, tmp_db_path: str) -> None:
        rl = RateLimiter(db_path=tmp_db_path)
        rl.record_request("tiingo")
        # No limit_per_window set → should still be available
        assert rl.is_available("tiingo") is True


class TestRateLimiterRecordRequest:
    def test_record_request_increments_counter(self, tmp_db_path: str) -> None:
        rl = RateLimiter(db_path=tmp_db_path)
        rl.update_from_headers(
            "tiingo",
            {
                "X-RateLimit-Remaining": "9",
                "X-RateLimit-Limit": "10",
                "X-RateLimit-Reset": "60",
            },
        )
        rl.record_request("tiingo")
        rl.record_request("tiingo")
        # Two more requests recorded; doesn't raise
        assert rl.is_available("tiingo") is True  # 10-9 + 2 = 3 < 10

    def test_record_request_for_new_provider(self, tmp_db_path: str) -> None:
        rl = RateLimiter(db_path=tmp_db_path)
        # Should not raise even for a provider with no prior state
        rl.record_request("new_provider")
        assert rl.is_available("new_provider") is True


class TestRateLimiterUpdateFromHeaders:
    def test_updates_from_standard_headers(self, tmp_db_path: str) -> None:
        rl = RateLimiter(db_path=tmp_db_path)
        rl.update_from_headers(
            "finnhub",
            {
                "X-RateLimit-Remaining": "3",
                "X-RateLimit-Limit": "5",
                "X-RateLimit-Reset": "30",
            },
        )
        # 5 - 3 = 2 requests made, limit 5 → still available
        assert rl.is_available("finnhub") is True

    def test_updates_from_retry_after(self, tmp_db_path: str) -> None:
        rl = RateLimiter(db_path=tmp_db_path)
        rl.update_from_headers("finnhub", {"Retry-After": "60"})
        # No limit_per_window set, so still available
        assert rl.is_available("finnhub") is True

    def test_empty_headers_no_error(self, tmp_db_path: str) -> None:
        rl = RateLimiter(db_path=tmp_db_path)
        rl.update_from_headers("tiingo", {})
        assert rl.is_available("tiingo") is True

    def test_case_insensitive_headers(self, tmp_db_path: str) -> None:
        rl = RateLimiter(db_path=tmp_db_path)
        rl.update_from_headers(
            "tiingo",
            {
                "x-ratelimit-remaining": "2",
                "x-ratelimit-limit": "10",
            },
        )
        assert rl.is_available("tiingo") is True


class TestRateLimiterResetWindow:
    def test_reset_window_clears_counter(self, tmp_db_path: str) -> None:
        rl = RateLimiter(db_path=tmp_db_path)
        rl.update_from_headers(
            "tiingo",
            {
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Limit": "10",
                "X-RateLimit-Reset": "9999",
            },
        )
        assert rl.is_available("tiingo") is False

        rl.reset_window("tiingo")
        # After reset, requests_made=0, no limit still tracked but window reset
        # The window_seconds/limit_per_window aren't cleared by reset, so still bounded
        # But requests_made=0 < limit=10
        assert rl.is_available("tiingo") is True

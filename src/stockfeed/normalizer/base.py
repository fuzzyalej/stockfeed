"""Base normalizer — transforms raw provider responses into canonical models."""

from abc import ABC, abstractmethod
from typing import Any

from stockfeed.exceptions import ValidationError
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo


class BaseNormalizer(ABC):
    """Convert raw provider JSON/objects into canonical stockfeed models.

    Each provider ships its own concrete subclass that knows how to map
    that provider's field names and formats onto the canonical schema.

    Raises
    ------
    ValidationError
        Raised (with a descriptive message) whenever the raw data is
        missing required fields or contains values that cannot be coerced
        into the canonical types.
    """

    @abstractmethod
    def normalize_ohlcv(self, raw: Any) -> list[OHLCVBar]:
        """Map raw provider OHLCV data to a list of :class:`OHLCVBar`.

        Parameters
        ----------
        raw : Any
            Provider-specific response object (dict, DataFrame, list, …).

        Returns
        -------
        list[OHLCVBar]
            Bars in ascending timestamp order.

        Raises
        ------
        ValidationError
            If *raw* is malformed or missing required fields.
        """

    @abstractmethod
    def normalize_quote(self, raw: Any) -> Quote:
        """Map raw provider quote data to a :class:`Quote`.

        Parameters
        ----------
        raw : Any
            Provider-specific response object.

        Returns
        -------
        Quote

        Raises
        ------
        ValidationError
            If *raw* is malformed or missing required fields.
        """

    @abstractmethod
    def normalize_ticker_info(self, raw: Any) -> TickerInfo:
        """Map raw provider ticker metadata to a :class:`TickerInfo`.

        Parameters
        ----------
        raw : Any
            Provider-specific response object.

        Returns
        -------
        TickerInfo

        Raises
        ------
        ValidationError
            If *raw* is malformed or missing required fields.
        """

    # ------------------------------------------------------------------
    # Helpers available to all subclasses
    # ------------------------------------------------------------------

    def _require(self, data: dict[str, Any], *keys: str, context: str = "") -> None:
        """Raise :class:`ValidationError` if any key is absent from *data*.

        Parameters
        ----------
        data : dict
            The raw mapping to inspect.
        *keys : str
            Field names that must be present.
        context : str
            Human-readable label for the data source (used in the error message).
        """
        missing = [k for k in keys if k not in data]
        if missing:
            label = f" in {context}" if context else ""
            raise ValidationError(
                f"Missing required fields{label}: {missing}",
                suggestion="Check provider API response shape or update the normalizer.",
            )

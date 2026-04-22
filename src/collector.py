"""API collectors for Hyperliquid and Binance perpetual volume data."""

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

HYPERLIQUID_URL = "https://api.hyperliquid.xyz/info"
BINANCE_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_DELAYS = [1, 2, 4]


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """Make an HTTP request with exponential backoff retries."""
    last_exception: Optional[Exception] = None
    for attempt, delay in enumerate(BACKOFF_DELAYS):
        try:
            response = requests.request(method, url, timeout=TIMEOUT, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_exception = exc
            logger.warning("Request to %s failed (attempt %d/%d): %s", url, attempt + 1, MAX_RETRIES, exc)
            if attempt < len(BACKOFF_DELAYS) - 1:
                time.sleep(delay)
    raise last_exception  # type: ignore[misc]


def fetch_hyperliquid_volume() -> Optional[float]:
    """Fetch total 24h notional volume from Hyperliquid."""
    try:
        resp = _request_with_retry("POST", HYPERLIQUID_URL, json={"type": "metaAndAssetCtxs"})
        data = resp.json()
        # Response format: [meta, [assetCtxs, ...]]
        if not isinstance(data, list) or len(data) < 2:
            logger.error("Unexpected Hyperliquid response structure")
            return None
        asset_ctxs = data[1]
        total = 0.0
        for ctx in asset_ctxs:
            if isinstance(ctx, dict):
                total += float(ctx.get("dayNtlVlm", 0) or 0)
        return round(total, 2)
    except Exception as exc:
        logger.error("Failed to fetch Hyperliquid volume: %s", exc)
        return None


def fetch_binance_volume() -> Optional[float]:
    """Fetch total 24h quote volume from Binance futures."""
    try:
        resp = _request_with_retry("GET", BINANCE_URL)
        tickers = resp.json()
        if not isinstance(tickers, list):
            logger.error("Unexpected Binance response structure")
            return None
        total = 0.0
        for ticker in tickers:
            if isinstance(ticker, dict):
                total += float(ticker.get("quoteVolume", 0) or 0)
        return round(total, 2)
    except Exception as exc:
        logger.error("Failed to fetch Binance volume: %s", exc)
        return None

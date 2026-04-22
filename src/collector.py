"""API collectors for Hyperliquid and Binance perpetual volume data."""

import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

HYPERLIQUID_URL = "https://api.hyperliquid.xyz/info"
BINANCE_URLS = [
    "https://fapi.binance.com/fapi/v1/ticker/24hr",
    "https://fapi1.binance.com/fapi/v1/ticker/24hr",
    "https://fapi2.binance.com/fapi/v1/ticker/24hr",
    "https://fapi3.binance.com/fapi/v1/ticker/24hr",
]
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_DELAYS = [1, 2, 4]

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _get_proxies() -> Optional[dict]:
    """Read HTTP_PROXY / HTTPS_PROXY from environment."""
    proxies = {}
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    return proxies if proxies else None


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """Make an HTTP request with exponential backoff retries."""
    proxies = _get_proxies()
    if proxies:
        kwargs.setdefault("proxies", proxies)
    kwargs.setdefault("headers", DEFAULT_HEADERS)

    last_exception: Optional[Exception] = None
    for attempt, delay in enumerate(BACKOFF_DELAYS):
        try:
            response = requests.request(method, url, timeout=TIMEOUT, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_exception = exc
            logger.warning(
                "Request to %s failed (attempt %d/%d): %s",
                url, attempt + 1, MAX_RETRIES, exc,
            )
            if attempt < len(BACKOFF_DELAYS) - 1:
                time.sleep(delay)
    raise last_exception  # type: ignore[misc]


def fetch_hyperliquid_volume() -> Optional[float]:
    """Fetch total 24h notional volume from Hyperliquid.

    Note: This covers the 230 native assets returned by metaAndAssetCtxs.
    HIP-3 markets (oil, gold, silver, equities, etc.) are not included
    because they are not exposed via the public API.
    """
    try:
        resp = _request_with_retry(
            "POST", HYPERLIQUID_URL, json={"type": "metaAndAssetCtxs"}
        )
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


def _fetch_binance_from_url(url: str) -> Optional[float]:
    """Try to fetch Binance volume from a single URL."""
    try:
        resp = _request_with_retry("GET", url)
        tickers = resp.json()
        if not isinstance(tickers, list):
            logger.error("Unexpected Binance response structure from %s", url)
            return None
        total = 0.0
        for ticker in tickers:
            if isinstance(ticker, dict):
                total += float(ticker.get("quoteVolume", 0) or 0)
        return round(total, 2)
    except Exception:
        return None


def fetch_binance_volume() -> Optional[float]:
    """Fetch total 24h quote volume from Binance futures with fallback URLs."""
    for url in BINANCE_URLS:
        result = _fetch_binance_from_url(url)
        if result is not None:
            logger.info("Binance data fetched successfully from %s", url)
            return result
        logger.warning("Binance URL %s failed, trying next fallback...", url)
    logger.error("All Binance URLs failed")
    return None

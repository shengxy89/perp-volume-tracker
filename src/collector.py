"""API collectors for Hyperliquid and Binance perpetual volume data."""

import csv
import io
import logging
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger(__name__)

HYPERLIQUID_URL = "https://api.hyperliquid.xyz/info"
BINANCE_URLS = [
    "https://fapi.binance.com/fapi/v1/ticker/24hr",
    "https://fapi1.binance.com/fapi/v1/ticker/24hr",
    "https://fapi2.binance.com/fapi/v1/ticker/24hr",
    "https://fapi3.binance.com/fapi/v1/ticker/24hr",
]
BINANCE_PUBLIC_DATA_S3_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
BINANCE_PUBLIC_DATA_BASE_URL = "https://data.binance.vision/data/futures/um/daily/klines"
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_DELAYS = [1, 2, 4]
PUBLIC_DATA_WORKERS = int(os.environ.get("BINANCE_PUBLIC_DATA_WORKERS", "16"))

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
    except Exception as exc:
        logger.warning("Binance URL %s failed: %s", url, exc)
        return None


def _get_binance_archive_date() -> str:
    """Return the UTC date used by Binance public daily archives."""
    override = os.environ.get("BINANCE_ARCHIVE_DATE")
    if override:
        return override
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def _fetch_binance_public_symbols() -> list[str]:
    """List USD stable-quoted symbols available in Binance USD-M futures archive."""
    resp = _request_with_retry(
        "GET",
        BINANCE_PUBLIC_DATA_S3_URL,
        params={
            "list-type": "2",
            "prefix": "data/futures/um/daily/klines/",
            "delimiter": "/",
        },
    )
    root = ET.fromstring(resp.content)
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    symbols: list[str] = []

    for elem in root.findall("s3:CommonPrefixes/s3:Prefix", namespace):
        if not elem.text:
            continue
        parts = elem.text.rstrip("/").split("/")
        symbol = parts[-1]
        if symbol.endswith(("USDT", "USDC", "BUSD")):
            symbols.append(symbol)

    return symbols


def _fetch_binance_public_symbol_volume(symbol: str, archive_date: str) -> Optional[float]:
    """Fetch one symbol's 1d quote volume from Binance public data archive."""
    url = (
        f"{BINANCE_PUBLIC_DATA_BASE_URL}/{symbol}/1d/"
        f"{symbol}-1d-{archive_date}.zip"
    )

    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
            names = archive.namelist()
            if not names:
                return None
            csv_text = archive.read(names[0]).decode("utf-8")
            rows = list(csv.DictReader(io.StringIO(csv_text)))
            if not rows:
                return None
            return float(rows[0]["quote_volume"])
    except Exception as exc:
        logger.debug("Failed to fetch Binance public archive for %s: %s", symbol, exc)
        return None


def fetch_binance_public_data_volume() -> Optional[float]:
    """Fetch Binance USD-M futures daily quote volume from public data archive.

    This is a fallback for environments where Binance Futures REST APIs return
    HTTP 451. The archive publishes completed UTC daily klines, so the fallback
    uses yesterday's UTC data by default.
    """
    archive_date = _get_binance_archive_date()
    logger.info("Fetching Binance public data archive for %s", archive_date)

    try:
        symbols = _fetch_binance_public_symbols()
    except Exception as exc:
        logger.error("Failed to list Binance public data symbols: %s", exc)
        return None

    if not symbols:
        logger.error("No Binance public data symbols found")
        return None

    total = 0.0
    found = 0
    max_workers = max(1, PUBLIC_DATA_WORKERS)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_fetch_binance_public_symbol_volume, symbol, archive_date): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            volume = future.result()
            if volume is None:
                continue
            total += volume
            found += 1

    if found == 0:
        logger.error("No Binance public archive files found for %s", archive_date)
        return None

    logger.info(
        "Binance public data archive fetched for %s symbols on %s",
        found,
        archive_date,
    )
    return round(total, 2)


def fetch_binance_volume() -> Optional[float]:
    """Fetch total 24h quote volume from Binance futures with fallback URLs."""
    for url in BINANCE_URLS:
        result = _fetch_binance_from_url(url)
        if result is not None:
            logger.info("Binance data fetched successfully from %s", url)
            return result
        logger.warning("Binance URL %s failed, trying next fallback...", url)

    logger.warning("Binance Futures API failed; trying public data archive fallback")
    result = fetch_binance_public_data_volume()
    if result is not None:
        return result

    logger.error("All Binance data sources failed")
    return None

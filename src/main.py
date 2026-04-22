"""Orchestrator: collect -> store -> chart -> email."""

import logging
import os
import sys
from datetime import datetime

import pytz

from src.collector import fetch_binance_volume, fetch_hyperliquid_volume
from src.email_report import send_alert, send_report
from src.chart import generate_chart
from src.storage import load_history, update_csv

logger = logging.getLogger(__name__)

TZ = os.environ.get("TZ", "Asia/Hong_Kong")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def get_today_date() -> str:
    tz = pytz.timezone(TZ)
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d")


def main() -> int:
    setup_logging()
    today = get_today_date()
    logger.info("Starting perp-volume-tracker for %s", today)

    hl_volume = fetch_hyperliquid_volume()
    bn_volume = fetch_binance_volume()

    errors = {}
    if hl_volume is None:
        errors["Hyperliquid"] = "HTTP error, timeout, or parsing error after retries"
    if bn_volume is None:
        errors["Binance"] = "HTTP error, timeout, or parsing error after retries"

    if errors:
        logger.error("Data collection failed for: %s", ", ".join(errors.keys()))
        send_alert(today, errors.get("Hyperliquid"), errors.get("Binance"))
        return 1

    ratio = round(hl_volume / bn_volume, 6)  # type: ignore[operator]
    hl_volume = round(hl_volume, 2)  # type: ignore[type-var]
    bn_volume = round(bn_volume, 2)  # type: ignore[type-var]

    logger.info("HL volume: %s | BN volume: %s | Ratio: %s", hl_volume, bn_volume, ratio)

    update_csv(today, hl_volume, bn_volume, ratio)
    df = load_history()
    chart_path = generate_chart(df, today, ratio)
    send_report(today, hl_volume, bn_volume, ratio, chart_path, df)

    logger.info("Run completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())

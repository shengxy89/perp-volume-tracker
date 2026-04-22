"""CSV storage logic for volume history."""

import logging
import os
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

CSV_PATH = os.path.join("data", "volume_history.csv")
COLUMNS = ["date", "hl_volume", "bn_volume", "ratio"]


def update_csv(date: str, hl_volume: Optional[float], bn_volume: Optional[float], ratio: Optional[float]) -> None:
    """Update the CSV with a new data point, overwriting if the date already exists."""
    if hl_volume is None or bn_volume is None or ratio is None:
        logger.warning("Skipping CSV update due to missing data")
        return

    new_row = pd.DataFrame([{
        "date": date,
        "hl_volume": hl_volume,
        "bn_volume": bn_volume,
        "ratio": ratio,
    }])

    if os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH)
        # Drop existing entry for the same date
        df = df[df["date"] != date]
        df = pd.concat([df, new_row], ignore_index=True)
    else:
        df = new_row

    df = df.sort_values("date").reset_index(drop=True)
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    df.to_csv(CSV_PATH, index=False)
    logger.info("CSV updated: %s rows total", len(df))


def load_history() -> pd.DataFrame:
    """Load the full volume history CSV."""
    if os.path.exists(CSV_PATH):
        return pd.read_csv(CSV_PATH)
    return pd.DataFrame(columns=COLUMNS)

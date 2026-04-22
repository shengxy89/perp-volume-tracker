"""Matplotlib chart generation for the volume ratio."""

import base64
import logging
import os
from io import BytesIO

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

logger = logging.getLogger(__name__)

CHART_PATH = os.path.join("data", "ratio_chart.png")


def generate_chart(df: pd.DataFrame, today_date: str, today_ratio: float) -> str:
    """Generate a line chart of the historical ratio and save to PNG.

    Returns the path to the saved chart.
    """
    if df.empty:
        logger.warning("No data available for chart generation")
        return ""

    # Adaptive window
    if len(df) > 30:
        plot_df = df.tail(30).copy()
    else:
        plot_df = df.copy()

    plot_df["date"] = pd.to_datetime(plot_df["date"])

    # Compute 7-day MA for the plot window
    ma7 = plot_df["ratio"].tail(7).mean()

    # Determine ATH / ATL across FULL history
    ath = df["ratio"].max()
    atl = df["ratio"].min()
    is_ath = today_ratio >= ath
    is_atl = today_ratio <= atl

    matplotlib.use("Agg")
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(10, 5))

    ax.plot(plot_df["date"], plot_df["ratio"], marker="o", markersize=4, linestyle="-", color="#1f77b4", label="Ratio")

    # 7-day MA horizontal line
    if not pd.isna(ma7):
        ax.axhline(ma7, color="gray", linestyle="--", linewidth=1, alpha=0.7, label=f"7-Day Avg: {ma7:.6f}")

    # Highlight latest point
    latest = plot_df.iloc[-1]
    ax.plot(latest["date"], latest["ratio"], "ro", markersize=8)
    ax.annotate(
        f"{latest['ratio']:.6f}",
        xy=(latest["date"], latest["ratio"]),
        xytext=(5, 10),
        textcoords="offset points",
        fontsize=9,
        color="red",
    )

    # ATH / ATL annotations
    if is_ath:
        ax.annotate(
            "ATH",
            xy=(latest["date"], latest["ratio"]),
            xytext=(5, -15),
            textcoords="offset points",
            fontsize=10,
            color="red",
            fontweight="bold",
        )
    elif is_atl:
        ax.annotate(
            "ATL",
            xy=(latest["date"], latest["ratio"]),
            xytext=(5, -15),
            textcoords="offset points",
            fontsize=10,
            color="blue",
            fontweight="bold",
        )

    # Tighten x-axis when very few points
    if len(plot_df) <= 3:
        min_date = plot_df["date"].min()
        max_date = plot_df["date"].max()
        padding = pd.Timedelta(days=3)
        ax.set_xlim(min_date - padding, max_date + padding)

    ax.set_title("Hyperliquid / Binance Perp Volume Ratio", fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=10)
    ax.set_ylabel("Ratio", fontsize=10)
    ax.tick_params(axis="x", rotation=45)
    ax.legend(loc="upper left")
    fig.tight_layout()

    os.makedirs(os.path.dirname(CHART_PATH), exist_ok=True)
    fig.savefig(CHART_PATH, dpi=150)
    plt.close(fig)
    logger.info("Chart saved to %s", CHART_PATH)
    return CHART_PATH


def chart_to_base64(chart_path: str) -> str:
    """Read a PNG file and return its base64-encoded string."""
    if not chart_path or not os.path.exists(chart_path):
        return ""
    with open(chart_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

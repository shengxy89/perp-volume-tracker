# Perp Volume Tracker

A lightweight, production-ready Python application that tracks the daily ratio of **Hyperliquid** vs **Binance** platform-level perpetual futures 24h trading volume, stores historical data, generates charts, and emails an HTML report every day.

---

## Architecture

```
Cron Trigger (GitHub Actions)
        |
        v
+-----------------+
|   Collector     |
|  HL API + BN API|
+--------+--------+
         |
         v
+-----------------+
|    Storage      |
|  CSV read/write |
+--------+--------+
         |
         v
+-----------------+
|     Chart       |
| matplotlib PNG  |
+--------+--------+
         |
         v
+-----------------+
|  Email Report   |
|  HTML + base64  |
+-----------------+
```

---

## Setup Instructions

1. **Fork or clone** this repository.
2. **Set repository secrets** in GitHub (`Settings > Secrets and variables > Actions`):
   - `SMTP_SERVER`
   - `SMTP_PORT`
   - `SMTP_USER`
   - `SMTP_PASSWORD`
   - `NOTIFY_EMAIL`
3. **Enable GitHub Actions** if not already enabled.
4. (Optional) Copy `.env.example` to `.env` and fill in values for local testing.

---

## Environment Variables

| Variable      | Description                        | Default               |
|---------------|------------------------------------|-----------------------|
| `SMTP_SERVER` | SMTP server hostname               | `smtp.gmail.com`      |
| `SMTP_PORT`   | SMTP server port                   | `587`                 |
| `SMTP_USER`   | Sender email address               | *(required)*          |
| `SMTP_PASSWORD`| SMTP app password                 | *(required)*          |
| `NOTIFY_EMAIL`| Recipient email(s), comma-separated| *(required)*          |
| `TZ`          | Timezone for date recording        | `Asia/Hong_Kong`      |
| `BINANCE_PUBLIC_DATA_WORKERS` | Parallel downloads for Binance public-data fallback | `16` |

---

## Manual Run

You can trigger the workflow manually from the GitHub Actions tab using **workflow_dispatch**.

To run locally:

```bash
pip install -r requirements.txt
python -m src.main
```

---

## Sample Email

The daily email contains:
- A summary table with volumes, ratio, moving averages, and day-over-day change
- An inline chart image (base64-encoded)
- ATH / ATL highlighting when applicable

*(Sample screenshot placeholder)*

---

## CSV Data Schema

`data/volume_history.csv`

| Column      | Type   | Description                          |
|-------------|--------|--------------------------------------|
| `date`      | string | Date in `YYYY-MM-DD`                 |
| `hl_volume` | float  | Hyperliquid 24h volume (USD)         |
| `bn_volume` | float  | Binance 24h volume (USD)             |
| `ratio`     | float  | HL / BN ratio (6 decimal places)     |

### Data Scope Note

The Hyperliquid volume is sourced from the public `metaAndAssetCtxs` API endpoint, which covers **230 native perpetual assets** (BTC, ETH, SOL, altcoins, etc.). It **does not include** HIP-3 markets such as oil, gold, silver, equities, or other real-world asset (RWA) perpetuals, because these are not exposed via the public API. As a result, the HL/BN ratio reflects native-crypto perpetual volume only and may understate Hyperliquid's true platform volume by approximately 25-35%.

Binance Futures REST endpoints may return HTTP 451 from some hosted runner regions. When that happens, the tracker falls back to Binance's official public data archive (`data.binance.vision`) and sums completed UTC daily USD-M futures kline `quote_volume` files for the previous UTC day.

---

## License

MIT

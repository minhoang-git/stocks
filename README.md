# Portfolio Pulse

A local Flask dashboard that monitors every ticker in `portfolio.csv`, refreshes market prices from Yahoo Finance, and alerts when a stock's session low reaches its rolling three-month low.

## What it does

- Imports symbols, purchase prices, and quantities from the supplied CSV.
- Polls Yahoo Finance every five minutes by default.
- Shows last price, daily move, rolling three-month low, distance from that low, and tracked position P&L.
- Creates an in-app alert when a symbol reaches its rolling three-month low.
- Sends the same alert through macOS Messages, with Twilio available as an alternative.
- Applies a per-symbol cooldown (24 hours by default) to prevent repeated messages for the same prolonged low.
- Keeps individual ticker failures visible without stopping the rest of the watchlist.

## Set up

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp portfolio.example.csv portfolio.csv
python run.py
```

Open [http://127.0.0.1:5001](http://127.0.0.1:5001).

The existing `run.py` automatically reuses the local `.venv` when dependencies are installed there.

## Enable phone messages with macOS Messages

Sign in to the Messages app on your Mac, then add these values to `.env`:

```dotenv
NOTIFICATION_PROVIDER=mac_messages
MAC_MESSAGES_ENABLED=true
ALERT_TO_NUMBER=+14085550123
```

Restart Portfolio Pulse and use **Send a test message** in the dashboard. The first attempt may trigger a macOS Automation permission prompt; choose **Allow** so the app can control Messages. Delivery uses iMessage when available, or SMS when your Mac and iPhone are configured for Text Message Forwarding.

### Optional Twilio alternative

To use Twilio instead, set `NOTIFICATION_PROVIDER=twilio` and configure `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER` in `.env`.

## Low-price rule

For each symbol, the app downloads one-minute prices for the current session and daily lows for the previous three months. An alert is eligible when:

```text
current session low <= rolling three-month low × (1 + LOW_TOLERANCE_PCT)
```

The default tolerance is zero, so only an actual rolling low qualifies. The notification is sent at most once per symbol during `ALERT_COOLDOWN_HOURS`.

## Change the portfolio

Copy `portfolio.example.csv` to `portfolio.csv`, then replace the sample rows with your own holdings. The file must contain at least a `Symbol` column. The optional `Current Price`, `Trade Date`, `Purchase Price`, and `Quantity` columns are imported when present. The private `portfolio.csv` file is ignored by Git and re-read on every refresh.

## Tests

```bash
PYTHONPATH=src pytest -q
```

## Google Cloud Run

The included `Dockerfile` runs the app with Gunicorn on Cloud Run's assigned
port. Set `WEB_AUTH_USERNAME` and `WEB_AUTH_PASSWORD` to protect the dashboard.
Hosted instances disable the in-process scheduler; call `POST /tasks/refresh`
every five minutes with the `X-Scheduler-Token` header instead. Keep
`portfolio.csv` and all credentials in Google Secret Manager, not in the
container image or Git repository.

macOS Messages is unavailable in Cloud Run's Linux environment. Use Twilio for
hosted SMS alerts by setting `NOTIFICATION_PROVIDER=twilio` and supplying the
Twilio credentials through Secret Manager.

## Data note

This app uses the third-party `yfinance` package to access publicly available Yahoo Finance data for personal use. Quotes may be delayed or temporarily unavailable and should not be treated as an execution-grade market-data feed.

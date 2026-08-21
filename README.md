# Portfolio Pulse

A Flask dashboard that monitors every ticker in `portfolio.csv` and refreshes market prices from Yahoo Finance.

## What it does

- Imports symbols, purchase prices, and quantities from the supplied CSV.
- Pins Nasdaq Composite, Dow 30, S&P 500, VIX, Bitcoin, and WTI crude oil above the portfolio.
- Polls Yahoo Finance every five minutes by default.
- Shows last price, daily move, rolling three- and six-month lows, three-day volume expansion, distance from the three-month low, and tracked position P&L.
- Marks symbols whose session low reaches the rolling three-month low.
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

## Low-price rule

For each symbol, the app downloads one-minute prices for the current session and daily lows for the previous three months. A symbol is marked at its low when:

```text
current session low <= rolling three-month low × (1 + LOW_TOLERANCE_PCT)
```

The default tolerance is zero, so only an actual rolling low qualifies.

The **3D volume spike** value is the average volume of the latest three
completed trading sessions divided by the average of the preceding 20
sessions. A value of `1.50×` means the recent three-day average is 50% higher
than that baseline.

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

## Free Render deployment

`render.yaml` defines a free, password-protected Render web service. The
Blueprint asks for the portfolio CSV and scheduler token as private environment
variables. A GitHub Actions workflow calls the protected
refresh endpoint every five minutes. Add matching `SERVICE_URL` and
`SCHEDULER_TOKEN` secrets to the GitHub repository after Render assigns the
service URL.

Render's free service uses an ephemeral filesystem, so refresh history can
reset after a restart or redeploy. Scheduled workflows in inactive public
repositories can also be disabled by GitHub after 60 days without repository
activity.

## Free Vercel deployment

Vercel can run this Flask project on its free Hobby tier using the root
`app.py` entry point and `vercel.json`. Configure the same private environment
variables described above, then set `SERVICE_URL` and `SCHEDULER_TOKEN` as
GitHub repository secrets so the existing workflow can refresh prices.

Vercel's function filesystem is ephemeral. The app stores SQLite data in
`/tmp`, so dashboard refresh history can reset when Vercel
recycles an instance. Use a persistent database before relying on this setup
for high-frequency or production monitoring.

Hosted dashboards can accept additional Basic Auth users through
`WEB_AUTH_USERS`, supplied as a private JSON object such as
`{"analyst":"use-a-strong-password"}`. The original
`WEB_AUTH_USERNAME`/`WEB_AUTH_PASSWORD` login remains supported.

## Data note

This app uses the third-party `yfinance` package to access publicly available Yahoo Finance data for personal use. Quotes may be delayed or temporarily unavailable and should not be treated as an execution-grade market-data feed.

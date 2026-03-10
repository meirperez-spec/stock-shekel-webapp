# Stock Shekel Calculator

## Overview
A Python web app that calculates how many shares of a given stock you can buy with a budget in Israeli Shekels (ILS). Uses yfinance for real-time stock prices and currency exchange rates.

## Architecture

### Core files
- `stock_lookup.py` — All business logic: ticker resolution, price fetching, ILS conversion, share calculation. Both the CLI and web app import from this module.
- `cli.py` — Command-line interface with argparse. Supports `python cli.py AAPL --amount 1000` or interactive prompts.
- `app.py` — Flask web server. Routes: `GET /` (UI), `POST /api/lookup` (main calc), `GET /api/search` (autocomplete). Has an in-memory cache (5 min TTL).
- `templates/index.html` — Single-page UI using Tailwind CSS CDN. Dark finance theme with SVG candlestick/chart decorations.
- `static/app.js` — Frontend JS handling form submission, loading states, result rendering.

### Key design decisions
- **US/NASDAQ prioritization**: `resolve_ticker()` prefers NASDAQ exchanges, then other US exchanges, before falling back to foreign listings. If no US result in initial search, it re-searches using the company's full name to find ADRs (e.g., "TSMC" → TSM on NYSE).
- **ILA handling**: TASE stocks report prices in Israeli Agora (ILA). The code detects `currency == "ILA"` and divides by 100 to convert to ILS.
- **Exchange rate**: Fetched via `yf.Ticker("USDILS=X").history(period="5d")`. Cached in `app.py` for 5 minutes.
- **Single library**: yfinance handles both stock data and FX rates — no extra API keys needed.

### Exchange code mapping
NASDAQ: `NMS`, `NGM`, `NCM`, `NAS`
NYSE/other US: `NYQ`, `NYS`, `PCX`, `ASE`, `BTS`

## Running locally

```bash
pip install -r requirements.txt

# CLI
python cli.py AAPL --amount 1000
python cli.py "Apple" --amount 5000

# Web app
python app.py
# Opens at http://localhost:5000
```

## Deployment
Configured for Render via `Procfile` and `render.yaml`. Start command: `gunicorn app:app`.

## Dependencies
- `yfinance` — stock prices, search, FX rates
- `flask` — web framework
- `gunicorn` — production WSGI server

## Conventions
- Keep all stock/finance logic in `stock_lookup.py` — the CLI and web app are thin wrappers
- Custom exceptions (`TickerNotFoundError`, `PriceUnavailableError`) for clean error handling
- No external API keys required

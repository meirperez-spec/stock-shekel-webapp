import logging

import yfinance as yf

# Suppress noisy yfinance HTTP error logs (e.g., 404 when probing ticker names)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


class TickerNotFoundError(Exception):
    pass


class PriceUnavailableError(Exception):
    pass


def resolve_ticker(query: str) -> dict | None:
    """Resolve a company name or ticker symbol to a ticker dict.

    Returns {"symbol": str, "name": str, "exchange": str} or None.
    """
    query = query.strip()
    if not query:
        return None

    # If it looks like a ticker (uppercase, 1-6 chars, no spaces, allows dots for .TA etc.)
    if query.replace(".", "").replace("-", "").isalpha() and len(query) <= 8 and " " not in query:
        ticker_candidate = query.upper()
        try:
            t = yf.Ticker(ticker_candidate)
            info = t.info
            if info.get("currentPrice") or info.get("regularMarketPrice"):
                return {
                    "symbol": ticker_candidate,
                    "name": info.get("shortName") or info.get("longName") or ticker_candidate,
                    "exchange": info.get("exchange", ""),
                }
        except Exception:
            pass  # Not a valid ticker, fall through to search

    # Fall back to search
    results = yf.Search(query, max_results=10)
    quotes = getattr(results, "quotes", []) or []
    equities = [q for q in quotes if q.get("quoteType") == "EQUITY"]

    if equities:
        # Prioritize US-listed stocks
        us_match = _pick_us_listed(equities)
        if us_match:
            return us_match

        # No US match found — try re-searching with the full company name
        # to find a US-listed ADR or equivalent
        first_symbol = equities[0].get("symbol", "")
        if first_symbol:
            us_result = _try_find_us_listing(first_symbol)
            if us_result:
                return us_result

        # Still no US match — return first equity result
        return _quote_to_dict(equities[0])

    # If no equity found, return first result if any
    if quotes:
        return _quote_to_dict(quotes[0])

    return None


# NASDAQ exchanges first, then other US exchanges
_NASDAQ_EXCHANGES = {"NMS", "NGM", "NCM", "NAS"}
_OTHER_US_EXCHANGES = {"NYQ", "NYS", "PCX", "ASE", "BTS"}
_US_EXCHANGES = _NASDAQ_EXCHANGES | _OTHER_US_EXCHANGES


def _try_find_us_listing(symbol: str) -> dict | None:
    """Given a non-US ticker, look up its full company name and re-search for a US listing."""
    try:
        info = yf.Ticker(symbol).info
        long_name = info.get("longName") or info.get("shortName")
        if not long_name:
            return None
        results = yf.Search(long_name, max_results=10)
        equities = [q for q in (results.quotes or []) if q.get("quoteType") == "EQUITY"]
        return _pick_us_listed(equities)
    except Exception:
        return None


def _pick_us_listed(equities: list[dict]) -> dict | None:
    """Return a US-listed equity, preferring NASDAQ over other US exchanges."""
    # First pass: NASDAQ
    for q in equities:
        if q.get("exchange", "") in _NASDAQ_EXCHANGES:
            return _quote_to_dict(q)
    # Second pass: other US exchanges
    for q in equities:
        if q.get("exchange", "") in _OTHER_US_EXCHANGES:
            return _quote_to_dict(q)
    return None


def _quote_to_dict(q: dict) -> dict:
    return {
        "symbol": q.get("symbol", ""),
        "name": q.get("shortname") or q.get("longname") or q.get("symbol", ""),
        "exchange": q.get("exchange", ""),
    }


def get_stock_price(ticker: str) -> dict:
    """Fetch current stock price for a ticker.

    Returns {"price": float, "currency": str, "name": str, "exchange": str}.
    Handles ILA (Israeli Agora) by converting to ILS.
    """
    t = yf.Ticker(ticker)
    info = t.info

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is None:
        raise PriceUnavailableError(f"Could not get price for {ticker}")

    currency = info.get("currency", "USD")
    name = info.get("shortName") or info.get("longName") or ticker

    # TASE stocks report in ILA (Agora). 100 ILA = 1 ILS
    if currency.upper() == "ILA":
        price = price / 100.0
        currency = "ILS"

    return {
        "price": float(price),
        "currency": currency,
        "name": name,
        "exchange": info.get("exchange", ""),
    }


def get_exchange_rate(from_currency: str, to_currency: str) -> float:
    """Get exchange rate between two currencies using Yahoo Finance.

    Returns the rate as a float (e.g., 3.6 for USD->ILS).
    """
    if from_currency.upper() == to_currency.upper():
        return 1.0

    pair = f"{from_currency.upper()}{to_currency.upper()}=X"
    t = yf.Ticker(pair)
    hist = t.history(period="5d")

    if hist.empty:
        raise PriceUnavailableError(
            f"Could not get exchange rate for {from_currency}/{to_currency}"
        )

    return float(hist["Close"].iloc[-1])


def lookup(query: str, amount_ils: float) -> dict:
    """Main lookup: resolve ticker, get price, convert currency, calculate shares.

    Returns a dict with all relevant information.
    """
    if amount_ils <= 0:
        raise ValueError("Amount must be positive")

    # Step 1: Resolve ticker
    resolved = resolve_ticker(query)
    if resolved is None:
        raise TickerNotFoundError(f"Could not find a stock matching '{query}'")

    symbol = resolved["symbol"]

    # Step 2: Get stock price
    stock = get_stock_price(symbol)
    price = stock["price"]
    currency = stock["currency"]

    # Step 3: Convert to ILS if needed
    if currency.upper() == "ILS":
        price_ils = price
        exchange_rate = None
    else:
        exchange_rate = get_exchange_rate(currency, "ILS")
        price_ils = price * exchange_rate

    # Step 4: Calculate shares
    shares_fractional = amount_ils / price_ils
    shares_whole = int(shares_fractional)
    cost_whole = shares_whole * price_ils
    remainder = amount_ils - cost_whole

    return {
        "symbol": symbol,
        "name": stock["name"],
        "exchange": stock["exchange"],
        "stock_price": price,
        "stock_currency": currency,
        "price_ils": round(price_ils, 2),
        "exchange_rate": round(exchange_rate, 4) if exchange_rate else None,
        "amount_ils": amount_ils,
        "shares_fractional": round(shares_fractional, 4),
        "shares_whole": shares_whole,
        "cost_whole_ils": round(cost_whole, 2),
        "remainder_ils": round(remainder, 2),
    }

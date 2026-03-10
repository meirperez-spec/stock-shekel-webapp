import logging
import time

import yfinance as yf

# Suppress noisy yfinance HTTP error logs (e.g., 404 when probing ticker names)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


class TickerNotFoundError(Exception):
    pass


class PriceUnavailableError(Exception):
    pass


# ---------------------------------------------------------------------------
# Module-level cache to reduce Yahoo Finance API calls
# ---------------------------------------------------------------------------
_cache = {}
_TICKER_CACHE_TTL = 600    # 10 min for ticker resolution
_PRICE_CACHE_TTL = 120     # 2 min for stock prices
_FX_CACHE_TTL = 300        # 5 min for exchange rates


def _get_cached(key: str, ttl: int):
    entry = _cache.get(key)
    if entry and (time.time() - entry["t"]) < ttl:
        return entry["v"]
    return None


def _set_cached(key: str, value):
    _cache[key] = {"v": value, "t": time.time()}


# ---------------------------------------------------------------------------
# Retry helper for yfinance calls that may get rate-limited
# ---------------------------------------------------------------------------
def _retry(fn, retries=2, delay=2):
    """Call fn(), retrying on rate-limit / transient errors."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if "rate" in err_str or "too many" in err_str or "429" in err_str:
                if attempt < retries:
                    time.sleep(delay * (attempt + 1))
                    continue
            raise
    raise last_err


# ---------------------------------------------------------------------------
# Ticker resolution
# ---------------------------------------------------------------------------
def resolve_ticker(query: str) -> dict | None:
    """Resolve a company name or ticker symbol to a ticker dict.

    Returns {"symbol": str, "name": str, "exchange": str} or None.
    """
    query = query.strip()
    if not query:
        return None

    cache_key = f"resolve:{query.upper()}"
    cached = _get_cached(cache_key, _TICKER_CACHE_TTL)
    if cached is not None:
        return cached

    result = _resolve_ticker_uncached(query)
    if result:
        _set_cached(cache_key, result)
    return result


def _resolve_ticker_uncached(query: str) -> dict | None:
    # If it looks like a ticker (uppercase, 1-6 chars, no spaces, allows dots for .TA etc.)
    if query.replace(".", "").replace("-", "").isalpha() and len(query) <= 8 and " " not in query:
        ticker_candidate = query.upper()
        try:
            info = _retry(lambda: yf.Ticker(ticker_candidate).info)
            if info.get("currentPrice") or info.get("regularMarketPrice"):
                return {
                    "symbol": ticker_candidate,
                    "name": info.get("shortName") or info.get("longName") or ticker_candidate,
                    "exchange": info.get("exchange", ""),
                }
        except Exception:
            pass  # Not a valid ticker, fall through to search

    # Fall back to search
    results = _retry(lambda: yf.Search(query, max_results=10))
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
        info = _retry(lambda: yf.Ticker(symbol).info)
        long_name = info.get("longName") or info.get("shortName")
        if not long_name:
            return None
        results = _retry(lambda: yf.Search(long_name, max_results=10))
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


# ---------------------------------------------------------------------------
# Stock price
# ---------------------------------------------------------------------------
def get_stock_price(ticker: str) -> dict:
    """Fetch current stock price for a ticker.

    Returns {"price": float, "currency": str, "name": str, "exchange": str}.
    Handles ILA (Israeli Agora) by converting to ILS.
    """
    cache_key = f"price:{ticker.upper()}"
    cached = _get_cached(cache_key, _PRICE_CACHE_TTL)
    if cached:
        return cached

    info = _retry(lambda: yf.Ticker(ticker).info)

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is None:
        raise PriceUnavailableError(f"Could not get price for {ticker}")

    currency = info.get("currency", "USD")
    name = info.get("shortName") or info.get("longName") or ticker

    # TASE stocks report in ILA (Agora). 100 ILA = 1 ILS
    if currency.upper() == "ILA":
        price = price / 100.0
        currency = "ILS"

    result = {
        "price": float(price),
        "currency": currency,
        "name": name,
        "exchange": info.get("exchange", ""),
    }
    _set_cached(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Exchange rate
# ---------------------------------------------------------------------------
def get_exchange_rate(from_currency: str, to_currency: str) -> float:
    """Get exchange rate between two currencies using Yahoo Finance.

    Returns the rate as a float (e.g., 3.6 for USD->ILS).
    """
    if from_currency.upper() == to_currency.upper():
        return 1.0

    cache_key = f"fx:{from_currency.upper()}{to_currency.upper()}"
    cached = _get_cached(cache_key, _FX_CACHE_TTL)
    if cached:
        return cached

    pair = f"{from_currency.upper()}{to_currency.upper()}=X"
    hist = _retry(lambda: yf.Ticker(pair).history(period="5d"))

    if hist.empty:
        raise PriceUnavailableError(
            f"Could not get exchange rate for {from_currency}/{to_currency}"
        )

    rate = float(hist["Close"].iloc[-1])
    _set_cached(cache_key, rate)
    return rate


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
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

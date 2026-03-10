import time

from flask import Flask, render_template, request, jsonify

from stock_lookup import lookup, TickerNotFoundError, PriceUnavailableError

app = Flask(__name__)

# Simple in-memory cache for exchange rates
_cache = {}
CACHE_TTL = 300  # 5 minutes


def _cached_lookup(query: str, amount_ils: float) -> dict:
    """Wrapper around lookup() with basic caching for exchange rates."""
    # Cache key based on query (not amount, since amount doesn't affect API calls)
    cache_key = query.strip().upper()
    now = time.time()

    # Check if we have a recent result for this ticker
    if cache_key in _cache and (now - _cache[cache_key]["time"]) < CACHE_TTL:
        cached = _cache[cache_key]["data"]
        # Recalculate shares with the new amount using cached price
        price_ils = cached["price_ils"]
        shares_fractional = amount_ils / price_ils
        shares_whole = int(shares_fractional)
        cost_whole = shares_whole * price_ils
        remainder = amount_ils - cost_whole
        return {
            **cached,
            "amount_ils": amount_ils,
            "shares_fractional": round(shares_fractional, 4),
            "shares_whole": shares_whole,
            "cost_whole_ils": round(cost_whole, 2),
            "remainder_ils": round(remainder, 2),
        }

    result = lookup(query, amount_ils)
    _cache[cache_key] = {"data": result, "time": now}
    return result


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/lookup", methods=["POST"])
def api_lookup():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    query = data.get("query", "").strip()
    amount = data.get("amount")

    if not query:
        return jsonify({"error": "Please enter a company name or ticker symbol"}), 400

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({"error": "Please enter a valid amount"}), 400

    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400

    try:
        result = _cached_lookup(query, amount)
        return jsonify(result)
    except TickerNotFoundError:
        return jsonify({"error": f"Could not find a stock matching '{query}'"}), 404
    except PriceUnavailableError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        return jsonify({"error": f"Something went wrong: {e}"}), 500


@app.route("/api/search")
def api_search():
    """Autocomplete endpoint for ticker/company search."""
    import yfinance as yf

    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])

    try:
        results = yf.Search(q, max_results=5)
        quotes = [
            {
                "symbol": r.get("symbol", ""),
                "name": r.get("shortname") or r.get("longname") or r.get("symbol", ""),
                "exchange": r.get("exchange", ""),
                "type": r.get("quoteType", ""),
            }
            for r in (results.quotes or [])
            if r.get("quoteType") == "EQUITY"
        ]
        return jsonify(quotes[:5])
    except Exception:
        return jsonify([])


if __name__ == "__main__":
    app.run(debug=True, port=5000)

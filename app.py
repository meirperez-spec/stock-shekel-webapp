from flask import Flask, render_template, request, jsonify

from stock_lookup import lookup, TickerNotFoundError, PriceUnavailableError

app = Flask(__name__)


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
        result = lookup(query, amount)
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

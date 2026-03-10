import argparse
import sys

from stock_lookup import lookup, TickerNotFoundError, PriceUnavailableError


def format_result(result: dict) -> str:
    lines = []
    lines.append("")
    lines.append("=" * 42)
    lines.append("  Stock Purchase Calculator")
    lines.append("=" * 42)
    lines.append(f"  Company:  {result['name']} ({result['symbol']})")
    lines.append(f"  Exchange: {result['exchange']}")
    lines.append("")

    if result["exchange_rate"]:
        lines.append(
            f"  Stock Price:   {result['stock_price']:,.2f} {result['stock_currency']}"
            f"  ({result['price_ils']:,.2f} ILS)"
        )
        lines.append(
            f"  Exchange Rate: 1 {result['stock_currency']} = {result['exchange_rate']} ILS"
        )
    else:
        lines.append(f"  Stock Price:   {result['price_ils']:,.2f} ILS")

    lines.append("")
    lines.append(f"  Your budget:   {result['amount_ils']:,.2f} ILS")
    lines.append("-" * 42)
    lines.append(f"  Whole shares:      {result['shares_whole']}")
    lines.append(f"  Cost:              {result['cost_whole_ils']:,.2f} ILS")
    lines.append(f"  Remaining:         {result['remainder_ils']:,.2f} ILS")
    lines.append("")
    lines.append(f"  Fractional shares: {result['shares_fractional']:.4f}")
    lines.append("=" * 42)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Calculate how many shares you can buy with a given ILS amount."
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Company name or ticker symbol (e.g., AAPL, 'Apple', TEVA.TA)",
    )
    parser.add_argument(
        "--amount", "-a",
        type=float,
        help="Amount in Israeli Shekels (ILS)",
    )

    args = parser.parse_args()

    # Interactive mode if no args provided
    query = args.query
    amount = args.amount

    if not query:
        query = input("Enter company name or ticker: ").strip()
    if not amount:
        amount_str = input("Enter amount in ILS: ").strip()
        try:
            amount = float(amount_str)
        except ValueError:
            print(f"Error: '{amount_str}' is not a valid number.")
            sys.exit(1)

    if amount <= 0:
        print("Error: Amount must be positive.")
        sys.exit(1)

    try:
        print(f"\nLooking up '{query}'...")
        result = lookup(query, amount)
        print(format_result(result))
    except TickerNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except PriceUnavailableError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

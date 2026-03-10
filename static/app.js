const form = document.getElementById("lookup-form");
const queryInput = document.getElementById("query");
const amountInput = document.getElementById("amount");
const submitBtn = document.getElementById("submit-btn");
const btnText = document.getElementById("btn-text");
const btnSpinner = document.getElementById("btn-spinner");
const errorBox = document.getElementById("error-box");
const errorText = document.getElementById("error-text");
const resultsDiv = document.getElementById("results");

function formatILS(n) {
  return "₪" + n.toLocaleString("en-IL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatCurrency(n, currency) {
  const symbols = { USD: "$", EUR: "\u20AC", GBP: "\u00A3", ILS: "\u20AA" };
  const sym = symbols[currency] || currency + " ";
  return sym + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function setLoading(loading) {
  submitBtn.disabled = loading;
  btnText.textContent = loading ? "Looking up\u2026" : "Calculate Shares";
  btnSpinner.classList.toggle("hidden", !loading);
}

function showError(msg) {
  errorText.textContent = msg;
  errorBox.classList.remove("hidden");
  resultsDiv.classList.add("hidden");
}

function hideError() {
  errorBox.classList.add("hidden");
}

function showResults(data) {
  hideError();

  document.getElementById("r-name").textContent = data.name;
  document.getElementById("r-symbol").textContent = data.symbol;
  document.getElementById("r-exchange").textContent = data.exchange;

  // Price display
  const priceMain = document.getElementById("r-price-main");
  const priceSub = document.getElementById("r-price-sub");
  const fxRow = document.getElementById("r-fx-row");

  if (data.exchange_rate) {
    priceMain.textContent = formatCurrency(data.stock_price, data.stock_currency);
    priceSub.textContent = formatILS(data.price_ils) + " per share";
    fxRow.classList.remove("hidden");
    document.getElementById("r-fx").textContent =
      `1 ${data.stock_currency} = ${data.exchange_rate} ILS`;
  } else {
    priceMain.textContent = formatILS(data.price_ils);
    priceSub.textContent = "per share";
    fxRow.classList.add("hidden");
  }

  // Budget
  document.getElementById("r-budget").textContent = formatILS(data.amount_ils);

  // Shares
  const sharesBig = document.getElementById("r-shares-big");
  const sharesLabel = document.getElementById("r-shares-label");

  if (data.shares_whole === 0) {
    sharesBig.textContent = "0";
    sharesLabel.textContent = "whole shares \u2014 stock price exceeds your budget";
  } else {
    sharesBig.textContent = data.shares_whole;
    sharesLabel.textContent = data.shares_whole === 1 ? "whole share" : "whole shares";
  }

  // Cost & remainder
  document.getElementById("r-cost").textContent = formatILS(data.cost_whole_ils);
  document.getElementById("r-remainder").textContent = formatILS(data.remainder_ils);

  // Fractional
  document.getElementById("r-fractional").textContent = data.shares_fractional.toFixed(4);

  // Show with animation
  resultsDiv.classList.remove("hidden");
  const card = resultsDiv.querySelector(".fade-in-up");
  card.style.animation = "none";
  void card.offsetWidth;
  card.style.animation = "";

  // Re-trigger count-up animation
  const countEl = resultsDiv.querySelector(".count-up");
  if (countEl) {
    countEl.style.animation = "none";
    void countEl.offsetWidth;
    countEl.style.animation = "";
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();

  const query = queryInput.value.trim();
  const amount = parseFloat(amountInput.value);

  if (!query) {
    showError("Please enter a company name or ticker symbol.");
    return;
  }
  if (!amount || amount <= 0) {
    showError("Please enter a valid positive amount.");
    return;
  }

  setLoading(true);

  try {
    const res = await fetch("/api/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, amount }),
    });

    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Something went wrong.");
      return;
    }

    showResults(data);
  } catch (err) {
    showError("Network error. Please try again.");
  } finally {
    setLoading(false);
  }
});

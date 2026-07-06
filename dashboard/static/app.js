const API = "";
let equityChart = null;
let currentMode = "paper";
let lastBacktestCurve = null;

// ---------- Clock ----------
function tickClock() {
  const el = document.getElementById("clock");
  el.textContent = new Date().toLocaleTimeString("en-IN", { hour12: false });
}
setInterval(tickClock, 1000);
tickClock();

// ---------- Helpers ----------
const fmtMoney = (n) => "₹" + Number(n ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const fmtNum = (n, d = 2) => Number(n ?? 0).toLocaleString("en-IN", { maximumFractionDigits: d });

async function getJSON(url) {
  const res = await fetch(API + url);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// ---------- Ticker tape ----------
async function refreshTape() {
  try {
    const [health, positions] = await Promise.all([
      getJSON("/api/health"),
      getJSON("/api/positions"),
    ]);
    document.getElementById("modeBadge").textContent = `MODE: ${health.trading_mode.toUpperCase()}`;

    const track = document.getElementById("tapeTrack");
    if (positions.positions.length === 0) {
      track.textContent = "No open positions — run a backtest below, or start the paper trading loop — Quant Desk — ";
    } else {
      const parts = positions.positions.map(
        (p) => `${p.symbol} ${p.quantity}@₹${fmtNum(p.avg_price)}`
      );
      track.textContent = parts.join("   ·   ") + "   ·   ";
    }
  } catch (e) {
    console.error(e);
  }
}

// ---------- Stats + equity curve ----------
async function refreshEquity(mode) {
  try {
    const data = await getJSON(`/api/equity-curve?mode=${mode}`);
    renderEquityChart(
      data.points.map((p) => p.timestamp),
      data.points.map((p) => p.equity)
    );
    if (data.points.length > 0) {
      const last = data.points[data.points.length - 1];
      document.getElementById("statEquity").textContent = fmtMoney(last.equity);
      document.getElementById("statCash").textContent = fmtMoney(last.cash);
    } else {
      document.getElementById("statEquity").textContent = fmtMoney(0);
      document.getElementById("statCash").textContent = fmtMoney(0);
    }
  } catch (e) {
    console.error(e);
  }
}

async function refreshPositions() {
  const data = await getJSON("/api/positions");
  document.getElementById("statPositions").textContent = data.positions.length;
  const tbody = document.querySelector("#positionsTable tbody");
  if (data.positions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty">No open positions</td></tr>`;
    return;
  }
  tbody.innerHTML = data.positions.map((p) => `
    <tr>
      <td>${p.symbol}</td>
      <td>${p.quantity}</td>
      <td>${fmtMoney(p.avg_price)}</td>
      <td>${p.stop_loss ? fmtMoney(p.stop_loss) : "—"}</td>
      <td>${p.take_profit ? fmtMoney(p.take_profit) : "—"}</td>
    </tr>`).join("");
}

async function refreshTrades() {
  const data = await getJSON("/api/trades");
  document.getElementById("statTrades").textContent = data.trades.length;
  const tbody = document.querySelector("#tradesTable tbody");
  if (data.trades.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty">No trades yet</td></tr>`;
    return;
  }
  const rows = data.trades.slice(-25).reverse();
  tbody.innerHTML = rows.map((t) => `
    <tr>
      <td>${new Date(t.timestamp).toLocaleString("en-IN")}</td>
      <td>${t.symbol}</td>
      <td class="side-${t.side.toLowerCase()}">${t.side}</td>
      <td>${t.quantity}</td>
      <td>${fmtMoney(t.price)}</td>
      <td class="${t.pnl > 0 ? 'pnl-pos' : t.pnl < 0 ? 'pnl-neg' : ''}">${t.pnl != null ? fmtMoney(t.pnl) : "—"}</td>
      <td>${t.strategy || "—"}</td>
    </tr>`).join("");
}

function renderEquityChart(labels, values) {
  const ctx = document.getElementById("equityChart");
  if (equityChart) equityChart.destroy();
  equityChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Equity",
        data: values,
        borderColor: "#E8A33D",
        backgroundColor: "rgba(232,163,61,0.08)",
        borderWidth: 1.5,
        pointRadius: 0,
        fill: true,
        tension: 0.15,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: labels.length > 0, ticks: { color: "#7C8798", maxTicksLimit: 8 }, grid: { color: "#232C38" } },
        y: { ticks: { color: "#7C8798" }, grid: { color: "#232C38" } },
      },
    },
  });
}

// ---------- Mode segmented control ----------
document.getElementById("modeSeg").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn");
  if (!btn) return;
  document.querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  currentMode = btn.dataset.mode;
  if (currentMode === "backtest") {
    if (lastBacktestCurve) {
      renderEquityChart(lastBacktestCurve.labels, lastBacktestCurve.values);
    }
  } else {
    refreshEquity(currentMode);
  }
});

// ---------- Backtest panel ----------
async function loadSymbols() {
  const data = await getJSON("/api/symbols");
  const sel = document.getElementById("btSymbol");
  sel.innerHTML = data.symbols.length
    ? data.symbols.map((s) => `<option value="${s}">${s}</option>`).join("")
    : `<option disabled selected>No data loaded</option>`;
}

document.getElementById("btRun").addEventListener("click", async () => {
  const btn = document.getElementById("btRun");
  const resultsEl = document.getElementById("btResults");
  const symbol = document.getElementById("btSymbol").value;
  if (!symbol) {
    resultsEl.innerHTML = `<div class="bt-empty">Load historical data for a symbol first (see README).</div>`;
    return;
  }
  const params = new URLSearchParams({
    symbol,
    strategy: document.getElementById("btStrategy").value,
    starting_capital: document.getElementById("btCapital").value,
    position_size_pct: Number(document.getElementById("btPosSize").value) / 100,
  });

  btn.disabled = true;
  btn.textContent = "Running…";
  try {
    const data = await getJSON(`/api/backtest?${params.toString()}`);
    renderBacktestResults(data);
  } catch (e) {
    resultsEl.innerHTML = `<div class="bt-empty">${e.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Backtest";
  }
});

function renderBacktestResults(data) {
  const m = data.metrics;
  const resultsEl = document.getElementById("btResults");
  resultsEl.innerHTML = `
    <div class="bt-metrics">
      <div class="bt-metric"><span class="bt-metric-label">Total Return</span><span class="bt-metric-value">${m.total_return_pct}%</span></div>
      <div class="bt-metric"><span class="bt-metric-label">CAGR</span><span class="bt-metric-value">${m.cagr_pct}%</span></div>
      <div class="bt-metric"><span class="bt-metric-label">Sharpe</span><span class="bt-metric-value">${m.sharpe_ratio}</span></div>
      <div class="bt-metric"><span class="bt-metric-label">Max Drawdown</span><span class="bt-metric-value">${m.max_drawdown_pct}%</span></div>
      <div class="bt-metric"><span class="bt-metric-label">Win Rate</span><span class="bt-metric-value">${m.win_rate_pct ?? "—"}%</span></div>
      <div class="bt-metric"><span class="bt-metric-label">Trades</span><span class="bt-metric-value">${m.num_trades ?? 0}</span></div>
    </div>`;

  lastBacktestCurve = {
    labels: data.equity_curve.map((p) => p.timestamp),
    values: data.equity_curve.map((p) => p.equity),
  };
  document.querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
  document.querySelector('.seg-btn[data-mode="backtest"]').classList.add("active");
  currentMode = "backtest";
  renderEquityChart(lastBacktestCurve.labels, lastBacktestCurve.values);
}

// ---------- Init ----------
async function init() {
  await Promise.allSettled([
    refreshTape(),
    refreshEquity(currentMode),
    refreshPositions(),
    refreshTrades(),
    loadSymbols(),
  ]);
}
init();
setInterval(refreshTape, 15000);

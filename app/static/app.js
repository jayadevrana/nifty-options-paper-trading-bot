const stateUrl = "/api/state";

function formatCurrency(value) {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatNumber(value) {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value);
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setPill(id, text, type) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = "pill";
  if (type === "neutral") el.classList.add("neutral");
  if (type === "danger") el.classList.add("danger");
}

function renderPreview(plan) {
  const container = document.getElementById("preview-content");
  if (!container) return;
  if (!plan) {
    container.innerHTML = `<div class="card"><span class="card-title">Preview</span><strong>No preview available yet.</strong></div>`;
    return;
  }

  const cards = [];
  cards.push(
    `<div class="card"><span class="card-title">Decision</span><strong>${plan.reason}</strong></div>`
  );
  if (plan.valid) {
    cards.push(
      `<div class="card"><span class="card-title">Structure</span><strong>${plan.short_put_strike} PE / ${plan.long_put_strike} PE hedge / ${plan.short_call_strike} CE / ${plan.long_call_strike} CE hedge</strong></div>`
    );
    cards.push(
      `<div class="card"><span class="card-title">Sizing</span><strong>${plan.lots} lot(s), credit ${formatNumber(plan.credit_points)} pts, max loss ${formatCurrency(plan.total_max_loss)}</strong></div>`
    );
    cards.push(
      `<div class="card"><span class="card-title">Margin</span><strong>Hedged est. ${formatCurrency(plan.total_estimated_margin)} • Naked ref. ${formatCurrency(plan.reference_naked_margin_per_lot)}</strong></div>`
    );
    setPill("preview-badge", "Tradable", null);
  } else {
    setPill("preview-badge", "Filtered", "danger");
  }
  container.innerHTML = cards.join("");
}

function renderOpenTrade(openTrade) {
  const container = document.getElementById("open-trade-content");
  if (!container) return;
  if (!openTrade) {
    container.innerHTML = `<div class="card"><span class="card-title">Status</span><strong>No open paper trade.</strong></div>`;
    setPill("open-trade-pill", "Flat", "neutral");
    return;
  }

  const mark = openTrade.mark_to_market || {};
  setPill("open-trade-pill", "Live Position", null);
  container.innerHTML = `
    <div class="card">
      <span class="card-title">Position</span>
      <strong>${openTrade.short_put_strike} / ${openTrade.long_put_strike} PE and ${openTrade.short_call_strike} / ${openTrade.long_call_strike} CE</strong>
    </div>
    <div class="card">
      <span class="card-title">Entry</span>
      <strong>${openTrade.lots} lot(s) at ${formatNumber(openTrade.entry_credit)} pts credit</strong>
    </div>
    <div class="card">
      <span class="card-title">MTM</span>
      <strong class="${(mark.gross_pnl || 0) >= 0 ? "positive" : "negative"}">${formatCurrency(mark.gross_pnl || 0)}</strong>
    </div>
    <div class="card">
      <span class="card-title">Exit Signal</span>
      <strong>${mark.exit_signal || "Holding"}</strong>
    </div>
  `;
}

function renderTradeLog(trades) {
  const tbody = document.getElementById("trade-table");
  if (!tbody) return;
  if (!trades || trades.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8">No trades yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = trades
    .map((trade) => {
      const structure = `${trade.short_put_strike}/${trade.long_put_strike} PE • ${trade.short_call_strike}/${trade.long_call_strike} CE`;
      const netClass = (trade.net_pnl || 0) >= 0 ? "positive" : "negative";
      return `
        <tr>
          <td>${trade.opened_at ? new Date(trade.opened_at).toLocaleString("en-IN") : "-"}</td>
          <td>${trade.closed_at ? new Date(trade.closed_at).toLocaleString("en-IN") : "-"}</td>
          <td>${structure}</td>
          <td>${trade.lots}</td>
          <td>${trade.gross_pnl !== null ? formatCurrency(trade.gross_pnl) : "-"}</td>
          <td>${trade.charges !== null ? formatCurrency(trade.charges) : "-"}</td>
          <td class="${netClass}">${trade.net_pnl !== null ? formatCurrency(trade.net_pnl) : "-"}</td>
          <td>${trade.exit_reason || trade.status}</td>
        </tr>
      `;
    })
    .join("");
}

function renderDrawdownMap(entries) {
  const container = document.getElementById("drawdown-map");
  if (!container) return;
  container.innerHTML = (entries || [])
    .map(
      (entry) =>
        `<div class="chip">${entry.trading_day}: ${formatCurrency(entry.worst_drawdown)}</div>`
    )
    .join("");
}

function renderEquityChart(points) {
  const svg = document.getElementById("equity-chart");
  if (!svg) return;
  if (!points || points.length < 2) {
    svg.innerHTML = "";
    return;
  }

  const width = 900;
  const height = 260;
  const padding = 22;
  const values = points.map((item) => item.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);

  const path = points
    .map((point, index) => {
      const x = padding + (index / (points.length - 1)) * (width - padding * 2);
      const y =
        height - padding - ((point.equity - min) / span) * (height - padding * 2);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="transparent"></rect>
    <path d="${path}" fill="none" stroke="#0a7a63" stroke-width="4" stroke-linecap="round"></path>
    <text x="${padding}" y="${padding}" fill="#6f655a" font-size="14">Peak ${formatCurrency(max)}</text>
    <text x="${padding}" y="${height - 8}" fill="#6f655a" font-size="14">Low ${formatCurrency(min)}</text>
  `;
}

async function post(url) {
  await fetch(url, { method: "POST" });
  await refresh();
}

async function refresh() {
  const response = await fetch(stateUrl);
  const state = await response.json();

  setPill(
    "status-pill",
    state.engine_enabled ? "Engine On" : "Engine Paused",
    state.engine_enabled ? null : "danger"
  );
  setText("spot-value", state.last_snapshot ? formatNumber(state.last_snapshot.spot) : "-");
  setText("vix-value", state.last_snapshot ? formatNumber(state.last_snapshot.vix) : "-");
  setText("expiry-value", state.last_snapshot ? state.last_snapshot.expiry : "-");
  setText("lot-size-value", state.last_snapshot ? state.last_snapshot.lot_size : "-");
  setText(
    "equity-value",
    state.latest_equity ? formatCurrency(state.latest_equity.equity) : formatCurrency(state.capital)
  );
  setText(
    "drawdown-value",
    state.latest_equity ? formatCurrency(state.latest_equity.drawdown) : formatCurrency(0)
  );

  const meta = document.getElementById("snapshot-meta");
  if (meta) {
    if (state.last_error) {
      meta.textContent = `Feed warning: ${state.last_error}`;
    } else if (state.last_snapshot) {
      meta.textContent = `NSE public feed • Exchange timestamp ${state.last_snapshot.exchange_timestamp} • Fetched ${new Date(state.last_snapshot.fetched_at).toLocaleString("en-IN")}`;
    } else {
      meta.textContent = "Waiting for first NSE snapshot.";
    }
  }

  renderPreview(state.preview_plan);
  renderOpenTrade(state.open_trade);
  renderTradeLog(state.trades);
  renderDrawdownMap(state.drawdown_map);
  renderEquityChart(state.equity_points);
}

document.getElementById("start-button")?.addEventListener("click", () => post("/api/control/start"));
document.getElementById("stop-button")?.addEventListener("click", () => post("/api/control/stop"));
document.getElementById("preview-button")?.addEventListener("click", () => post("/api/control/preview"));

refresh();
setInterval(refresh, 10000);

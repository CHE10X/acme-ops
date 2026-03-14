const API = {
  overview: "/api/overview",
  agents: "/api/agents",
  economics: "/api/economics",
  alerts: "/api/alerts",
  runaway: "/api/runaway",
  burnrate: "/api/burnrate",
  modelTimeline: "/api/model-timeline",
  heatmap: "/api/heatmap",
  modelEfficiency: "/api/model-efficiency",
  loops: "/api/loops",
  costAnomalies: "/api/cost-anomalies",
};

const MONEY = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 4,
});

const fmtNumber = (value) => (value === null || value === undefined ? "-" : Number(value).toLocaleString());
const fmtPct = (value) => {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${Number(value).toFixed(2)}%`;
};

const classFromState = (state) => `state-${(state || "unavailable").toLowerCase()}`;

function severityBadge(state) {
  const cls = classFromState(state);
  return `<span class="${cls}">${state || "unavailable"}</span>`;
}

function applyMessages(targetEl, payload) {
  const messages = [];
  if (payload && payload.message) {
    messages.push(payload.message);
  }
  if (payload && payload.status_messages) {
    messages.push(...payload.status_messages);
  }
  if (payload && payload.available === false && !messages.includes("source file unavailable")) {
    messages.push("source file unavailable");
  }
  const src = payload && payload.sources ? payload.sources : {};
  const missing = [];
  for (const meta of Object.values(src)) {
    if (!meta || meta.available === false) {
      missing.push("source file unavailable");
    }
  }
  if (missing.length > 0 && !messages.includes("source file unavailable")) {
    messages.push("source file unavailable");
  }
  if (messages.length === 0) {
    targetEl.textContent = "";
    return;
  }
  targetEl.textContent = [...new Set(messages)].join(" | ");
}

function renderOverview(data) {
  const overview = data && data.metrics ? data.metrics : {};
  document.getElementById("oTokens1h").textContent = fmtNumber(overview.total_tokens_last_1h);
  document.getElementById("oTokens24h").textContent = fmtNumber(overview.total_tokens_last_24h);
  document.getElementById("oActive").textContent = fmtNumber(overview.active_sessions);
  document.getElementById("oCost").textContent = MONEY.format(overview.cost_today || 0);
  const topRisk = overview.top_risk_agent;
  if (topRisk && topRisk.agent_id) {
    document.getElementById("oRisk").textContent = `${topRisk.agent_id} (${topRisk.risk_score || 0}, ${topRisk.risk_level || "unavailable"})`;
  } else {
    document.getElementById("oRisk").textContent = "none";
  }
  if (overview.latest_alert && overview.latest_alert.message) {
    document.getElementById("oAlert").textContent = `${overview.latest_alert.severity || "info"}: ${overview.latest_alert.message}`;
  } else {
    document.getElementById("oAlert").textContent = "no alerts";
  }
  document.getElementById("stateBanner").textContent = `Dashboard refresh: ${overview.last_refresh || "unavailable"}`;
}

function renderAgents(data) {
  const rows = (data && data.agents) || [];
  const tbody = document.getElementById("agentsRows");
  tbody.innerHTML = "";
  if (!rows.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="8">no agent telemetry available</td>`;
    tbody.appendChild(row);
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.agent_id}</td>
      <td>${fmtNumber(row.hourly_tokens)}</td>
      <td>${fmtNumber(row.predicted_tokens)}</td>
      <td>${fmtNumber(row.risk_score)}</td>
      <td><span class="${classFromState(row.risk_level)}">${row.risk_level || "unavailable"}</span></td>
      <td>${Number(row.efficiency || 0).toFixed(3)}</td>
      <td>${row.dominant_model}</td>
      <td>${fmtNumber(row.alerts_count)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderRunaway(data) {
  const rows = (data && data.runaway_agents) || [];
  const tbody = document.getElementById("runawayRows");
  tbody.innerHTML = "";
  if (!rows.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="6">no runaway agents detected</td>`;
    tbody.appendChild(row);
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.agent_id}</td>
      <td>${fmtNumber(row.risk_score)}</td>
      <td><span class="${classFromState(row.risk_level)}">${row.risk_level || "unavailable"}</span></td>
      <td>${fmtNumber(row.recent_tokens)}</td>
      <td>${fmtNumber(row.alerts_last_hour)}</td>
      <td>${row.latest_alert || "-"}</td>
    `;
    tbody.appendChild(tr);
  });
}

function colorForBurnRate(value) {
  if (value < 200) {
    return "#1f7a1f";
  }
  if (value <= 800) {
    return "#9a6d00";
  }
  return "#b71c1c";
}

function renderBurnRate(data) {
  const canvas = document.getElementById("burnRateCanvas");
  const messageTarget = document.getElementById("burnrateMessage");
  const points = (data && data.points) || [];

  if (!canvas) {
    return;
  }

  const containerWidth = canvas.clientWidth || 980;
  const containerHeight = canvas.clientHeight || 220;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = containerWidth * dpr;
  canvas.height = containerHeight * dpr;

  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, containerWidth, containerHeight);
  ctx.fillStyle = "#f8fbff";
  ctx.fillRect(0, 0, containerWidth, containerHeight);

  if (!points.length) {
    messageTarget.textContent = data && data.message ? data.message : "no telemetry available";
    return;
  }
  const tokens = points.map((p) => Number(p.tokens || 0));
  const maxTokens = Math.max(1, Math.max(...tokens));
  const minY = containerHeight - 28;
  const chartHeight = containerHeight - 40;
  const chartLeft = 50;
  const chartRight = containerWidth - 10;
  const chartWidth = chartRight - chartLeft;

  ctx.strokeStyle = "#ccd4df";
  ctx.beginPath();
  ctx.moveTo(chartLeft, minY);
  ctx.lineTo(chartRight, minY);
  ctx.moveTo(chartLeft, 10);
  ctx.lineTo(chartLeft, containerHeight - 20);
  ctx.stroke();

  ctx.fillStyle = "#54606d";
  ctx.font = "12px Arial";
  ctx.fillText("tokens/min", 4, 16);

  ctx.beginPath();
  points.forEach((point, index) => {
    const tokenValue = Number(point.tokens || 0);
    const x = chartLeft + (chartWidth * index) / Math.max(1, points.length - 1);
    const y = 10 + (chartHeight - ((tokenValue / maxTokens) * chartHeight));
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.strokeStyle = "#1f2a37";
  ctx.stroke();

  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const curr = points[i];
    const x1 = chartLeft + (chartWidth * (i - 1)) / Math.max(1, points.length - 1);
    const x2 = chartLeft + (chartWidth * i) / Math.max(1, points.length - 1);
    const y1 = 10 + (chartHeight - ((Number(prev.tokens || 0) / maxTokens) * chartHeight));
    const y2 = 10 + (chartHeight - ((Number(curr.tokens || 0) / maxTokens) * chartHeight));
    ctx.beginPath();
    ctx.strokeStyle = colorForBurnRate(curr.tokens || 0);
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }

  const mid = points[Math.floor(points.length / 2)] || {};
  if (mid.timestamp) {
    messageTarget.textContent = `${points.length} minute points | latest ${mid.timestamp}`;
  } else {
    messageTarget.textContent = "no telemetry events found";
  }
}

function renderHeatmap(data) {
  const headers = document.getElementById("heatmapHeaderRow");
  const tbody = document.getElementById("heatmapRows");
  const buckets = (data && data.bucket_starts) || [];
  const heatmap = (data && data.heatmap) || [];

  if (!headers || !tbody) {
    return;
  }
  headers.innerHTML = "";
  const headAgent = document.createElement("th");
  headAgent.textContent = "agent_id";
  headers.appendChild(headAgent);
  buckets.forEach((bucket) => {
    const cell = document.createElement("th");
    cell.textContent = String(bucket).replace("T", " ").slice(0, 16);
    headers.appendChild(cell);
  });

  tbody.innerHTML = "";
  if (!heatmap.length) {
    const row = document.createElement("tr");
    const colSpan = Math.max(1, buckets.length + 1);
    row.innerHTML = `<td colspan="${colSpan}">no heatmap data</td>`;
    tbody.appendChild(row);
    return;
  }
  heatmap.forEach((agentRow) => {
    const tr = document.createElement("tr");
    const agentCell = document.createElement("td");
    agentCell.textContent = agentRow.agent_id || "unknown";
    tr.appendChild(agentCell);
    const bucketMap = {};
    (agentRow.buckets || []).forEach((bucket) => {
      bucketMap[bucket.bucket_start] = bucket;
    });
    buckets.forEach((bucketStart) => {
      const bucket = bucketMap[bucketStart] || { total_tokens: 0, intensity: "none" };
      const td = document.createElement("td");
      const tokens = Number(bucket.total_tokens || 0);
      const cls = `heat-${bucket.intensity || "none"}`;
      td.className = cls;
      td.textContent = tokens > 0 ? tokens : "";
      td.title = `${bucketStart}: ${tokens} tokens`;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

function renderModelEfficiency(data) {
  const rows = (data && data.models) || [];
  const tbody = document.getElementById("modelEfficiencyRows");
  tbody.innerHTML = "";
  if (!rows.length) {
    const row = document.createElement("tr");
    row.innerHTML = "<td colspan=\"7\">no model data</td>";
    tbody.appendChild(row);
    return;
  }
  rows.forEach((row) => {
    const ratio = row.efficiency_ratio ?? 0;
    const scoreState = ratio < 0.25 ? "high" : ratio < 0.55 ? "caution" : "healthy";
    const cost = row.cost_total;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.model}</td>
      <td>${fmtNumber(row.events_count)}</td>
      <td>${fmtNumber(row.total_tokens)}</td>
      <td>${fmtNumber(row.avg_tokens_per_event)}</td>
      <td><span class="${classFromState(scoreState)}">${Number(ratio).toFixed(3)}</span></td>
      <td>${row.avg_latency_ms === null ? "-" : Number(row.avg_latency_ms || 0).toFixed(2)}</td>
      <td>${cost === null ? "-" : MONEY.format(cost || 0)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderEconomics(data) {
  document.getElementById("eEfficiency").textContent = Number((data && data.totals && data.totals.token_efficiency_index) || 0).toFixed(3);
  document.getElementById("eTokens").textContent = fmtNumber((data && data.totals && data.totals.total_tokens) || 0);
  document.getElementById("eCost").textContent = MONEY.format((data && data.totals && data.totals.total_cost_usd) || 0);
  document.getElementById("eGenerated").textContent = (data && data.totals && data.totals.generated_at) || "-";

  const agentTbody = document.getElementById("econAgentRows");
  agentTbody.innerHTML = "";
  (data.agent_rows || []).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.agent_id}</td>
      <td>${fmtNumber(row.token_total)}</td>
      <td>${MONEY.format(row.cost_total || 0)}</td>
      <td>${row.cost_per_task ? MONEY.format(row.cost_per_task) : "-"}</td>
      <td>${(row.efficiency_index || 0).toFixed(3)}</td>
    `;
    agentTbody.appendChild(tr);
  });

  const modelTbody = document.getElementById("econModelRows");
  modelTbody.innerHTML = "";
  (data.model_rows || []).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.model}</td>
      <td>${fmtNumber(row.token_total)}</td>
      <td>${MONEY.format(row.cost_total || 0)}</td>
    `;
    modelTbody.appendChild(tr);
  });
}

function renderCostAnomalies(data) {
  const rows = (data && data.anomalies) || [];
  const tbody = document.getElementById("costAnomalyRows");
  tbody.innerHTML = "";
  if (!rows.length) {
    const row = document.createElement("tr");
    row.innerHTML = "<td colspan=\"8\">no cost anomalies detected</td>";
    tbody.appendChild(row);
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.timestamp || "-"}</td>
      <td>${row.scope || "-"}</td>
      <td>${row.entity || "-"}</td>
      <td>${MONEY.format(row.baseline_cost || 0)}</td>
      <td>${MONEY.format(row.observed_cost || 0)}</td>
      <td>${fmtPct(row.delta_percent)}</td>
      <td><span class="${classFromState(row.severity)}">${row.severity || "-"}</span></td>
      <td>${row.reason || "-"}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderLoops(data) {
  const rows = (data && data.loops) || [];
  const tbody = document.getElementById("loopRows");
  tbody.innerHTML = "";
  if (!rows.length) {
    const row = document.createElement("tr");
    row.innerHTML = "<td colspan=\"7\">no strong loop patterns</td>";
    tbody.appendChild(row);
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.agent_id}</td>
      <td>${row.session_id || "unknown-session"}</td>
      <td>${fmtNumber(row.event_count)}</td>
      <td>${fmtNumber(row.time_window_minutes)}</td>
      <td><span class="${classFromState(row.loop_score)}">${row.loop_score || "unavailable"}</span></td>
      <td>${(row.reason_signals || []).join(", ")}</td>
      <td>${row.latest_timestamp || "-"}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderModelTimeline(data) {
  const tbody = document.getElementById("modelTimelineRows");
  tbody.innerHTML = "";
  const rows = (data && data.events) || [];
  if (!rows.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="5">no model downgrades recorded</td>`;
    tbody.appendChild(row);
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.timestamp || "unavailable"}</td>
      <td>${row.agent || "-"}</td>
      <td>${row.original_model || "-"}</td>
      <td>${row.new_model || "-"}</td>
      <td>${row.reason || "-"}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderAlerts(data) {
  const tbody = document.getElementById("alertRows");
  tbody.innerHTML = "";
  if (!data.alerts || data.alerts.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="4">no alerts</td>`;
    tbody.appendChild(row);
    return;
  }
  data.alerts.slice(0, 75).forEach((alert) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${alert.timestamp || "unavailable"}</td>
      <td>${severityBadge(alert.severity || "unavailable")}</td>
      <td>${alert.message}</td>
      <td>${alert.agent || "-"}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function renderStatus() {
  try {
    const [overview, agents, economics, alerts, runaway, burnrate, modelTimeline, heatmap, modelEfficiency, loops, costAnomalies] =
      await Promise.all([
        fetch(API.overview).then((r) => r.json()),
        fetch(API.agents).then((r) => r.json()),
        fetch(API.economics).then((r) => r.json()),
        fetch(API.alerts).then((r) => r.json()),
        fetch(API.runaway).then((r) => r.json()),
        fetch(API.burnrate).then((r) => r.json()),
        fetch(API.modelTimeline).then((r) => r.json()),
        fetch(API.heatmap).then((r) => r.json()),
        fetch(API.modelEfficiency).then((r) => r.json()),
        fetch(API.loops).then((r) => r.json()),
        fetch(API.costAnomalies).then((r) => r.json()),
      ]);

    renderOverview(overview);
    renderRunaway(runaway);
    renderBurnRate(burnrate);
    renderHeatmap(heatmap);
    renderAgents(agents);
    renderModelEfficiency(modelEfficiency);
    renderEconomics(economics);
    renderCostAnomalies(costAnomalies);
    renderLoops(loops);
    renderModelTimeline(modelTimeline);
    renderAlerts(alerts);

    applyMessages(document.getElementById("agentsMessage"), agents);
    applyMessages(document.getElementById("economicsMessage"), economics);
    applyMessages(document.getElementById("alertsMessage"), alerts);
    applyMessages(document.getElementById("runawayMessage"), runaway);
    applyMessages(document.getElementById("burnrateMessage"), burnrate);
    applyMessages(document.getElementById("modelTimelineMessage"), modelTimeline);
    applyMessages(document.getElementById("heatmapMessage"), heatmap);
    applyMessages(document.getElementById("modelEfficiencyMessage"), modelEfficiency);
    applyMessages(document.getElementById("loopsMessage"), loops);
    applyMessages(document.getElementById("costAnomaliesMessage"), costAnomalies);

    const allMessages = [
      ...(overview.status_messages || []),
      ...(economicErrorFromPayload(economics) ? ["source file unavailable"] : []),
    ];

    if (allMessages.length) {
      document.getElementById("stateBanner").className = "banner unavailable";
      document.getElementById("stateBanner").textContent = [...new Set(allMessages)].join(" | ");
    } else {
      document.getElementById("stateBanner").className = "banner";
      document.getElementById("stateBanner").textContent = "All available Bonfire sources loaded.";
    }

    document.getElementById("refreshTime").textContent = `last refresh: ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    document.getElementById("stateBanner").className = "banner state-runaway";
    document.getElementById("stateBanner").textContent = `refresh failed: ${error.message}`;
    document.getElementById("refreshTime").textContent = "refresh failed";
  }
}

function economicErrorFromPayload(payload) {
  if (!payload) {
    return false;
  }
  return payload.available === false || (Array.isArray(payload.status_messages) && payload.status_messages.includes("source file unavailable"));
}

document.getElementById("refreshBtn").addEventListener("click", () => renderStatus());
renderStatus();
setInterval(() => {
  renderStatus();
}, 15000);

const state = {
  sessionId: "",
  sessions: [],
  lastAuditEventIds: new Set(),
};

function byId(id) {
  const node = document.getElementById(id);
  if (!node) {
    throw new Error(`missing required node id=${id}`);
  }
  return node;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (error) {
    payload = { detail: text };
  }
  if (!response.ok) {
    const detail = payload.detail ?? JSON.stringify(payload);
    throw new Error(`request failed ${response.status} ${url}: ${detail}`);
  }
  return payload;
}

function showStatus(message, tone = "info") {
  const banner = byId("status-banner");
  banner.className = `status-banner visible ${tone}`;
  banner.textContent = message;
  window.clearTimeout(showStatus.timer);
  showStatus.timer = window.setTimeout(() => {
    banner.className = "status-banner";
    banner.textContent = "";
  }, 5000);
}
showStatus.timer = 0;

function appendTimeline(text) {
  const list = byId("event-timeline");
  const li = document.createElement("li");
  li.className = "timeline-item";
  li.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
  list.prepend(li);
  while (list.children.length > 60) {
    list.removeChild(list.lastChild);
  }
}

function renderChatMessages(messages) {
  const container = byId("chat-messages");
  if (!messages.length) {
    container.innerHTML = '<p class="muted">No messages yet.</p>';
    return;
  }

  const rows = messages
    .slice()
    .reverse()
    .map((row) => {
      const parts = Array.isArray(row.parts) ? row.parts : [];
      const text = parts
        .map((part) => (part && part.type === "text" ? String(part.text ?? "") : ""))
        .filter((part) => part.length > 0)
        .join("\n") || "(non-text response)";
      const id = row.info && row.info.id ? row.info.id : "message";
      return `<article class="message"><header>${escapeHtml(id)}</header><pre>${escapeHtml(text)}</pre></article>`;
    })
    .join("");
  container.innerHTML = rows;
}

function renderTableRows(bodyId, rowsHtml, emptyText) {
  const body = byId(bodyId);
  if (!rowsHtml.length) {
    body.innerHTML = `<tr><td colspan="6" class="muted">${escapeHtml(emptyText)}</td></tr>`;
    return;
  }
  body.innerHTML = rowsHtml.join("");
}

async function loadSessions() {
  const payload = await fetchJson("/v1/chat/sessions");
  const select = byId("session-select");
  const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
  state.sessions = sessions;
  select.innerHTML = "";

  for (const session of sessions) {
    const id = String(session.id ?? "").trim();
    if (!id) continue;
    const option = document.createElement("option");
    option.value = id;
    option.textContent = session.title ? `${id} · ${session.title}` : id;
    select.appendChild(option);
  }

  if (!sessions.length) {
    state.sessionId = "";
    return;
  }

  if (!state.sessionId || !sessions.some((row) => row.id === state.sessionId)) {
    state.sessionId = String(sessions[0].id);
  }
  select.value = state.sessionId;
}

async function loadMessages(sessionId) {
  if (!sessionId) {
    renderChatMessages([]);
    return;
  }
  const payload = await fetchJson(`/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages?limit=40`);
  const messages = Array.isArray(payload.messages) ? payload.messages : [];
  renderChatMessages(messages);
}

async function sendMessage(text, title = "") {
  if (!text.trim()) {
    showStatus("Message cannot be empty.", "error");
    return;
  }
  const payload = {
    session_id: state.sessionId || undefined,
    message: text.trim(),
    title,
  };
  const response = await fetchJson("/v1/chat/respond", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.sessionId = String(response.session_id ?? "");
  await loadSessions();
  await loadMessages(state.sessionId);
  if (response.assistant_text) {
    appendTimeline(`Agent reply: ${String(response.assistant_text).slice(0, 120)}`);
  } else {
    appendTimeline("Agent responded.");
  }
}

function renderBacktestDetail(run) {
  const target = byId("backtest-detail");
  const metrics = run.metrics ?? {};
  const artifacts = run.artifacts ?? {};
  const equityPath = artifacts.equity_curve_path ? `/v1/artifacts/file?path=${encodeURIComponent(artifacts.equity_curve_path)}` : "";
  const drawdownPath = artifacts.drawdown_path ? `/v1/artifacts/file?path=${encodeURIComponent(artifacts.drawdown_path)}` : "";
  target.innerHTML = `
    <h3>Run ${escapeHtml(run.run_id)}</h3>
    <div class="metric-inline">
      <span>Final Equity: <strong>${escapeHtml(metrics.final_equity ?? "-")}</strong></span>
      <span>Sharpe: <strong>${escapeHtml(metrics.sharpe ?? "-")}</strong></span>
      <span>CAGR: <strong>${escapeHtml(metrics.cagr ?? "-")}</strong></span>
      <span>Max DD: <strong>${escapeHtml(metrics.max_drawdown ?? "-")}</strong></span>
    </div>
    <div class="artifact-grid">
      ${equityPath ? `<img src="${equityPath}" alt="equity curve" />` : ""}
      ${drawdownPath ? `<img src="${drawdownPath}" alt="drawdown curve" />` : ""}
    </div>
  `;
}

async function loadBacktests() {
  const payload = await fetchJson("/v1/backtests/runs?limit=12");
  const runs = Array.isArray(payload.runs) ? payload.runs : [];
  const rows = runs.map((run) => {
    const metrics = run.metrics ?? {};
    return `<tr>
      <td>${escapeHtml(run.run_id)}</td>
      <td>${escapeHtml(run.strategy_name ?? "-")}</td>
      <td>${escapeHtml(metrics.final_equity ?? "-")}</td>
      <td>${escapeHtml(metrics.sharpe ?? "-")}</td>
      <td>${escapeHtml(metrics.cagr ?? "-")}</td>
      <td><button class="btn btn-small" data-view-backtest="${escapeHtml(run.run_id)}">View</button></td>
    </tr>`;
  });
  renderTableRows("backtests-body", rows, "No backtest runs.");
}

async function loadBacktestRunDetail(runId) {
  const run = await fetchJson(`/v1/backtests/runs/${encodeURIComponent(runId)}`);
  renderBacktestDetail(run);
}

function renderTuningDetail(detail) {
  const target = byId("tuning-detail");
  const trials = Array.isArray(detail.trials) ? detail.trials : [];
  const layers = Array.isArray(detail.layer_decisions) ? detail.layer_decisions : [];
  target.innerHTML = `
    <h3>Tuning ${escapeHtml(detail.tuning_run_id)}</h3>
    <p>Strategy: <strong>${escapeHtml(detail.strategy_name)}</strong></p>
    <p>Trials: <strong>${escapeHtml(trials.length)}</strong> · Layers: <strong>${escapeHtml(layers.length)}</strong></p>
  `;
}

async function loadTuning() {
  const payload = await fetchJson("/v1/tuning/runs?limit=12");
  const runs = Array.isArray(payload.runs) ? payload.runs : [];
  const rows = runs.map((run) => `<tr>
      <td>${escapeHtml(run.tuning_run_id)}</td>
      <td>${escapeHtml(run.strategy_name)}</td>
      <td>${escapeHtml(run.best_score ?? "-")}</td>
      <td>${escapeHtml(run.candidate_count ?? 0)}</td>
      <td><button class="btn btn-small" data-view-tuning="${escapeHtml(run.tuning_run_id)}">View</button></td>
    </tr>`);
  renderTableRows("tuning-body", rows, "No tuning runs.");
}

async function loadTuningDetail(tuningRunId) {
  const detail = await fetchJson(`/v1/tuning/runs/${encodeURIComponent(tuningRunId)}`);
  renderTuningDetail(detail);
}

async function loadLiveStates() {
  const payload = await fetchJson("/v1/live/states?limit=12");
  const rows = Array.isArray(payload.states) ? payload.states : [];
  const body = byId("live-body");
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="4" class="muted">No live states.</td></tr>';
    return;
  }
  body.innerHTML = rows.map((row) => `<tr>
      <td>${escapeHtml(row.strategy_version_id)}</td>
      <td>${escapeHtml(row.strategy_name)}</td>
      <td>${escapeHtml(row.status)}</td>
      <td>${escapeHtml(row.updated_at)}</td>
    </tr>`).join("");
}

async function loadDiagnostics() {
  const providers = await fetchJson("/v1/providers/health");
  const readiness = await fetchJson("/v1/diagnostics/readiness");
  byId("providers-health").textContent = JSON.stringify(providers, null, 2);
  byId("readiness-health").textContent = JSON.stringify(readiness, null, 2);
}

async function refreshAuditTimeline() {
  const payload = await fetchJson("/v1/audit/events?limit=20");
  const events = Array.isArray(payload.events) ? payload.events : [];
  for (const event of events) {
    const eventId = Number(event.id);
    if (state.lastAuditEventIds.has(eventId)) continue;
    state.lastAuditEventIds.add(eventId);
    appendTimeline(`audit:${event.event_type}`);
  }
  if (state.lastAuditEventIds.size > 200) {
    const sliced = [...state.lastAuditEventIds].slice(-100);
    state.lastAuditEventIds = new Set(sliced);
  }
}

function activateWorkspace(targetId) {
  for (const tab of document.querySelectorAll(".tab-btn")) {
    tab.classList.toggle("active", tab.dataset.workspaceTarget === targetId);
  }
  for (const workspace of document.querySelectorAll(".workspace")) {
    workspace.classList.toggle("active", workspace.id === targetId);
  }
}

function bindUiEvents() {
  byId("session-select").addEventListener("change", async (event) => {
    const next = event.target.value;
    state.sessionId = next;
    try {
      await loadMessages(next);
    } catch (error) {
      showStatus(String(error), "error");
    }
  });

  byId("new-session").addEventListener("click", async () => {
    state.sessionId = "";
    byId("session-select").value = "";
    byId("chat-input").focus();
    showStatus("Next message will create a new session.");
  });

  byId("chat-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = byId("chat-input");
    const message = input.value;
    input.value = "";
    try {
      await sendMessage(message);
      showStatus("Message sent.", "ok");
    } catch (error) {
      showStatus(String(error), "error");
    }
  });

  for (const button of document.querySelectorAll("#action-cards .action-card")) {
    button.addEventListener("click", async () => {
      const prompt = button.dataset.prompt ?? "";
      try {
        await sendMessage(prompt);
        showStatus("Action sent to agent.", "ok");
      } catch (error) {
        showStatus(String(error), "error");
      }
    });
  }

  byId("refresh-all").addEventListener("click", async () => {
    try {
      await refreshAll();
      showStatus("All workspaces refreshed.", "ok");
    } catch (error) {
      showStatus(String(error), "error");
    }
  });

  byId("refresh-timeline").addEventListener("click", async () => {
    try {
      await refreshAuditTimeline();
      showStatus("Timeline refreshed.", "ok");
    } catch (error) {
      showStatus(String(error), "error");
    }
  });

  byId("refresh-backtests").addEventListener("click", async () => {
    try {
      await loadBacktests();
    } catch (error) {
      showStatus(String(error), "error");
    }
  });

  byId("refresh-tuning").addEventListener("click", async () => {
    try {
      await loadTuning();
    } catch (error) {
      showStatus(String(error), "error");
    }
  });

  byId("refresh-live").addEventListener("click", async () => {
    try {
      await loadLiveStates();
    } catch (error) {
      showStatus(String(error), "error");
    }
  });

  byId("refresh-diagnostics").addEventListener("click", async () => {
    try {
      await loadDiagnostics();
    } catch (error) {
      showStatus(String(error), "error");
    }
  });

  document.addEventListener("click", async (event) => {
    const viewBacktest = event.target.closest("[data-view-backtest]");
    if (viewBacktest) {
      try {
        await loadBacktestRunDetail(viewBacktest.dataset.viewBacktest);
      } catch (error) {
        showStatus(String(error), "error");
      }
      return;
    }

    const viewTuning = event.target.closest("[data-view-tuning]");
    if (viewTuning) {
      try {
        await loadTuningDetail(viewTuning.dataset.viewTuning);
      } catch (error) {
        showStatus(String(error), "error");
      }
      return;
    }

    const tabButton = event.target.closest(".tab-btn");
    if (tabButton) {
      activateWorkspace(tabButton.dataset.workspaceTarget);
    }
  });
}

async function refreshAll() {
  await Promise.all([
    loadSessions(),
    loadBacktests(),
    loadTuning(),
    loadLiveStates(),
    loadDiagnostics(),
    refreshAuditTimeline(),
  ]);
  if (state.sessionId) {
    await loadMessages(state.sessionId);
  }
}

async function init() {
  bindUiEvents();
  try {
    await refreshAll();
    appendTimeline("UI initialized");
    showStatus("Connected.", "ok");
  } catch (error) {
    showStatus(String(error), "error");
    appendTimeline(`Initialization error: ${String(error)}`);
  }

  window.setInterval(async () => {
    try {
      await refreshAuditTimeline();
    } catch (_error) {
      // surface errors via explicit user action to avoid noisy loops
    }
  }, 15000);
}

init();

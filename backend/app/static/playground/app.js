const STORAGE_KEY = "laborlawhelp-middlend-playground";

const state = {
  runtime: null,
  lastSeq: 0,
  assistantText: "",
  finalPayload: null,
  events: [],
};

const els = {
  runtimeMeta: document.getElementById("runtimeMeta"),
  refreshRuntimeBtn: document.getElementById("refreshRuntimeBtn"),
  saveDraftBtn: document.getElementById("saveDraftBtn"),
  baseUrl: document.getElementById("baseUrl"),
  traceId: document.getElementById("traceId"),
  ownerMode: document.getElementById("ownerMode"),
  anonymousToken: document.getElementById("anonymousToken"),
  bearerToken: document.getElementById("bearerToken"),
  ownerHint: document.getElementById("ownerHint"),
  caseTitle: document.getElementById("caseTitle"),
  regionCode: document.getElementById("regionCode"),
  caseId: document.getElementById("caseId"),
  sessionId: document.getElementById("sessionId"),
  createCaseBtn: document.getElementById("createCaseBtn"),
  listCasesBtn: document.getElementById("listCasesBtn"),
  createSessionBtn: document.getElementById("createSessionBtn"),
  listSessionsBtn: document.getElementById("listSessionsBtn"),
  loadMessagesBtn: document.getElementById("loadMessagesBtn"),
  endSessionBtn: document.getElementById("endSessionBtn"),
  resourceList: document.getElementById("resourceList"),
  messageInput: document.getElementById("messageInput"),
  clientSeq: document.getElementById("clientSeq"),
  locale: document.getElementById("locale"),
  policyVersion: document.getElementById("policyVersion"),
  capabilities: document.getElementById("capabilities"),
  attachments: document.getElementById("attachments"),
  sendChatBtn: document.getElementById("sendChatBtn"),
  clearEventsBtn: document.getElementById("clearEventsBtn"),
  resetStateBtn: document.getElementById("resetStateBtn"),
  requestPreview: document.getElementById("requestPreview"),
  assistantOutput: document.getElementById("assistantOutput"),
  finalSummary: document.getElementById("finalSummary"),
  finalRefs: document.getElementById("finalRefs"),
  eventLog: document.getElementById("eventLog"),
  messageHistory: document.getElementById("messageHistory"),
  streamStatus: document.getElementById("streamStatus"),
  eventStats: document.getElementById("eventStats"),
};

function loadDraft() {
  const saved = window.localStorage.getItem(STORAGE_KEY);
  const defaults = {
    baseUrl: window.location.origin,
    traceId: "",
    ownerMode: "anonymous",
    anonymousToken: "anon-labor-debug",
    bearerToken: "",
    caseTitle: "试用期辞退联调样例",
    regionCode: "xian",
    caseId: "",
    sessionId: "",
    messageInput: "我在试用期被口头辞退，公司没有出书面通知，也没有结清工资，我该怎么取证和准备仲裁？",
    clientSeq: "1",
    locale: "zh-CN",
    policyVersion: "",
    capabilities: "citations,tool-status",
    attachments: "",
  };

  if (!saved) {
    return defaults;
  }

  try {
    return { ...defaults, ...JSON.parse(saved) };
  } catch {
    return defaults;
  }
}

function saveDraft() {
  const payload = {
    baseUrl: els.baseUrl.value.trim(),
    traceId: els.traceId.value.trim(),
    ownerMode: els.ownerMode.value,
    anonymousToken: els.anonymousToken.value.trim(),
    bearerToken: els.bearerToken.value.trim(),
    caseTitle: els.caseTitle.value.trim(),
    regionCode: els.regionCode.value.trim(),
    caseId: els.caseId.value.trim(),
    sessionId: els.sessionId.value.trim(),
    messageInput: els.messageInput.value,
    clientSeq: els.clientSeq.value,
    locale: els.locale.value.trim(),
    policyVersion: els.policyVersion.value.trim(),
    capabilities: els.capabilities.value.trim(),
    attachments: els.attachments.value.trim(),
  };

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

function hydrateDraft() {
  const draft = loadDraft();
  Object.entries(draft).forEach(([key, value]) => {
    if (els[key]) {
      els[key].value = value;
    }
  });
}

function updateOwnerHint() {
  const runtimeMode = state.runtime?.auth_mode || "unknown";
  const currentMode = els.ownerMode.value;
  const notes = [];

  notes.push(`后端当前 auth_mode: ${runtimeMode}`);
  notes.push(`页面当前将发送: ${currentMode === "jwt" ? "Authorization: Bearer <token>" : "X-Anonymous-Token"}`);

  if (runtimeMode === "jwt" && currentMode !== "jwt") {
    notes.push("当前配置可能会被后端拒绝，请切换到 Bearer token。");
  }

  if (runtimeMode === "anonymous" && currentMode === "jwt") {
    notes.push("后端允许 Bearer 优先，但匿名模式下通常也可以直接用匿名 token 联调。");
  }

  els.ownerHint.textContent = notes.join("  ");
}

function renderRuntime() {
  if (!state.runtime) {
    els.runtimeMeta.innerHTML = "<div><dt>status</dt><dd>loading...</dd></div>";
    updateOwnerHint();
    return;
  }

  const fields = [
    ["app", `${state.runtime.app_name} ${state.runtime.app_version}`],
    ["auth_mode", state.runtime.auth_mode],
    ["storage", state.runtime.storage_backend],
    ["OpenHarness", state.runtime.openharness_mode],
    ["workflow", state.runtime.workflow],
    ["fallback", String(state.runtime.local_rule_fallback)],
    ["rate_limit", `${state.runtime.rate_limit_per_minute}/min`],
    ["stream_path", state.runtime.stream_path],
  ];

  els.runtimeMeta.innerHTML = fields
    .map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`)
    .join("");

  if (state.runtime.auth_mode === "jwt") {
    els.ownerMode.value = "jwt";
  }

  updateOwnerHint();
}

function escapeHtml(input) {
  return String(input)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStreamStatus(kind, label) {
  els.streamStatus.className = `status-chip ${kind}`;
  els.streamStatus.textContent = label;
}

function updateEventStats() {
  els.eventStats.textContent = `${state.events.length} events`;
}

function appendEvent(eventName, payload) {
  state.events.unshift({
    eventName,
    payload,
    at: new Date().toLocaleTimeString("zh-CN", { hour12: false }),
  });

  renderEvents();
}

function renderEvents() {
  updateEventStats();

  if (!state.events.length) {
    els.eventLog.innerHTML = '<div class="empty-state">等待事件...</div>';
    return;
  }

  els.eventLog.innerHTML = state.events
    .map(
      (entry) => `
        <article class="event-item">
          <div class="event-head">
            <span class="event-name">${escapeHtml(entry.eventName)}</span>
            <span class="event-time">${escapeHtml(entry.at)}</span>
          </div>
          <pre class="event-payload">${escapeHtml(JSON.stringify(entry.payload, null, 2))}</pre>
        </article>
      `,
    )
    .join("");
}

function renderResources(items, type) {
  if (!items.length) {
    els.resourceList.innerHTML = `<div class="empty-state">没有可展示的 ${escapeHtml(type)}。</div>`;
    return;
  }

  els.resourceList.innerHTML = items
    .map((item) => {
      const title = type === "cases" ? item.title || item.id : item.id;
      const subline = type === "cases"
        ? `${item.id} · ${item.region_code} · ${item.status}`
        : `${item.id} · case ${item.case_id} · ${item.status}`;
      return `
        <article class="resource-item">
          <div class="event-head">
            <strong>${escapeHtml(title)}</strong>
            <span class="resource-pill">${escapeHtml(type.slice(0, -1))}</span>
          </div>
          <div>${escapeHtml(subline)}</div>
        </article>
      `;
    })
    .join("");
}

function renderAssistant() {
  if (!state.assistantText) {
    els.assistantOutput.className = "assistant-output empty-state";
    els.assistantOutput.textContent = "等待 SSE 响应...";
    return;
  }

  els.assistantOutput.className = "assistant-output";
  els.assistantOutput.textContent = state.assistantText;
}

function renderFinal() {
  if (!state.finalPayload) {
    els.finalSummary.className = "summary-card empty-state";
    els.finalSummary.textContent = "还没有收到 final 事件。";
    els.finalRefs.className = "reference-list empty-state";
    els.finalRefs.textContent = "引用信息会显示在这里。";
    return;
  }

  const summaryLines = [
    state.finalPayload.summary || "summary 为空",
    `message_id: ${state.finalPayload.message_id || "-"}`,
    `rule_version: ${state.finalPayload.rule_version || "-"}`,
    `finish_reason: ${state.finalPayload.finish_reason || "-"}`,
    `trace_id: ${state.finalPayload.trace_id || "-"}`,
  ];

  els.finalSummary.className = "summary-card";
  els.finalSummary.innerHTML = summaryLines.map((line) => `<div>${escapeHtml(line)}</div>`).join("");

  const references = Array.isArray(state.finalPayload.references) ? state.finalPayload.references : [];
  if (!references.length) {
    els.finalRefs.className = "reference-list empty-state";
    els.finalRefs.textContent = "本次 final 没有返回 references。";
    return;
  }

  els.finalRefs.className = "reference-list";
  els.finalRefs.innerHTML = references
    .map((ref, index) => {
      const title = ref.title || `reference-${index + 1}`;
      const url = ref.url ? `<a href="${escapeHtml(ref.url)}" target="_blank" rel="noreferrer">${escapeHtml(ref.url)}</a>` : "无 URL";
      const snippet = ref.snippet ? `<div>${escapeHtml(ref.snippet)}</div>` : "";
      return `
        <article class="reference-item">
          <strong>${escapeHtml(title)}</strong>
          <div>${url}</div>
          ${snippet}
        </article>
      `;
    })
    .join("");
}

function renderMessages(messages) {
  if (!messages.length) {
    els.messageHistory.innerHTML = '<div class="empty-state">当前 session 还没有消息。</div>';
    return;
  }

  els.messageHistory.innerHTML = messages
    .map((item) => {
      const createdAt = item.created_at || "-";
      return `
        <article class="history-item">
          <div class="event-head">
            <span class="history-role ${escapeHtml(item.role)}">${escapeHtml(item.role)}</span>
            <span class="event-time">${escapeHtml(createdAt)}</span>
          </div>
          <pre class="history-body">${escapeHtml(item.content || "")}</pre>
        </article>
      `;
    })
    .join("");
}

function buildHeaders() {
  const headers = { "Content-Type": "application/json" };
  const traceId = els.traceId.value.trim();
  if (traceId) {
    headers["X-Trace-Id"] = traceId;
  }

  if (els.ownerMode.value === "jwt") {
    const token = els.bearerToken.value.trim();
    if (!token) {
      throw new Error("当前选择了 Bearer token，但 token 为空。");
    }
    headers.Authorization = `Bearer ${token}`;
  } else {
    const token = els.anonymousToken.value.trim();
    if (!token) {
      throw new Error("请填写匿名 token。");
    }
    headers["X-Anonymous-Token"] = token;
  }

  return headers;
}

function getBaseUrl() {
  const value = els.baseUrl.value.trim();
  return value || window.location.origin;
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${getBaseUrl()}${path}`, options);
  const rawText = await response.text();
  let payload = null;

  try {
    payload = rawText ? JSON.parse(rawText) : null;
  } catch {
    payload = rawText;
  }

  if (!response.ok) {
    const message = typeof payload === "object" && payload?.message
      ? payload.message
      : `request failed: ${response.status}`;
    throw new Error(message);
  }

  return payload;
}

function parseAttachments() {
  const raw = els.attachments.value.trim();
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      throw new Error("附件 JSON 必须是数组。");
    }
    return parsed;
  } catch (error) {
    throw new Error(`附件 JSON 解析失败: ${error.message}`);
  }
}

function buildChatPayload() {
  const payload = {
    message: els.messageInput.value.trim(),
    client_seq: Number(els.clientSeq.value || "1"),
    attachments: parseAttachments(),
  };

  if (!payload.message) {
    throw new Error("message 不能为空。");
  }

  const locale = els.locale.value.trim();
  const policyVersion = els.policyVersion.value.trim();
  const capabilities = els.capabilities.value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  if (locale) {
    payload.locale = locale;
  }
  if (policyVersion) {
    payload.policy_version = policyVersion;
  }
  if (capabilities.length) {
    payload.client_capabilities = capabilities;
  }

  return payload;
}

function resetStreamView() {
  state.lastSeq = 0;
  state.assistantText = "";
  state.finalPayload = null;
  renderAssistant();
  renderFinal();
}

function notify(message, level = "idle") {
  setStreamStatus(level, message);
}

function showRequestPreview(payload, endpoint) {
  els.requestPreview.className = "request-preview";
  els.requestPreview.textContent = JSON.stringify(
    {
      endpoint,
      headers: buildHeaders(),
      body: payload,
    },
    null,
    2,
  );
}

async function loadRuntime() {
  try {
    state.runtime = await requestJson("/api/v1/playground/runtime");
    renderRuntime();
    notify("Runtime ready", "idle");
  } catch (error) {
    state.runtime = null;
    renderRuntime();
    notify(`Runtime load failed: ${error.message}`, "error");
  }
}

async function createCase() {
  const payload = {
    title: els.caseTitle.value.trim() || "未命名案件",
    region_code: els.regionCode.value.trim() || "xian",
  };

  const result = await requestJson("/api/v1/cases", {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });

  els.caseId.value = result.id;
  saveDraft();
  appendEvent("case_created", result);
  notify("Case created", "success");
  return result;
}

async function listCases() {
  const result = await requestJson("/api/v1/cases", {
    headers: buildHeaders(),
  });
  renderResources(result, "cases");
  appendEvent("cases_loaded", { count: result.length });
  notify("Cases loaded", "success");
}

async function createSession() {
  const caseId = els.caseId.value.trim();
  if (!caseId) {
    throw new Error("请先创建或填入 case_id。");
  }

  const result = await requestJson(`/api/v1/cases/${encodeURIComponent(caseId)}/sessions`, {
    method: "POST",
    headers: buildHeaders(),
  });

  els.sessionId.value = result.id;
  saveDraft();
  appendEvent("session_created", result);
  notify("Session created", "success");
  return result;
}

async function listSessions() {
  const caseId = els.caseId.value.trim();
  if (!caseId) {
    throw new Error("请先填入 case_id。");
  }

  const result = await requestJson(`/api/v1/cases/${encodeURIComponent(caseId)}/sessions`, {
    headers: buildHeaders(),
  });
  renderResources(result, "sessions");
  appendEvent("sessions_loaded", { case_id: caseId, count: result.length });
  notify("Sessions loaded", "success");
}

async function loadMessages() {
  const sessionId = els.sessionId.value.trim();
  if (!sessionId) {
    throw new Error("请先填入 session_id。");
  }

  const result = await requestJson(`/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`, {
    headers: buildHeaders(),
  });
  renderMessages(result);
  appendEvent("messages_loaded", { session_id: sessionId, count: result.length });
  notify("Messages loaded", "success");
}

async function endSession() {
  const sessionId = els.sessionId.value.trim();
  if (!sessionId) {
    throw new Error("请先填入 session_id。");
  }

  const result = await requestJson(`/api/v1/sessions/${encodeURIComponent(sessionId)}/end`, {
    method: "PATCH",
    headers: buildHeaders(),
  });
  appendEvent("session_ended", result);
  notify("Session ended", "success");
}

function handleSseEvent(eventName, data) {
  appendEvent(eventName, data);

  if (eventName === "message_start") {
    resetStreamView();
    setStreamStatus("live", "Streaming");
    return;
  }

  if (eventName === "content_delta") {
    const seq = Number(data.seq || 0);
    if (seq > state.lastSeq) {
      state.lastSeq = seq;
      state.assistantText += data.delta || "";
      renderAssistant();
    }
    return;
  }

  if (eventName === "final") {
    state.finalPayload = data;
    renderFinal();
    setStreamStatus("success", "Final received");
    return;
  }

  if (eventName === "error") {
    setStreamStatus("error", data.code || "Stream error");
    if (data.message) {
      state.assistantText = state.assistantText || `[error] ${data.message}`;
      renderAssistant();
    }
    return;
  }

  if (eventName === "message_end") {
    if (!state.finalPayload) {
      setStreamStatus("idle", "Message ended");
    }
  }
}

async function streamChat() {
  const sessionId = els.sessionId.value.trim();
  if (!sessionId) {
    throw new Error("请先创建或填入 session_id。");
  }

  const payload = buildChatPayload();
  showRequestPreview(payload, `/api/v1/sessions/${sessionId}/chat/stream`);
  resetStreamView();
  setStreamStatus("live", "Streaming");

  const response = await fetch(`${getBaseUrl()}/api/v1/sessions/${encodeURIComponent(sessionId)}/chat/stream`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    const raw = await response.text();
    let message = `chat request failed: ${response.status}`;
    try {
      const parsed = JSON.parse(raw);
      message = parsed.message || parsed.code || message;
    } catch {
      if (raw) {
        message = raw;
      }
    }
    throw new Error(message);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";

    for (const frame of frames) {
      const lines = frame.split("\n").filter(Boolean);
      const eventLine = lines.find((line) => line.startsWith("event:"));
      const dataLines = lines.filter((line) => line.startsWith("data:"));
      if (!eventLine || !dataLines.length) {
        continue;
      }

      const eventName = eventLine.slice(6).trim();
      const dataText = dataLines.map((line) => line.slice(5).trim()).join("\n");
      let parsed = {};
      try {
        parsed = JSON.parse(dataText);
      } catch {
        parsed = { raw: dataText };
      }
      handleSseEvent(eventName, parsed);
    }
  }

  els.clientSeq.value = String(Number(payload.client_seq) + 1);
  saveDraft();
}

function clearEvents() {
  state.events = [];
  renderEvents();
}

function resetState() {
  clearEvents();
  resetStreamView();
  renderMessages([]);
  renderResources([], "cases");
  els.requestPreview.className = "request-preview empty-state";
  els.requestPreview.textContent = "发送前请求体会显示在这里。";
  notify("State reset", "idle");
}

async function safeAction(action) {
  try {
    saveDraft();
    await action();
  } catch (error) {
    appendEvent("ui_error", { message: error.message });
    notify(error.message, "error");
  }
}

function bindEvents() {
  els.refreshRuntimeBtn.addEventListener("click", () => safeAction(loadRuntime));
  els.saveDraftBtn.addEventListener("click", () => {
    saveDraft();
    notify("Draft saved", "success");
  });
  els.ownerMode.addEventListener("change", updateOwnerHint);
  els.createCaseBtn.addEventListener("click", () => safeAction(createCase));
  els.listCasesBtn.addEventListener("click", () => safeAction(listCases));
  els.createSessionBtn.addEventListener("click", () => safeAction(createSession));
  els.listSessionsBtn.addEventListener("click", () => safeAction(listSessions));
  els.loadMessagesBtn.addEventListener("click", () => safeAction(loadMessages));
  els.endSessionBtn.addEventListener("click", () => safeAction(endSession));
  els.sendChatBtn.addEventListener("click", () => safeAction(streamChat));
  els.clearEventsBtn.addEventListener("click", clearEvents);
  els.resetStateBtn.addEventListener("click", resetState);

  [
    "baseUrl",
    "traceId",
    "ownerMode",
    "anonymousToken",
    "bearerToken",
    "caseTitle",
    "regionCode",
    "caseId",
    "sessionId",
    "messageInput",
    "clientSeq",
    "locale",
    "policyVersion",
    "capabilities",
    "attachments",
  ].forEach((key) => {
    els[key].addEventListener("change", saveDraft);
    els[key].addEventListener("blur", saveDraft);
  });
}

async function bootstrap() {
  hydrateDraft();
  renderRuntime();
  renderAssistant();
  renderFinal();
  renderEvents();
  renderMessages([]);
  bindEvents();
  await loadRuntime();
}

bootstrap();

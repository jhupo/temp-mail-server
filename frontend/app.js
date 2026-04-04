const STORE_KEY = "tempmail_ui_v2";
const state = {
  apiKey: "",
  domain: "temp.jhupo.com",
  ttl: 60,
  current: null,
  mailboxes: [],
  autoTimer: null,
};

const el = {
  loginPanel: document.getElementById("loginPanel"),
  appPanel: document.getElementById("appPanel"),
  apiKeyInput: document.getElementById("apiKeyInput"),
  domainInput: document.getElementById("domainInput"),
  ttlInput: document.getElementById("ttlInput"),
  enterBtn: document.getElementById("enterBtn"),
  loginMsg: document.getElementById("loginMsg"),
  newMailboxBtn: document.getElementById("newMailboxBtn"),
  refreshInboxBtn: document.getElementById("refreshInboxBtn"),
  extractCodeBtn: document.getElementById("extractCodeBtn"),
  copyAddressBtn: document.getElementById("copyAddressBtn"),
  copyTokenBtn: document.getElementById("copyTokenBtn"),
  autoRefreshToggle: document.getElementById("autoRefreshToggle"),
  currentAddress: document.getElementById("currentAddress"),
  currentExpiry: document.getElementById("currentExpiry"),
  latestCode: document.getElementById("latestCode"),
  mailboxList: document.getElementById("mailboxList"),
  messageList: document.getElementById("messageList"),
};

function toLocalTime(v) {
  if (!v) return "-";
  const dt = new Date(v);
  return Number.isNaN(dt.getTime()) ? v : dt.toLocaleString();
}

function saveState() {
  localStorage.setItem(
    STORE_KEY,
    JSON.stringify({
      apiKey: state.apiKey,
      domain: state.domain,
      ttl: state.ttl,
      current: state.current,
      mailboxes: state.mailboxes,
    })
  );
}

function loadState() {
  const raw = localStorage.getItem(STORE_KEY);
  if (!raw) return;
  try {
    const v = JSON.parse(raw);
    state.apiKey = v.apiKey || "";
    state.domain = v.domain || "temp.jhupo.com";
    state.ttl = v.ttl || 60;
    state.current = v.current || null;
    state.mailboxes = Array.isArray(v.mailboxes) ? v.mailboxes : [];
  } catch (_err) {
    // ignore
  }
}

function applyFormFromState() {
  el.apiKeyInput.value = state.apiKey;
  el.domainInput.value = state.domain;
  el.ttlInput.value = state.ttl;
}

function setCurrent(mailbox) {
  state.current = mailbox;
  state.mailboxes = [mailbox, ...state.mailboxes.filter((m) => m.address !== mailbox.address)].slice(0, 40);
  saveState();
  renderCurrent();
  renderMailboxList();
}

function renderCurrent() {
  el.currentAddress.textContent = state.current?.address || "-";
  el.currentExpiry.textContent = toLocalTime(state.current?.expires_at);
}

function renderMailboxList() {
  el.mailboxList.innerHTML = "";
  if (!state.mailboxes.length) {
    el.mailboxList.innerHTML = '<p class="sub">暂无邮箱，先新建一个。</p>';
    return;
  }
  for (const mb of state.mailboxes) {
    const item = document.createElement("div");
    item.className = `mailbox-item${state.current?.address === mb.address ? " active" : ""}`;
    item.innerHTML = `<strong>${mb.address}</strong><small>过期: ${toLocalTime(mb.expires_at)}</small>`;
    item.addEventListener("click", () => {
      setCurrent(mb);
      refreshInbox();
    });
    el.mailboxList.appendChild(item);
  }
}

function renderMessages(messages) {
  el.messageList.innerHTML = "";
  if (!messages.length) {
    el.messageList.innerHTML = '<p class="sub">收件箱为空，点击刷新等待邮件。</p>';
    return;
  }
  for (const m of messages) {
    const card = document.createElement("article");
    card.className = "message-item";
    card.innerHTML = `
      <div class="message-meta">
        <div><strong>From:</strong> ${m.from_addr || "-"}</div>
        <div><strong>Subject:</strong> ${m.subject || "-"}</div>
        <div><strong>Time:</strong> ${toLocalTime(m.received_at)}</div>
      </div>
      <div class="message-body">${escapeHtml(m.text_body || "(no text body)")}</div>
    `;
    el.messageList.appendChild(card);
  }
}

function escapeHtml(s) {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function api(path, { method = "GET", body = null } = {}) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (state.apiKey) headers["X-API-Key"] = state.apiKey;
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : null });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "request failed");
  return data;
}

async function createRandomMailbox() {
  state.apiKey = el.apiKeyInput.value.trim();
  state.domain = el.domainInput.value.trim() || "temp.jhupo.com";
  state.ttl = Number(el.ttlInput.value || "60");
  saveState();
  const data = await api("/api/v1/mailboxes/new", {
    method: "POST",
    body: { domain: state.domain, ttl_minutes: state.ttl },
  });
  setCurrent(data);
  showApp();
  await refreshInbox();
}

async function refreshInbox() {
  if (!state.current) return;
  const q = `token=${encodeURIComponent(state.current.token)}&limit=20`;
  const data = await api(`/api/v1/mailboxes/${encodeURIComponent(state.current.address)}/messages?${q}`);
  renderMessages(data.messages || []);
}

async function extractCode() {
  if (!state.current) return;
  const q = `token=${encodeURIComponent(state.current.token)}`;
  const data = await api(`/api/v1/mailboxes/${encodeURIComponent(state.current.address)}/latest/code?${q}`);
  el.latestCode.textContent = data.code || "-";
}

function showApp() {
  el.loginPanel.classList.add("hidden");
  el.appPanel.classList.remove("hidden");
}

function startAutoRefresh() {
  stopAutoRefresh();
  if (!el.autoRefreshToggle.checked) return;
  state.autoTimer = setInterval(async () => {
    try {
      await refreshInbox();
      await extractCode();
    } catch (_err) {
      // keep silent in auto mode
    }
  }, 8000);
}

function stopAutoRefresh() {
  if (!state.autoTimer) return;
  clearInterval(state.autoTimer);
  state.autoTimer = null;
}

async function initSession() {
  loadState();
  applyFormFromState();
  renderMailboxList();
  renderCurrent();

  if (state.current) {
    showApp();
    try {
      await refreshInbox();
      await extractCode();
    } catch (_err) {
      // token expired or mailbox missing
    }
  }
  startAutoRefresh();
}

el.enterBtn.addEventListener("click", async () => {
  el.loginMsg.textContent = "创建中...";
  try {
    await createRandomMailbox();
    el.loginMsg.textContent = "进入成功";
  } catch (err) {
    el.loginMsg.textContent = err.message;
  }
});

el.newMailboxBtn.addEventListener("click", async () => {
  try {
    await createRandomMailbox();
  } catch (err) {
    alert(err.message);
  }
});

el.refreshInboxBtn.addEventListener("click", () => refreshInbox().catch((err) => alert(err.message)));
el.extractCodeBtn.addEventListener("click", () => extractCode().catch((err) => alert(err.message)));
el.autoRefreshToggle.addEventListener("change", startAutoRefresh);

el.copyAddressBtn.addEventListener("click", () => {
  if (state.current?.address) navigator.clipboard.writeText(state.current.address).catch(() => {});
});
el.copyTokenBtn.addEventListener("click", () => {
  if (state.current?.token) navigator.clipboard.writeText(state.current.token).catch(() => {});
});

initSession().catch((err) => {
  console.error(err);
});

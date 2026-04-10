<template>
  <el-container class="layout">
    <el-aside class="sidebar" :width="isMobile ? '100%' : '320px'" v-show="showSidebar">
      <div class="brand">
        <div>
          <div class="title">Temp Mail</div>
          <div class="desc">Cloud Mail UI adapted for this backend</div>
        </div>
        <el-switch
          v-model="darkMode"
          inline-prompt
          active-text="暗"
          inactive-text="亮"
          @change="applyTheme"
        />
      </div>

      <el-card shadow="never" class="panel create-panel">
        <template #header>
          <div class="panel-header">
            <span>创建邮箱</span>
            <el-button text @click="createRandomMailbox" :loading="creating">随机</el-button>
          </div>
        </template>

        <el-form label-position="top" @submit.prevent>
          <el-form-item label="域名">
            <el-select v-model="createForm.domain" placeholder="选择域名">
              <el-option
                v-for="domain in availableDomains"
                :key="domain"
                :label="domain"
                :value="domain"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="用户名">
            <el-input v-model="createForm.localPart" placeholder="留空则随机生成" />
          </el-form-item>

          <el-form-item label="管理员密钥">
            <el-input
              v-model="settings.adminKey"
              type="password"
              show-password
              placeholder="需要自定义域名/用户名时填写"
            />
          </el-form-item>

          <el-form-item label="默认域名列表">
            <el-input
              v-model="settings.domainInput"
              placeholder="alpha.test,beta.test"
              @blur="persistSettings"
            />
          </el-form-item>

          <el-form-item label="API 地址">
            <el-input v-model="settings.baseUrl" placeholder="默认同源" @blur="persistSettings" />
          </el-form-item>

          <el-button type="primary" class="full" :loading="creating" @click="createMailbox">
            创建邮箱
          </el-button>
        </el-form>
      </el-card>

      <el-card shadow="never" class="panel mailbox-panel">
        <template #header>
          <div class="panel-header">
            <span>邮箱列表</span>
            <el-button text @click="refreshSelected" :disabled="!selectedMailbox">刷新</el-button>
          </div>
        </template>

        <div v-if="mailboxes.length === 0" class="empty-hint">还没有保存的邮箱</div>
        <div
          v-for="mailbox in mailboxes"
          :key="mailbox.token"
          class="mailbox-item"
          :class="{ active: selectedMailbox?.token === mailbox.token }"
          @click="selectMailbox(mailbox)"
        >
          <div class="mailbox-line">
            <span class="mailbox-address">{{ mailbox.address }}</span>
            <el-tag size="small" type="info">{{ mailbox.domain }}</el-tag>
          </div>
          <div class="mailbox-meta">
            <span>到期 {{ formatDate(mailbox.expires_at) }}</span>
            <el-button text type="danger" @click.stop="removeMailbox(mailbox.token)">删除</el-button>
          </div>
        </div>
      </el-card>
    </el-aside>

    <el-container class="main-container">
      <el-header class="topbar">
        <div class="topbar-left">
          <el-button class="mobile-only" text @click="showSidebar = !showSidebar">
            <el-icon><Menu /></el-icon>
          </el-button>
          <div>
            <div class="title">{{ selectedMailbox?.address || "选择或创建一个邮箱" }}</div>
            <div class="desc">{{ statusText }}</div>
          </div>
        </div>
        <div class="topbar-actions">
          <el-input-number
            v-model="settings.pollSeconds"
            :min="3"
            :max="60"
            size="small"
            @change="persistSettings"
          />
          <span class="poll-label">秒轮询</span>
          <el-button @click="refreshSelected" :disabled="!selectedMailbox" :loading="loadingMessages">
            拉取邮件
          </el-button>
        </div>
      </el-header>

      <el-main class="content-shell">
        <div class="message-layout">
          <div class="message-list-wrap">
            <div class="section-header">
              <span>邮件列表</span>
              <el-tag type="info">{{ messages.length }}</el-tag>
            </div>

            <el-scrollbar class="message-scroll">
              <div v-if="messages.length === 0" class="empty-state">
                {{ selectedMailbox ? "暂时没有邮件" : "先在左侧创建或选择邮箱" }}
              </div>
              <div
                v-for="message in messages"
                :key="message.mail_id"
                class="message-item"
                :class="{ active: selectedMessage?.mail_id === message.mail_id }"
                @click="selectMessage(message)"
              >
                <div class="message-top">
                  <span class="message-from">{{ message.from || "(unknown)" }}</span>
                  <span class="message-time">{{ formatDate(message.created_at) }}</span>
                </div>
                <div class="message-subject">{{ message.subject || "(no subject)" }}</div>
                <div class="message-preview">{{ previewText(message) }}</div>
              </div>
            </el-scrollbar>
          </div>

          <div class="message-detail-wrap">
            <div class="section-header">
              <span>邮件详情</span>
              <el-button
                text
                :disabled="!selectedMessage || loadingMessageDetail"
                @click="loadMessageDetail(selectedMessage.mail_id, true)"
              >
                刷新详情
              </el-button>
            </div>

            <div v-if="!selectedMessage" class="empty-state">选择一封邮件查看内容</div>
            <div v-else class="detail-card">
              <div class="detail-header">
                <div class="detail-subject">{{ selectedMessage.subject || "(no subject)" }}</div>
                <div class="detail-meta">
                  <div><strong>发件人：</strong>{{ selectedMessage.from || "(unknown)" }}</div>
                  <div><strong>地址：</strong>{{ selectedMailbox?.address }}</div>
                  <div><strong>时间：</strong>{{ formatDate(selectedMessage.created_at) }}</div>
                </div>
              </div>

              <el-tabs v-model="detailTab" class="detail-tabs">
                <el-tab-pane label="HTML" name="html">
                  <iframe
                    v-if="selectedMessage.html"
                    class="html-frame"
                    :srcdoc="selectedMessage.html"
                    sandbox=""
                  />
                  <div v-else class="empty-state small">这封邮件没有 HTML 内容</div>
                </el-tab-pane>
                <el-tab-pane label="Text" name="text">
                  <pre class="text-body">{{ selectedMessage.text || selectedMessage.body || "" }}</pre>
                </el-tab-pane>
                <el-tab-pane label="Raw" name="raw">
                  <pre class="text-body">{{ selectedMessage.raw || "" }}</pre>
                </el-tab-pane>
              </el-tabs>
            </div>
          </div>
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import dayjs from "dayjs";
import axios from "axios";

const storageKeys = {
  mailboxes: "temp-mail-ui.mailboxes",
  settings: "temp-mail-ui.settings",
  darkMode: "temp-mail-ui.darkMode"
};

const savedSettings = safeJsonParse(localStorage.getItem(storageKeys.settings), {});
const savedMailboxes = safeJsonParse(localStorage.getItem(storageKeys.mailboxes), []);

const settings = reactive({
  baseUrl: savedSettings.baseUrl || "",
  adminKey: savedSettings.adminKey || "",
  domainInput: savedSettings.domainInput || "jhupo.com",
  pollSeconds: Number(savedSettings.pollSeconds || 10)
});

const mailboxes = ref(savedMailboxes);
const selectedMailbox = ref(mailboxes.value[0] || null);
const messages = ref([]);
const selectedMessage = ref(null);
const creating = ref(false);
const loadingMessages = ref(false);
const loadingMessageDetail = ref(false);
const showSidebar = ref(window.innerWidth > 1024);
const isMobile = ref(window.innerWidth <= 1024);
const detailTab = ref("html");
const darkMode = ref(localStorage.getItem(storageKeys.darkMode) === "1");

const createForm = reactive({
  domain: "",
  localPart: ""
});

const availableDomains = computed(() => {
  return settings.domainInput
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
});

const statusText = computed(() => {
  if (!selectedMailbox.value) {
    return "当前没有选中的邮箱";
  }
  return `轮询间隔 ${settings.pollSeconds} 秒`;
});

let pollTimer = null;

const api = computed(() => {
  return axios.create({
    baseURL: settings.baseUrl || "",
    timeout: 30000
  });
});

watch(
  availableDomains,
  (domains) => {
    if (!createForm.domain || !domains.includes(createForm.domain)) {
      createForm.domain = domains[0] || "";
    }
  },
  { immediate: true }
);

watch(
  selectedMailbox,
  async (value) => {
    if (!value) {
      messages.value = [];
      selectedMessage.value = null;
      return;
    }
    persistMailboxes();
    await refreshSelected();
  },
  { immediate: true }
);

watch(
  () => settings.pollSeconds,
  () => {
    persistSettings();
    restartPolling();
  }
);

watch(
  () => settings.baseUrl,
  () => {
    persistSettings();
  }
);

watch(
  () => settings.adminKey,
  () => {
    persistSettings();
  }
);

watch(
  () => settings.domainInput,
  () => {
    persistSettings();
  }
);

onMounted(() => {
  applyTheme();
  restartPolling();
  window.addEventListener("resize", handleResize);
});

onBeforeUnmount(() => {
  stopPolling();
  window.removeEventListener("resize", handleResize);
});

function handleResize() {
  isMobile.value = window.innerWidth <= 1024;
  if (!isMobile.value) {
    showSidebar.value = true;
  }
}

function applyTheme() {
  document.documentElement.classList.toggle("dark", darkMode.value);
  localStorage.setItem(storageKeys.darkMode, darkMode.value ? "1" : "0");
}

function persistSettings() {
  localStorage.setItem(storageKeys.settings, JSON.stringify(settings));
}

function persistMailboxes() {
  localStorage.setItem(storageKeys.mailboxes, JSON.stringify(mailboxes.value));
}

function safeJsonParse(value, fallback) {
  try {
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}

function formatDate(value) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function previewText(message) {
  return message.text || message.body || stripHtml(message.html || "") || "(empty)";
}

function stripHtml(html) {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function upsertMailbox(mailbox) {
  const existingIndex = mailboxes.value.findIndex((item) => item.token === mailbox.token);
  if (existingIndex >= 0) {
    mailboxes.value.splice(existingIndex, 1, mailbox);
  } else {
    mailboxes.value.unshift(mailbox);
  }
  persistMailboxes();
}

function removeMailbox(token) {
  mailboxes.value = mailboxes.value.filter((item) => item.token !== token);
  if (selectedMailbox.value?.token === token) {
    selectedMailbox.value = mailboxes.value[0] || null;
  }
  persistMailboxes();
}

function selectMailbox(mailbox) {
  selectedMailbox.value = mailbox;
  if (isMobile.value) {
    showSidebar.value = false;
  }
}

function selectMessage(message) {
  selectedMessage.value = message;
  detailTab.value = message.html ? "html" : "text";
  if (!message.raw || !message.text) {
    loadMessageDetail(message.mail_id, true);
  }
}

async function createRandomMailbox() {
  createForm.localPart = "";
  await createMailbox();
}

async function createMailbox() {
  creating.value = true;
  try {
    let mailbox;
    if (settings.adminKey && (createForm.localPart || createForm.domain !== availableDomains.value[0])) {
      const response = await api.value.post(
        "/admin/new_address",
        {
          name: createForm.localPart || undefined,
          domain: createForm.domain || availableDomains.value[0]
        },
        {
          headers: {
            "x-admin-auth": settings.adminKey
          }
        }
      );
      mailbox = normalizeMailboxResponse(response.data);
    } else {
      const response = await api.value.post("/inbox/create");
      mailbox = normalizeMailboxResponse(response.data);
    }

    upsertMailbox(mailbox);
    selectedMailbox.value = mailbox;
    createForm.localPart = "";
    ElMessage.success(`已创建 ${mailbox.address}`);
  } catch (error) {
    ElMessage.error(extractError(error));
  } finally {
    creating.value = false;
  }
}

function normalizeMailboxResponse(data) {
  const address = data.address;
  return {
    address,
    token: data.token || data.jwt,
    expires_at: data.expires_at,
    domain: address.split("@")[1]
  };
}

async function refreshSelected() {
  if (!selectedMailbox.value) {
    return;
  }
  loadingMessages.value = true;
  try {
    const response = await api.value.get("/user_api/mails", {
      headers: {
        "x-user-token": selectedMailbox.value.token
      }
    });
    messages.value = response.data.results || [];
    if (selectedMessage.value) {
      const refreshed = messages.value.find((item) => item.mail_id === selectedMessage.value.mail_id);
      if (refreshed) {
        selectedMessage.value = { ...selectedMessage.value, ...refreshed };
      }
    }
  } catch (error) {
    ElMessage.error(extractError(error));
  } finally {
    loadingMessages.value = false;
  }
}

async function loadMessageDetail(mailId, silent = false) {
  if (!selectedMailbox.value || !mailId) {
    return;
  }
  loadingMessageDetail.value = true;
  try {
    const response = await api.value.get(`/user_api/mails/${mailId}`, {
      headers: {
        "x-user-token": selectedMailbox.value.token
      }
    });
    selectedMessage.value = response.data;
  } catch (error) {
    if (!silent) {
      ElMessage.error(extractError(error));
    }
  } finally {
    loadingMessageDetail.value = false;
  }
}

function restartPolling() {
  stopPolling();
  pollTimer = window.setInterval(async () => {
    if (!selectedMailbox.value) {
      return;
    }
    await refreshSelected();
  }, Math.max(Number(settings.pollSeconds) || 10, 3) * 1000);
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

function extractError(error) {
  return error?.response?.data?.detail || error?.message || "请求失败";
}
</script>

<style scoped>
.layout {
  height: 100%;
  position: fixed;
  inset: 0;
}

.sidebar {
  background: var(--el-bg-color);
  border-right: 1px solid var(--el-border-color);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.brand,
.panel-header,
.mailbox-line,
.mailbox-meta,
.topbar,
.topbar-left,
.topbar-actions,
.message-top,
.section-header {
  display: flex;
  align-items: center;
}

.brand,
.panel-header,
.mailbox-meta,
.topbar,
.section-header {
  justify-content: space-between;
}

.brand {
  gap: 12px;
}

.title {
  font-size: 18px;
  font-weight: 700;
}

.desc {
  color: var(--secondary-text-color);
  font-size: 12px;
}

.panel {
  border: 1px solid var(--el-border-color);
}

.create-panel {
  flex: 0 0 auto;
}

.mailbox-panel {
  min-height: 0;
  flex: 1 1 auto;
}

.full {
  width: 100%;
}

.mailbox-item {
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--light-border-color);
  margin-bottom: 10px;
  cursor: pointer;
  transition: 0.15s ease;
}

.mailbox-item:hover,
.message-item:hover {
  background: var(--email-hover-background);
}

.mailbox-item.active,
.message-item.active {
  background: var(--choose-account-background);
  border-color: var(--el-color-primary-light-5);
}

.mailbox-line {
  gap: 8px;
  justify-content: space-between;
  margin-bottom: 6px;
}

.mailbox-address {
  font-weight: 600;
  word-break: break-all;
}

.mailbox-meta {
  gap: 10px;
  color: var(--secondary-text-color);
  font-size: 12px;
}

.main-container {
  background: var(--el-bg-color);
}

.topbar {
  height: 64px;
  padding: 0 20px;
  border-bottom: 1px solid var(--el-border-color);
  gap: 16px;
}

.topbar-left {
  gap: 12px;
}

.topbar-actions {
  gap: 8px;
}

.poll-label {
  color: var(--secondary-text-color);
  font-size: 12px;
}

.content-shell {
  padding: 0;
  height: calc(100vh - 64px);
}

.message-layout {
  display: grid;
  grid-template-columns: 380px minmax(0, 1fr);
  height: 100%;
}

.message-list-wrap,
.message-detail-wrap {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.message-list-wrap {
  border-right: 1px solid var(--el-border-color);
}

.section-header {
  height: 52px;
  padding: 0 16px;
  border-bottom: 1px solid var(--el-border-color);
  font-weight: 600;
}

.message-scroll {
  height: calc(100% - 52px);
}

.message-item {
  padding: 14px 16px;
  border-bottom: 1px solid var(--light-border-color);
  cursor: pointer;
}

.message-top {
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}

.message-from,
.message-subject {
  font-weight: 600;
}

.message-time,
.message-preview {
  color: var(--secondary-text-color);
}

.message-preview,
.message-subject,
.message-from {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: calc(100% - 52px);
}

.detail-header {
  padding: 18px 20px 12px;
  border-bottom: 1px solid var(--el-border-color);
}

.detail-subject {
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 10px;
}

.detail-meta {
  display: grid;
  gap: 6px;
  color: var(--regular-text-color);
}

.detail-tabs {
  min-height: 0;
  height: 100%;
  padding: 0 20px 20px;
}

.html-frame {
  width: 100%;
  min-height: 520px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: #fff;
}

.text-body {
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--light-ill);
  border-radius: 8px;
  padding: 16px;
  min-height: 300px;
}

.empty-state,
.empty-hint {
  padding: 24px;
  color: var(--secondary-text-color);
}

.empty-state.small {
  padding: 16px 0;
}

.mobile-only {
  display: none;
}

@media (max-width: 1024px) {
  .mobile-only {
    display: inline-flex;
  }

  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 100;
    width: min(100%, 360px);
    box-shadow: var(--aside-right-border);
  }

  .topbar {
    padding: 0 12px;
    height: auto;
    min-height: 64px;
    align-items: flex-start;
    padding-top: 10px;
    padding-bottom: 10px;
    flex-direction: column;
  }

  .message-layout {
    grid-template-columns: 1fr;
    grid-template-rows: 40% 60%;
  }

  .message-list-wrap {
    border-right: none;
    border-bottom: 1px solid var(--el-border-color);
  }

  .html-frame {
    min-height: 320px;
  }
}
</style>

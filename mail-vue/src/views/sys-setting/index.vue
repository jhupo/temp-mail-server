<template>
  <div class="settings-page" v-loading="loading">
    <div class="grid" v-if="!loading">
      <section class="card">
        <div class="card-title">{{ $t('websiteSetting') }}</div>
        <div class="card-body">
          <label class="row">
            <span>{{ $t('websiteTitle') }}</span>
            <div class="inline">
              <el-input v-model="titleInput" />
              <el-button type="primary" @click="saveTitle" :loading="saving">{{ $t('save') }}</el-button>
            </div>
          </label>

          <label class="row">
            <span>{{ $t('websiteReg') }}</span>
            <el-switch :model-value="setting.register === 0" @change="val => saveSwitch('register', val)" />
          </label>

          <label class="row">
            <span>{{ $t('loginDomain') }}</span>
            <el-switch :model-value="setting.loginDomain === 0" @change="val => saveSwitch('loginDomain', val)" />
          </label>

          <label class="row">
            <span>{{ $t('regKey') }}</span>
            <el-select :model-value="setting.regKey" @change="val => savePatch({ regKey: val })">
              <el-option :label="$t('enable')" :value="0" />
              <el-option :label="$t('disable')" :value="1" />
              <el-option :label="$t('optional')" :value="2" />
            </el-select>
          </label>

          <label class="row">
            <span>{{ $t('addAccount') }}</span>
            <el-switch :model-value="setting.addEmail === 0" @change="val => saveSwitch('addEmail', val)" />
          </label>

          <label class="row">
            <span>{{ $t('multipleEmail') }}</span>
            <el-switch :model-value="setting.manyEmail === 0" @change="val => saveSwitch('manyEmail', val)" />
          </label>

          <label class="row">
            <span>{{ $t('autoRefresh') }}</span>
            <el-select :model-value="setting.autoRefresh" @change="val => savePatch({ autoRefresh: val })">
              <el-option :label="$t('disable')" :value="0" />
              <el-option label="3s" :value="3" />
              <el-option label="5s" :value="5" />
              <el-option label="10s" :value="10" />
              <el-option label="15s" :value="15" />
              <el-option label="20s" :value="20" />
            </el-select>
          </label>
        </div>
      </section>

      <section class="card">
        <div class="card-title">{{ $t('availableDomains') }}</div>
        <div class="card-body">
          <div class="hint">{{ $t('availableDomainsDesc') }}</div>
          <el-input-tag v-model="domainInputs" :placeholder="$t('domainDesc')" />
          <div class="spacer"></div>

          <label class="row">
            <span>{{ $t('emailPrefix') }}</span>
            <el-input-number v-model="minEmailPrefix" :min="1" :max="20" />
          </label>

          <div class="actions">
            <el-button type="primary" @click="saveDomains" :loading="saving">{{ $t('save') }}</el-button>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-title">{{ $t('emailSetting') }}</div>
        <div class="card-body">
          <label class="row">
            <span>{{ $t('receiveEmail') }}</span>
            <el-switch :model-value="setting.receive === 0" @change="val => saveSwitch('receive', val)" />
          </label>

          <label class="row">
            <span>{{ $t('sendEmail') }}</span>
            <el-switch :model-value="setting.send === 0" @change="val => saveSwitch('send', val)" />
          </label>

          <div class="row readonly">
            <span>{{ $t('sendEmail') }} Mode</span>
            <el-tag>{{ setting.sendMode || 'record' }}</el-tag>
          </div>

          <label class="row">
            <span>{{ $t('resendToken') }}</span>
            <div class="inline">
              <el-input v-model="resendTokenInput" :placeholder="$t('addResendTokenDesc')" show-password />
              <el-button type="primary" @click="saveResendToken" :loading="saving">{{ $t('save') }}</el-button>
            </div>
          </label>

          <div class="row readonly">
            <span>Resend</span>
            <el-tag :type="setting.resendConfigured ? 'success' : 'info'">
              {{ setting.resendConfigured ? $t('enabled') : $t('disabled') }}
            </el-tag>
          </div>

          <div class="row readonly" v-if="setting.sendMode === 'smtp'">
            <span>SMTP Host</span>
            <code>{{ setting.smtpHost || '-' }}</code>
          </div>

          <div class="row readonly" v-if="setting.sendMode === 'smtp'">
            <span>SMTP From</span>
            <code>{{ setting.smtpFromEmail || '-' }}</code>
          </div>

          <div class="row readonly" v-if="setting.sendMode === 'direct-mx'">
            <span>Direct MX</span>
            <code>Enabled on server</code>
          </div>

          <div class="row readonly" v-if="setting.sendMode === 'direct-mx'">
            <span>HELO</span>
            <code>{{ setting.directHeloHost || 'mail.freeloader.xyz' }}</code>
          </div>

          <div class="row readonly" v-if="setting.sendMode === 'direct-mx'">
            <span>DKIM</span>
            <code>{{ setting.dkimSelector || 'default' }}._domainkey.{{ setting.dkimDomain || '-' }}</code>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-title">{{ $t('noticeTitle') }}</div>
        <div class="card-body">
          <label class="row">
            <span>{{ $t('noticePopup') }}</span>
            <el-switch :model-value="setting.notice === 0" @change="val => saveSwitch('notice', val)" />
          </label>

          <label class="row">
            <span>{{ $t('loginBoxOpacity') }}</span>
            <el-input-number v-model="loginOpacity" :precision="2" :step="0.01" :max="1" :min="0" />
          </label>

          <div class="actions">
            <el-button type="primary" @click="saveDisplay" :loading="saving">{{ $t('save') }}</el-button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useSettingStore } from '@/store/setting.js'
import { settingQuery, settingSet } from '@/request/setting.js'

const loading = ref(true)
const saving = ref(false)
const settingStore = useSettingStore()
const setting = ref({})
const titleInput = ref('')
const domainInputs = ref([])
const minEmailPrefix = ref(1)
const loginOpacity = ref(1)
const resendTokenInput = ref('')

getSettings()

async function getSettings() {
  loading.value = true
  try {
    const data = await settingQuery()
    setting.value = data
    settingStore.settings = data
    settingStore.domainList = data.domainList || []
    titleInput.value = data.title || ''
    domainInputs.value = [...(data.allowedDomains || [])]
    minEmailPrefix.value = data.minEmailPrefix || 1
    loginOpacity.value = data.loginOpacity || 1
  } finally {
    loading.value = false
  }
}

async function savePatch(patch) {
  if (saving.value) return
  saving.value = true
  try {
    await settingSet(patch)
    ElMessage({ message: 'Saved', type: 'success', plain: true })
    await getSettings()
  } finally {
    saving.value = false
  }
}

function saveSwitch(key, enabled) {
  savePatch({ [key]: enabled ? 0 : 1 })
}

function saveTitle() {
  savePatch({ title: titleInput.value })
}

function saveDomains() {
  const cleaned = domainInputs.value.map(item => item.trim().toLowerCase()).filter(Boolean)
  savePatch({
    allowedDomains: cleaned,
    minEmailPrefix: minEmailPrefix.value,
  })
}

function saveDisplay() {
  savePatch({
    loginOpacity: loginOpacity.value,
    notice: setting.value.notice,
  })
}

function saveResendToken() {
  savePatch({ resendToken: resendTokenInput.value })
}
</script>

<style scoped lang="scss">
.settings-page {
  height: 100%;
  overflow: auto;
  padding: 20px;
  background: var(--extra-light-fill);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 20px;
}

.card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  overflow: hidden;
}

.card-title {
  padding: 14px 18px;
  font-weight: 700;
  border-bottom: 1px solid var(--el-border-color);
}

.card-body {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.row {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 12px;
  align-items: center;
}

.readonly code {
  overflow-wrap: anywhere;
}

.inline {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
}

.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.actions {
  display: flex;
  justify-content: flex-end;
}

.spacer {
  height: 4px;
}

@media (max-width: 640px) {
  .settings-page {
    padding: 14px;
  }

  .row {
    grid-template-columns: 1fr;
  }

  .inline {
    grid-template-columns: 1fr;
  }
}
</style>

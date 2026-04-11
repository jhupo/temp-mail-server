import {createApp} from 'vue';
import App from './App.vue';
import router from './router';
import './style.css';
import { init } from '@/init/init.js';
import { createPinia } from 'pinia';
import piniaPersistedState from 'pinia-plugin-persistedstate';
import 'element-plus/theme-chalk/dark/css-vars.css';
import 'nprogress/nprogress.css';
import perm from "@/perm/perm.js";
import { registerSW } from "virtual:pwa-register";
const pinia = createPinia().use(piniaPersistedState)
import i18n from "@/i18n/index.js";
const app = createApp(App).use(pinia)
await init()
app.use(router).use(i18n).directive('perm',perm)
app.config.devtools = true;

app.mount('#app');

function showUpdatePrompt(applyUpdate) {
    if (document.getElementById('pwa-update-banner')) {
        return;
    }
    const banner = document.createElement('div');
    banner.id = 'pwa-update-banner';
    banner.style.position = 'fixed';
    banner.style.right = '16px';
    banner.style.bottom = '16px';
    banner.style.zIndex = '99999';
    banner.style.display = 'flex';
    banner.style.alignItems = 'center';
    banner.style.gap = '10px';
    banner.style.padding = '10px 12px';
    banner.style.background = '#1f2937';
    banner.style.color = '#fff';
    banner.style.borderRadius = '10px';
    banner.style.boxShadow = '0 6px 20px rgba(0,0,0,0.2)';
    banner.style.fontSize = '13px';
    banner.textContent = '发现新版本';

    const updateBtn = document.createElement('button');
    updateBtn.type = 'button';
    updateBtn.textContent = '点击升级';
    updateBtn.style.border = 'none';
    updateBtn.style.borderRadius = '6px';
    updateBtn.style.padding = '6px 10px';
    updateBtn.style.cursor = 'pointer';
    updateBtn.style.background = '#409eff';
    updateBtn.style.color = '#fff';
    updateBtn.onclick = () => {
        applyUpdate();
    };

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.textContent = '稍后';
    closeBtn.style.border = 'none';
    closeBtn.style.borderRadius = '6px';
    closeBtn.style.padding = '6px 10px';
    closeBtn.style.cursor = 'pointer';
    closeBtn.style.background = '#4b5563';
    closeBtn.style.color = '#fff';
    closeBtn.onclick = () => {
        banner.remove();
    };

    banner.appendChild(updateBtn);
    banner.appendChild(closeBtn);
    document.body.appendChild(banner);
}

const updateSW = registerSW({
    immediate: true,
    onNeedRefresh() {
        showUpdatePrompt(() => updateSW(true));
    },
    onRegisteredSW(_swUrl, registration) {
        if (!registration) {
            return;
        }
        setInterval(() => {
            registration.update();
        }, 60 * 1000);
    },
});

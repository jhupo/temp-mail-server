import http from '@/axios/index.js';

export function versionInfo() {
    return http.get('/version', {noMsg: true})
}

export function checkUpdate() {
    return http.get('/update/check', {noMsg: true})
}

export function triggerUpdate(payload = {}) {
    return http.post('/update/trigger', payload, {noMsg: true})
}

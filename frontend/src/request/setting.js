import http from '@/axios/index.js';

export function settingSet(setting) {
    return http.put('/setting/set',setting)
}

export function settingQuery() {
    return http.get('/setting/query')
}

export function websiteConfig() {
    return http.get('/setting/websiteConfig')
}

export function setBackground(background) {
    return http.put('/setting/setBackground',{background})
}

export function deleteBackground() {
    return http.delete('/setting/deleteBackground')
}

export function certStatus() {
    return http.get('/cert/status')
}

export function certApply() {
    return http.post('/cert/apply')
}

export function certRenew() {
    return http.post('/cert/renew')
}

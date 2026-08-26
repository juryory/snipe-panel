import { createApp } from 'vue'
import 'vant/lib/index.css'

import App from './App.vue'
import { router } from './router'
import { showFailToast } from 'vant'

import { setErrorNotifier, setPasswordChangeHandler, setUnauthorizedHandler } from '../api'
import { session } from '../store'
import './style.css'

setErrorNotifier((message) => showFailToast(message))

setUnauthorizedHandler(() => {
  session.user = null
  if (router.currentRoute.value.name !== 'login') {
    router.replace({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
  }
})
setPasswordChangeHandler(() => {
  if (router.currentRoute.value.name !== 'change-password') {
    router.replace({ name: 'change-password' })
  }
})

// 仅生产环境注册:开发时 SW 会拦住 Vite 的热更新请求
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}

createApp(App).use(router).mount('#app')

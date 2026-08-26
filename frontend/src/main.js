import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'

import App from './App.vue'
import { router } from './router'
import { setPasswordChangeHandler, setUnauthorizedHandler } from './api'
import { session } from './store'
import './style.css'

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
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // 注册失败不影响使用,PWA 只是锦上添花
    })
  })
}

createApp(App)
  .use(router)
  // 全中文(PRD 第 4 节):Element Plus 内置组件的默认文案也要跟着切
  .use(ElementPlus, { locale: zhCn })
  .mount('#app')

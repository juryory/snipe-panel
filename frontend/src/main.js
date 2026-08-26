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

createApp(App)
  .use(router)
  // 全中文(PRD 第 4 节):Element Plus 内置组件的默认文案也要跟着切
  .use(ElementPlus, { locale: zhCn })
  .mount('#app')

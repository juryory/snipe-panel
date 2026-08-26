import { createRouter, createWebHistory } from 'vue-router'

import { api } from '../api'
import { session } from '../store'

/**
 * 手机端路由。base 是 /m —— 这一半由 m.html 承载,与后台的 index.html 完全分开。
 */
const routes = [
  { path: '/', redirect: '/scan' },
  {
    path: '/login',
    name: 'login',
    component: () => import('./views/Login.vue'),
    meta: { public: true, plain: true },
  },
  {
    path: '/change-password',
    name: 'change-password',
    component: () => import('./views/ChangePassword.vue'),
    meta: { allowBeforePasswordChange: true, plain: true },
  },

  { path: '/scan', name: 'scan', component: () => import('./views/Scan.vue'), meta: { tab: 'scan' } },
  { path: '/assets', name: 'assets', component: () => import('./views/Assets.vue'), meta: { tab: 'assets' } },
  { path: '/mine', name: 'mine', component: () => import('./views/Mine.vue'), meta: { tab: 'mine' } },

  { path: '/a/:tag', name: 'asset', component: () => import('./views/AssetDetail.vue'), meta: { plain: true } },
  { path: '/install', name: 'install', component: () => import('./views/Install.vue'), meta: { plain: true } },

  { path: '/:pathMatch(.*)*', redirect: '/scan' },
]

export const router = createRouter({
  history: createWebHistory('/m'),
  routes,
})

router.beforeEach(async (to) => {
  if (!session.loaded) {
    try {
      session.user = await api.me()
    } catch {
      session.user = null
    }
    session.loaded = true
  }

  if (to.meta.public) return true
  if (!session.user) return { name: 'login', query: { redirect: to.fullPath } }

  // PRD 3.7:首次登录强制改密,改密前不放行任何业务页面
  if (session.user.must_change_password && !to.meta.allowBeforePasswordChange) {
    return { name: 'change-password' }
  }
  return true
})

import { createRouter, createWebHistory } from 'vue-router'

import { api } from './api'
import { session } from './store'

const routes = [
  { path: '/', redirect: '/m' },
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { public: true } },
  {
    path: '/change-password',
    name: 'change-password',
    component: () => import('./views/ChangePassword.vue'),
    meta: { allowBeforePasswordChange: true },
  },

  // 移动端(PRD 3.4:首页即取景框)
  { path: '/m', name: 'scan', component: () => import('./views/m/Scan.vue') },
  { path: '/m/a/:tag', name: 'm-asset', component: () => import('./views/m/AssetDetail.vue') },
  { path: '/m/mine', name: 'm-mine', component: () => import('./views/m/MyAssets.vue') },
  { path: '/m/install', name: 'm-install', component: () => import('./views/m/Install.vue') },

  // 桌面后台
  { path: '/admin', redirect: '/admin/assets' },
  { path: '/admin/assets', name: 'admin-assets', component: () => import('./views/admin/AssetList.vue') },
  { path: '/admin/categories', name: 'admin-categories', component: () => import('./views/admin/Categories.vue'), meta: { admin: true } },
  { path: '/admin/companies', name: 'admin-companies', component: () => import('./views/admin/Companies.vue') },
  { path: '/admin/users', name: 'admin-users', component: () => import('./views/admin/Users.vue'), meta: { admin: true } },
  { path: '/admin/checkouts', name: 'admin-checkouts', component: () => import('./views/admin/Checkouts.vue') },
  { path: '/admin/inventory', name: 'admin-inventory', component: () => import('./views/admin/Inventory.vue') },

  { path: '/:pathMatch(.*)*', redirect: '/m' },
]

export const router = createRouter({
  history: createWebHistory(),
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
  if (to.meta.admin && session.user.role !== 'admin') return { name: 'scan' }
  return true
})

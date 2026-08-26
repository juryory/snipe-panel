import { createRouter, createWebHistory } from 'vue-router'

import { api } from './api'
import { session } from './store'

const routes = [
  // 手机端是另一个入口(m.html),不在这个路由表里;窄屏访问根路径直接整页跳过去
  { path: '/', redirect: () => (isNarrowScreen() ? redirectToMobile() : '/admin/assets') },
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { public: true } },
  {
    path: '/change-password',
    name: 'change-password',
    component: () => import('./views/ChangePassword.vue'),
    meta: { allowBeforePasswordChange: true },
  },


  // 桌面后台
  { path: '/admin', redirect: '/admin/assets' },
  { path: '/admin/assets', name: 'admin-assets', component: () => import('./views/admin/AssetList.vue') },
  { path: '/admin/categories', name: 'admin-categories', component: () => import('./views/admin/Categories.vue'), meta: { admin: true } },
  { path: '/admin/companies', name: 'admin-companies', component: () => import('./views/admin/Companies.vue') },
  { path: '/admin/users', name: 'admin-users', component: () => import('./views/admin/Users.vue'), meta: { admin: true } },
  { path: '/admin/checkouts', name: 'admin-checkouts', component: () => import('./views/admin/Checkouts.vue') },
  { path: '/admin/inventory', name: 'admin-inventory', component: () => import('./views/admin/Inventory.vue') },
  { path: '/admin/repairs', name: 'admin-repairs', component: () => import('./views/admin/Repairs.vue') },

  { path: '/:pathMatch(.*)*', redirect: '/admin/assets' },
]

function isNarrowScreen() {
  return window.matchMedia('(max-width: 768px)').matches
}

function redirectToMobile() {
  window.location.replace('/m/')
  return '/admin/assets' // 占位,整页跳转会立刻接管
}

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
  if (to.meta.admin && session.user.role !== 'admin') return { name: 'admin-assets' }
  return true
})

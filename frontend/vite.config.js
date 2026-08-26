import { resolve } from 'node:path'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * 两个独立入口:
 *
 * - index.html  → 桌面后台(Element Plus),路由 /admin/*
 * - m.html      → 手机端(Vant),路由 /m/*
 *
 * 拆开的原因:两套 UI 库如果打进同一个包,手机用户要白下载一整套桌面组件。
 * 分入口之后各自只加载自己那套,互不影响;将来手机端要换成 App 壳或重写成
 * 小程序,也只动这一半。
 */
function mobileHistoryFallback() {
  return {
    name: 'mobile-history-fallback',
    configureServer(server) {
      // 开发时 /m/xxx 这类前端路由要落到 m.html,否则 Vite 会回退到 index.html
      server.middlewares.use((req, _res, next) => {
        if (req.url === '/m' || req.url.startsWith('/m/')) {
          if (!req.url.includes('.')) req.url = '/m.html'
        }
        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [vue(), mobileHistoryFallback()],
  server: {
    host: true,
    // 开发时把 /api 代理到后端,前后端同域 —— 与生产一致(PRD 第 7 节)
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        admin: resolve(__dirname, 'index.html'),
        mobile: resolve(__dirname, 'm.html'),
      },
    },
  },
})

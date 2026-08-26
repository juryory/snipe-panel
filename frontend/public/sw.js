/**
 * Service Worker。
 *
 * 存在的两个理由:
 * 1. 让浏览器认可这是个可安装的应用(Android Chrome 的「安装应用」入口)
 * 2. 二次打开时前端壳子秒开,不用重新下 Element Plus 那一大坨
 *
 * 刻意不做的事:
 * - **绝不碰 /api**。设备状态、借出情况都是实时数据,缓存了就是在骗人。
 * - **不做构建期 precache 清单**。那要求 SW 和构建产物绑定,每次发版都得重新
 *   生成清单;这里改用运行时缓存,Vite 给静态资源的文件名带内容哈希,
 *   缓存旧文件本身不会造成版本错乱。
 */
const SHELL_CACHE = 'snipe-shell-v1'
const ASSET_CACHE = 'snipe-assets-v1'
const KEEP = [SHELL_CACHE, ASSET_CACHE]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(['/', '/m'])).catch(() => {}),
  )
  // 新版本立刻接管,配合下面的「导航走网络优先」,不会让人卡在旧版前端上
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((n) => !KEEP.includes(n)).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  // 接口一律直连,不缓存也不拦截
  if (url.pathname.startsWith('/api/')) return

  // 页面导航:网络优先,断网时退回缓存的壳子
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone()
          caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy)).catch(() => {})
          return response
        })
        .catch(() => caches.match(request).then((hit) => hit || caches.match('/m'))),
    )
    return
  }

  // 静态资源:先给缓存,后台顺手更新(文件名带哈希,拿到旧的也不会串版本)
  if (url.pathname.startsWith('/assets/') || /\.(png|svg|ico|webmanifest)$/.test(url.pathname)) {
    event.respondWith(
      caches.open(ASSET_CACHE).then((cache) =>
        cache.match(request).then((hit) => {
          const network = fetch(request)
            .then((response) => {
              if (response.ok) cache.put(request, response.clone())
              return response
            })
            .catch(() => hit)
          return hit || network
        }),
      ),
    )
  }
})

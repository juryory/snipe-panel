import { reactive } from 'vue'

export const session = reactive({
  user: null,
  loaded: false,
})

/**
 * 台账列表被 keep-alive 缓存着,新增/编辑/删除之后回到列表不会自动重拉。
 * 写操作把这个置 true,列表 onActivated 时检查并刷新。
 */
export const dirty = reactive({ assets: false })

export function markAssetsDirty() {
  dirty.assets = true
}

export function isAdmin() {
  return session.user && session.user.role === 'admin'
}

export function displayName(user) {
  if (!user) return ''
  return user.real_name || user.username
}

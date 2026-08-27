/**
 * 接口封装。
 * 鉴权走 httpOnly Cookie(PRD 3.7),前端拿不到也不需要 token,
 * 因此所有请求带 credentials: 'same-origin' 即可。
 */
let onUnauthorized = () => {}
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

let onPasswordChangeRequired = () => {}
export function setPasswordChangeHandler(fn) {
  onPasswordChangeRequired = fn
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

async function request(path, { method = 'GET', body, params, raw = false } = {}) {
  const url = new URL(path, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v)
    })
  }
  const init = { method, credentials: 'same-origin', headers: {} }
  if (body instanceof FormData) {
    // 不能自己设 Content-Type:multipart 的 boundary 要由浏览器生成
    init.body = body
  } else if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }

  let res
  try {
    res = await fetch(url, init)
  } catch {
    throw new ApiError(0, '网络异常,请检查连接')
  }

  if (res.status === 401) {
    onUnauthorized()
    throw new ApiError(401, '请先登录')
  }
  if (!res.ok) {
    let detail = `请求失败(${res.status})`
    try {
      const data = await res.json()
      if (data && data.detail) {
        detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
      }
    } catch {
      /* 响应体不是 JSON,用默认文案 */
    }
    // PRD 3.7:首次登录强制改密,未改密前后端会拒绝一切业务接口
    if (res.status === 403 && detail.includes('修改密码')) onPasswordChangeRequired()
    throw new ApiError(res.status, detail)
  }
  if (raw) return res
  if (res.status === 204) return null
  return res.json()
}

/**
 * 统一的错误提示。
 *
 * 具体怎么弹由各入口注入 —— 这一层不能 import 任何 UI 库:后台用 Element Plus、
 * 手机端用 Vant,一旦在这里写死一个,另一半就会被迫打包进整套用不上的组件库。
 */
let errorNotifier = (message) => {
  // 没注册就退化成控制台,至少不吞掉错误
  console.error(message)
}

export function setErrorNotifier(fn) {
  errorNotifier = fn
}

/** 页面里 catch 后调用即可。 */
export function toast(err) {
  errorNotifier(err instanceof ApiError ? err.detail : String(err))
}

export const api = {
  login: (username, password) =>
    request('/api/auth/login', { method: 'POST', body: { username, password } }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  me: () => request('/api/auth/me'),
  changePassword: (old_password, new_password) =>
    request('/api/auth/change-password', { method: 'POST', body: { old_password, new_password } }),

  listAssets: (params) => request('/api/assets', { params }),
  getAsset: (id) => request(`/api/assets/${id}`),
  getAssetByTag: (tag) => request(`/api/assets/by-tag/${encodeURIComponent(tag)}`),
  createAsset: (body) => request('/api/assets', { method: 'POST', body }),
  updateAsset: (id, body) => request(`/api/assets/${id}`, { method: 'PUT', body }),
  deleteAsset: (id) => request(`/api/assets/${id}`, { method: 'DELETE' }),
  assetHistory: (id) => request(`/api/assets/${id}/history`),
  checkout: (id, body) => request(`/api/assets/${id}/checkout`, { method: 'POST', body }),
  checkin: (id, body) => request(`/api/assets/${id}/checkin`, { method: 'POST', body }),
  qrcodeUrl: (id, format = 'png', scale = 8) =>
    `/api/assets/${id}/qrcode?format=${format}&scale=${scale}`,
  labelUrl: (id, moduleWidth = 0.375, moduleHeight = 8) =>
    `/api/assets/${id}/label?module_width=${moduleWidth}&module_height=${moduleHeight}`,
  exportQrcodes: (assetIds, fmt) =>
    request(`/api/assets/qrcodes/export?fmt=${fmt}`, { method: 'POST', body: assetIds, raw: true }),
  importTemplateUrl: () => '/api/assets/import/template',
  exportAssetsUrl: (params) => {
    const url = new URL('/api/assets/export', window.location.origin)
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v)
    })
    return url.pathname + url.search
  },
  importAssets: (file, { commit, createMissingCompanies }) => {
    const form = new FormData()
    form.append('file', file)
    form.append('create_missing_companies', createMissingCompanies ? 'true' : 'false')
    return request(commit ? '/api/assets/import' : '/api/assets/import/preview', {
      method: 'POST',
      body: form,
    })
  },

  listCompanies: () => request('/api/companies'),
  createCompany: (body) => request('/api/companies', { method: 'POST', body }),
  updateCompany: (id, body) => request(`/api/companies/${id}`, { method: 'PUT', body }),
  deleteCompany: (id) => request(`/api/companies/${id}`, { method: 'DELETE' }),

  listCategories: () => request('/api/categories'),
  createCategory: (body) => request('/api/categories', { method: 'POST', body }),
  updateCategory: (id, body) => request(`/api/categories/${id}`, { method: 'PUT', body }),
  deleteCategory: (id) => request(`/api/categories/${id}`, { method: 'DELETE' }),

  listUsers: (q) => request('/api/users', { params: { q } }),
  listUsersDetail: () => request('/api/users/detail'),
  createUser: (body) => request('/api/users', { method: 'POST', body }),
  updateUser: (id, body) => request(`/api/users/${id}`, { method: 'PUT', body }),
  resetPassword: (id, new_password) =>
    request(`/api/users/${id}/reset-password`, { method: 'POST', body: { new_password } }),

  listCheckouts: (params) => request('/api/checkouts', { params }),
  listLogs: (params) => request('/api/logs', { params }),
  logActions: () => request('/api/logs/actions'),
  checkoutKit: (body) => request('/api/checkouts/kit', { method: 'POST', body }),

  // 报修
  reportRepair: (assetId, body) =>
    request(`/api/assets/${assetId}/repairs`, { method: 'POST', body }),
  assetRepairs: (assetId) => request(`/api/assets/${assetId}/repairs`),
  listRepairs: (params) => request('/api/repairs', { params }),
  updateRepair: (id, body) => request(`/api/repairs/${id}`, { method: 'PUT', body }),
  closeRepair: (id, body) => request(`/api/repairs/${id}/close`, { method: 'POST', body }),

  // 盘库(滚动盘点)
  checkAsset: (id, body) => request(`/api/assets/${id}/check`, { method: 'POST', body }),
  assetChecks: (id) => request(`/api/assets/${id}/checks`),
  listChecks: (params) => request('/api/inventory/checks', { params }),
  inventorySummary: (unchecked_days) =>
    request('/api/inventory/summary', { params: { unchecked_days } }),
  resolveCheck: (id, action) =>
    request(`/api/inventory/checks/${id}/resolve`, { method: 'POST', body: { action } }),
  myAssets: () => request('/api/me/assets'),
}

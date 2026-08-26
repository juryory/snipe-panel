/** 后端下发的时间带时区(见 schemas.UtcDatetime),这里统一按本地时区展示。 */
export function fmtTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function fmtDate(value) {
  if (!value) return '—'
  return String(value).slice(0, 10)
}

/** 设备的展示状态:借出是派生状态(PRD 3.5),优先于 status 显示。 */
export function displayStatus(asset) {
  if (!asset) return { label: '', type: 'info' }
  // 在修优先于在库:设备虽然没借出去,但也不能借
  if (asset.open_repair_id) return { label: '维修中', type: 'danger' }
  if (asset.is_checked_out) {
    const overdue = asset.current_checkout && asset.current_checkout.is_overdue
    return { label: overdue ? '逾期未还' : '借出', type: overdue ? 'danger' : 'warning' }
  }
  const map = { in_stock: 'success', repair: 'warning', retired: 'info' }
  return { label: asset.status_label, type: map[asset.status] || 'info' }
}

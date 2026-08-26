<template>
  <el-card shadow="never">
    <div class="filters">
      <strong style="margin-right: auto">操作日志</strong>
      <el-select v-model="filters.action" placeholder="全部动作" clearable filterable
        style="width: 180px" @change="reload(1)">
        <el-option v-for="a in actions" :key="a" :label="labelOf(a)" :value="a" />
      </el-select>
      <el-select v-model="filters.actor_id" placeholder="全部操作人" clearable filterable
        style="width: 160px" @change="reload(1)">
        <el-option v-for="u in users" :key="u.id" :label="displayName(u)" :value="u.id" />
      </el-select>
      <el-select v-model="filters.days" style="width: 130px" @change="reload(1)">
        <el-option label="最近 7 天" :value="7" />
        <el-option label="最近 30 天" :value="30" />
        <el-option label="最近 90 天" :value="90" />
        <el-option label="最近一年" :value="365" />
      </el-select>
    </div>

    <el-table v-loading="loading" :data="rows" style="margin-top: 12px">
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作人" width="120" prop="actor" />
      <el-table-column label="动作" width="140">
        <template #default="{ row }">
          <el-tag :type="toneOf(row.action)" size="small">{{ row.action_label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="详情" min-width="280" show-overflow-tooltip>
        <template #default="{ row }">{{ row.detail || '—' }}</template>
      </el-table-column>
      <el-table-column label="对象" width="120">
        <template #default="{ row }">
          <span v-if="row.target_id" class="muted">{{ row.target_type }} #{{ row.target_id }}</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !rows.length" description="这段时间没有匹配的记录" />

    <el-pagination
      v-if="total"
      style="margin-top: 12px; justify-content: flex-end"
      :layout="narrow ? 'total, prev, pager, next' : 'total, sizes, prev, pager, next'"
      :total="total"
      :current-page="page"
      :page-size="pageSize"
      :page-sizes="[50, 100, 200]"
      @current-change="reload"
      @size-change="(size) => { pageSize = size; reload(1) }"
    />
  </el-card>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'

import { api, toast } from '../../api'
import { useNarrow } from '../../useNarrow'
import { fmtTime } from '../../format'
import { displayName } from '../../store'

const narrow = useNarrow()
const rows = ref([])
const actions = ref([])
const users = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const loading = ref(false)
const filters = reactive({ action: null, actor_id: null, days: 30 })

// 删除、锁定这类要显眼一点,登录、盘库这种日常的淡一点
const TONES = {
  asset_delete: 'danger',
  category_delete: 'danger',
  company_delete: 'danger',
  login_locked: 'danger',
  by_tag_rate_limited: 'danger',
  repair_scrapped: 'danger',
  repair_open: 'warning',
  asset_update: 'warning',
  user_reset_password: 'warning',
  checkout: 'primary',
  checkout_kit: 'primary',
  checkin: 'success',
  asset_create: 'success',
  asset_import: 'success',
}

function toneOf(action) {
  return TONES[action] || 'info'
}

function labelOf(action) {
  const hit = rows.value.find((r) => r.action === action)
  return hit ? hit.action_label : action
}

async function reload(toPage) {
  if (toPage) page.value = toPage
  loading.value = true
  try {
    const data = await api.listLogs({
      action: filters.action,
      actor_id: filters.actor_id,
      days: filters.days,
      page: page.value,
      page_size: pageSize.value,
    })
    rows.value = data.items
    total.value = data.total
  } catch (err) {
    toast(err)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    ;[actions.value, users.value] = await Promise.all([api.logActions(), api.listUsers('')])
  } catch {
    // 筛选项拉不到不影响看日志
  }
  await reload(1)
})
</script>

<style scoped>
.filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
</style>

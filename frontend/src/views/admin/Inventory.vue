<template>
  <div class="stack">
    <!--
      滚动盘点:没有「盘点任务」这个概念,超期未盘列表就是待办清单。
      清空了就等于盘完一轮。
    -->
    <el-card shadow="never">
      <div class="row-between" style="margin-bottom: 12px">
        <strong>盘库概览</strong>
        <div>
          <span class="muted" style="margin-right: 8px">盘库周期</span>
          <el-select v-model="days" style="width: 120px" @change="loadSummary">
            <el-option label="30 天" :value="30" />
            <el-option label="90 天" :value="90" />
            <el-option label="180 天" :value="180" />
          </el-select>
        </div>
      </div>

      <div v-loading="loadingSummary" class="cards">
        <div class="card">
          <div class="card__num">{{ summary.total }}</div>
          <div class="muted">在册设备</div>
        </div>
        <div class="card card--ok">
          <div class="card__num">{{ summary.checked }}</div>
          <div class="muted">{{ days }} 天内已盘</div>
        </div>
        <div class="card" :class="{ 'card--warn': summary.overdue }">
          <div class="card__num">{{ summary.overdue }}</div>
          <div class="muted">超期未盘</div>
          <el-button v-if="summary.overdue" link type="primary" @click="gotoOverdue">
            去盘这些 →
          </el-button>
        </div>
        <div class="card" :class="{ 'card--danger': summary.pending_discrepancies }">
          <div class="card__num">{{ summary.pending_discrepancies }}</div>
          <div class="muted">待处理差异</div>
        </div>
      </div>

      <el-progress
        v-if="summary.total"
        :percentage="percent"
        :status="percent === 100 ? 'success' : undefined"
        style="margin-top: 16px"
      />
    </el-card>

    <el-card shadow="never">
      <div class="row-between" style="margin-bottom: 12px">
        <strong>盘库记录</strong>
        <el-radio-group v-model="mode" @change="loadChecks">
          <el-radio-button :value="true">待处理差异</el-radio-button>
          <el-radio-button :value="false">全部</el-radio-button>
        </el-radio-group>
      </div>

      <el-table v-loading="loadingChecks" :data="rows" :row-class-name="rowClass">
        <el-table-column label="资产编号" width="120">
          <template #default="{ row }"><span class="tag">{{ row.asset_tag }}</span></template>
        </el-table-column>
        <el-table-column prop="asset_name" label="设备" min-width="150" />
        <el-table-column label="盘库人" width="110">
          <template #default="{ row }">{{ displayName(row.checked_by) }}</template>
        </el-table-column>
        <el-table-column label="盘库时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.checked_at) }}</template>
        </el-table-column>
        <el-table-column label="差异" min-width="240">
          <template #default="{ row }">
            <span v-if="!row.has_discrepancy" class="muted">无</span>
            <div v-else class="diff">
              <div v-if="row.observed_location !== row.location_at_check">
                位置:<span class="was">{{ row.location_at_check || '（空）' }}</span>
                → <strong>{{ row.observed_location || '（空）' }}</strong>
              </div>
              <div v-if="row.observed_status !== row.status_at_check">
                状态:<span class="was">{{ row.status_at_check_label }}</span>
                → <strong>{{ row.observed_status_label }}</strong>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="使用情况" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.note || '—' }}</template>
        </el-table-column>
        <el-table-column label="盘时借给" width="100">
          <template #default="{ row }">{{ row.borrower ? displayName(row.borrower) : '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.pending" type="danger" size="small">待处理</el-tag>
            <el-tag v-else-if="row.applied" type="warning" size="small">已采纳</el-tag>
            <el-tag v-else-if="row.has_discrepancy" type="info" size="small">已忽略</el-tag>
            <el-tag v-else type="success" size="small">无误</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" :fixed="narrow ? false : 'right'">
          <template #default="{ row }">
            <template v-if="row.pending">
              <el-button link type="primary" @click="resolve(row, 'apply')">采纳</el-button>
              <el-button link type="info" @click="resolve(row, 'dismiss')">忽略</el-button>
            </template>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loadingChecks && !rows.length" :description="mode ? '没有待处理的差异' : '暂无盘库记录'" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { api, toast } from '../../api'
import { useNarrow } from '../../useNarrow'
import { fmtTime } from '../../format'
import { displayName } from '../../store'

const router = useRouter()

const days = ref(90)
const summary = reactive({ total: 0, checked: 0, overdue: 0, pending_discrepancies: 0 })
const narrow = useNarrow()
const rows = ref([])
const mode = ref(true) // true = 只看待处理差异
const loadingSummary = ref(false)
const loadingChecks = ref(false)

const percent = computed(() =>
  summary.total ? Math.round((summary.checked / summary.total) * 100) : 0,
)

function rowClass({ row }) {
  return row.pending ? 'row-pending' : ''
}

function gotoOverdue() {
  router.push({ name: 'admin-assets', query: { unchecked_days: days.value } })
}

async function loadSummary() {
  loadingSummary.value = true
  try {
    Object.assign(summary, await api.inventorySummary(days.value))
  } catch (err) {
    toast(err)
  } finally {
    loadingSummary.value = false
  }
}

async function loadChecks() {
  loadingChecks.value = true
  try {
    rows.value = await api.listChecks({ pending: mode.value })
  } catch (err) {
    toast(err)
  } finally {
    loadingChecks.value = false
  }
}

async function resolve(row, action) {
  const label = action === 'apply' ? '采纳盘库结果并更新台账' : '忽略差异,维持台账原值'
  try {
    await ElMessageBox.confirm(`确认${label}?`, `${row.asset_tag} ${row.asset_name}`, {
      type: 'warning',
      confirmButtonText: '确认',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await api.resolveCheck(row.id, action)
    ElMessage.success(action === 'apply' ? '已更新台账' : '已忽略')
    await Promise.all([loadChecks(), loadSummary()])
  } catch (err) {
    toast(err)
  }
}

onMounted(async () => {
  await Promise.all([loadSummary(), loadChecks()])
})
</script>

<style scoped>
.cards { display: flex; gap: 12px; flex-wrap: wrap; }
.card {
  flex: 1;
  min-width: 140px;
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafafa;
}
.card__num { font-size: 28px; font-weight: 600; line-height: 1.2; }
.card--ok { border-color: #b3e19d; background: #f0f9eb; }
.card--warn { border-color: #f3d19e; background: #fdf6ec; }
.card--danger { border-color: #fbc4c4; background: #fef0f0; }
.tag { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.diff { line-height: 1.7; }
.was { color: #909399; text-decoration: line-through; }
</style>

<style>
.el-table .row-pending td { background: #fef0f0 !important; }
</style>

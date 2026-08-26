<template>
  <el-card shadow="never">
    <div class="row-between" style="margin-bottom: 12px">
      <strong>借还记录</strong>
      <div>
        <el-radio-group v-model="mode" @change="load">
          <el-radio-button value="open">未归还</el-radio-button>
          <el-radio-button value="overdue">逾期未还</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <el-table v-loading="loading" :data="rows" :row-class-name="rowClass">
      <el-table-column label="资产编号" width="120">
        <template #default="{ row }"><span class="tag">{{ row.asset_tag }}</span></template>
      </el-table-column>
      <el-table-column prop="asset_name" label="设备" min-width="160" />
      <el-table-column label="领用人" width="120">
        <template #default="{ row }">{{ displayName(row.user) }}</template>
      </el-table-column>
      <el-table-column label="借出时间" width="160">
        <template #default="{ row }">{{ fmtTime(row.checked_out_at) }}</template>
      </el-table-column>
      <el-table-column label="应归还" width="160">
        <template #default="{ row }">
          <span :class="{ overdue: row.is_overdue }">{{ fmtTime(row.due_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="实际归还" width="160">
        <template #default="{ row }">{{ fmtTime(row.checked_in_at) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.is_overdue" type="danger" size="small">逾期</el-tag>
          <el-tag v-else-if="!row.checked_in_at" type="warning" size="small">借出中</el-tag>
          <el-tag v-else type="success" size="small">已归还</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="经办" min-width="140">
        <template #default="{ row }">
          <div class="muted small">借出:{{ displayName(row.operator) }}</div>
          <div v-if="row.checkin_operator" class="muted small">
            归还:{{ displayName(row.checkin_operator) }}
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90" :fixed="narrow ? false : 'right'">
        <template #default="{ row }">
          <el-button v-if="!row.checked_in_at" link type="success" @click="checkin(row)">归还</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { api, toast } from '../../api'
import { useNarrow } from '../../useNarrow'
import { fmtTime } from '../../format'
import { displayName } from '../../store'

const narrow = useNarrow()
const rows = ref([])
const loading = ref(false)
const mode = ref('open')

function rowClass({ row }) {
  return row.is_overdue ? 'row-overdue' : ''
}

async function load() {
  loading.value = true
  try {
    rows.value = await api.listCheckouts({
      overdue: mode.value === 'overdue',
      open_only: mode.value !== 'all',
    })
  } catch (err) {
    toast(err)
  } finally {
    loading.value = false
  }
}

async function checkin(row) {
  try {
    await api.checkin(row.asset_id, {})
    ElMessage.success('已归还')
    await load()
  } catch (err) {
    toast(err)
  }
}

onMounted(load)
</script>

<style scoped>
.tag { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.small { font-size: 12px; }
.overdue { color: #f56c6c; font-weight: 600; }
</style>

<style>
/* 逾期未还高亮(PRD 3.5) */
.el-table .row-overdue td { background: #fef0f0 !important; }
</style>

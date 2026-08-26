<template>
  <el-card shadow="never">
    <div class="row-between" style="margin-bottom: 12px">
      <strong>报修</strong>
      <el-radio-group v-model="openOnly" @change="load">
        <el-radio-button :value="true">维修中</el-radio-button>
        <el-radio-button :value="false">全部</el-radio-button>
      </el-radio-group>
    </div>

    <el-table v-loading="loading" :data="rows" :row-class-name="rowClass">
      <el-table-column label="资产编号" width="120">
        <template #default="{ row }"><span class="tag">{{ row.asset_tag }}</span></template>
      </el-table-column>
      <el-table-column prop="asset_name" label="设备" min-width="140" />
      <el-table-column prop="symptom" label="故障描述" min-width="200" show-overflow-tooltip />
      <el-table-column label="报修人" width="110">
        <template #default="{ row }">{{ displayName(row.reported_by) }}</template>
      </el-table-column>
      <el-table-column label="报修时间" width="160">
        <template #default="{ row }">{{ fmtTime(row.reported_at) }}</template>
      </el-table-column>
      <el-table-column label="已修" width="90">
        <template #default="{ row }">
          <span :class="{ slow: row.is_open && row.days_open >= 14 }">{{ row.days_open }} 天</span>
        </template>
      </el-table-column>
      <el-table-column label="送修厂商" min-width="140">
        <template #default="{ row }">{{ row.vendor ? row.vendor.name : '—' }}</template>
      </el-table-column>
      <el-table-column label="费用" width="120">
        <template #default="{ row }">
          <span v-if="row.cost_yuan !== null">
            {{ row.cost_yuan }} 元
            <el-tag v-if="row.under_warranty" size="small" type="success">保修</el-tag>
          </span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.is_open" type="danger" size="small">维修中</el-tag>
          <el-tag v-else :type="row.result === 'scrapped' ? 'info' : 'success'" size="small">
            {{ row.result_label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" :fixed="narrow ? false : 'right'">
        <template #default="{ row }">
          <template v-if="row.is_open">
            <el-button link type="primary" @click="openProgress(row)">跟进</el-button>
            <el-button link type="success" @click="openClose(row)">结案</el-button>
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !rows.length" :description="openOnly ? '没有维修中的设备' : '暂无报修记录'" />

    <!-- 跟进 -->
    <el-dialog v-model="progressVisible" title="跟进维修进度" width="460px">
      <el-form v-if="current" :model="progress" label-width="90px">
        <el-form-item label="设备">
          <span class="tag">{{ current.asset_tag }}</span> {{ current.asset_name }}
        </el-form-item>
        <el-form-item label="故障描述">
          <el-input v-model="progress.symptom" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="送修厂商">
          <el-select v-model="progress.vendor_id" clearable filterable style="width: 100%">
            <el-option v-for="c in companies" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="费用(元)">
          <el-input-number v-model="progress.cost_yuan" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="走保修">
          <el-switch v-model="progress.under_warranty" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="progress.note" type="textarea" :rows="2" placeholder="已寄出 / 对方说要两周 等" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="progressVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveProgress">保存</el-button>
      </template>
    </el-dialog>

    <!-- 结案 -->
    <el-dialog v-model="closeVisible" title="结案" width="440px">
      <el-form v-if="current" label-width="90px">
        <el-form-item label="设备">
          <span class="tag">{{ current.asset_tag }}</span> {{ current.asset_name }}
        </el-form-item>
        <el-form-item label="结果" required>
          <el-radio-group v-model="closing.result">
            <el-radio value="fixed">已修好</el-radio>
            <el-radio value="scrapped">判定报废</el-radio>
            <el-radio value="cancelled">误报</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="费用(元)">
          <el-input-number v-model="closing.cost_yuan" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="closing.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" show-icon :title="closeHint" />
      <template #footer>
        <el-button @click="closeVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doClose">确认结案</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { api, toast } from '../../api'
import { useNarrow } from '../../useNarrow'
import { fmtTime } from '../../format'
import { displayName } from '../../store'

const narrow = useNarrow()
const rows = ref([])
const companies = ref([])
const loading = ref(false)
const saving = ref(false)
const openOnly = ref(true)

const current = ref(null)
const progressVisible = ref(false)
const closeVisible = ref(false)
const progress = reactive({ symptom: '', vendor_id: null, cost_yuan: null, under_warranty: false, note: '' })
const closing = reactive({ result: 'fixed', cost_yuan: null, note: '' })

const closeHint = computed(() => {
  if (closing.result === 'scrapped') return '设备将转为「报废」。'
  return '设备将回到「在库」。若仍借在别人手上,状态会在归还时结算。'
})

function rowClass({ row }) {
  return row.is_open && row.days_open >= 14 ? 'row-slow' : ''
}

async function load() {
  loading.value = true
  try {
    rows.value = await api.listRepairs({ open_only: openOnly.value })
  } catch (err) {
    toast(err)
  } finally {
    loading.value = false
  }
}

function openProgress(row) {
  current.value = row
  Object.assign(progress, {
    symptom: row.symptom,
    vendor_id: row.vendor ? row.vendor.id : null,
    cost_yuan: row.cost_yuan,
    under_warranty: row.under_warranty,
    note: '',
  })
  progressVisible.value = true
}

async function saveProgress() {
  saving.value = true
  try {
    const body = { symptom: progress.symptom, vendor_id: progress.vendor_id,
                   under_warranty: progress.under_warranty }
    if (progress.cost_yuan !== null) body.cost_yuan = progress.cost_yuan
    if (progress.note) body.note = progress.note
    await api.updateRepair(current.value.id, body)
    ElMessage.success('已保存')
    progressVisible.value = false
    await load()
  } catch (err) {
    toast(err)
  } finally {
    saving.value = false
  }
}

function openClose(row) {
  current.value = row
  Object.assign(closing, { result: 'fixed', cost_yuan: row.cost_yuan, note: '' })
  closeVisible.value = true
}

async function doClose() {
  saving.value = true
  try {
    const body = { result: closing.result, note: closing.note }
    if (closing.cost_yuan !== null) body.cost_yuan = closing.cost_yuan
    await api.closeRepair(current.value.id, body)
    ElMessage.success('已结案')
    closeVisible.value = false
    await load()
  } catch (err) {
    toast(err)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    companies.value = await api.listCompanies()
  } catch {
    // 厂商列表拉不到不影响查看报修
  }
  await load()
})
</script>

<style scoped>
.tag { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.slow { color: #f56c6c; font-weight: 600; }
</style>

<style>
/* 修了两周还没回来的高亮出来 */
.el-table .row-slow td { background: #fef0f0 !important; }
</style>

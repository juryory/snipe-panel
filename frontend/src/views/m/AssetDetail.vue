<template>
  <!-- 扫码后的落地页:设备详情 + 借出/归还按钮(PRD 3.4)。 -->
  <div class="m-page stack">
    <div class="row-between">
      <el-button link @click="$router.back()">‹ 返回</el-button>
      <el-button link @click="$router.push('/m')">继续扫码</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="6" animated />

    <el-alert v-else-if="error" type="error" :closable="false" show-icon :title="error" />

    <template v-else-if="asset">
      <el-card shadow="never">
        <div class="row-between">
          <div>
            <div class="tag">{{ asset.asset_tag }}</div>
            <h2 class="name">{{ asset.name }}</h2>
          </div>
          <el-tag :type="badge.type" size="large">{{ badge.label }}</el-tag>
        </div>

        <el-descriptions :column="1" size="small" border style="margin-top: 12px">
          <el-descriptions-item label="分类">{{ asset.category_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="品牌型号">
            {{ [asset.brand, asset.model].filter(Boolean).join(' ') || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="序列号">{{ asset.serial_no || '—' }}</el-descriptions-item>
          <el-descriptions-item label="存放位置">{{ asset.location || '—' }}</el-descriptions-item>
          <el-descriptions-item label="采购公司">
            {{ asset.company ? asset.company.name : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="长期责任人">
            {{ asset.owner ? displayName(asset.owner) : '—' }}
          </el-descriptions-item>
          <el-descriptions-item v-if="asset.current_checkout" label="当前借用人">
            {{ displayName(asset.current_checkout.user) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="asset.current_checkout" label="借出时间">
            {{ fmtTime(asset.current_checkout.checked_out_at) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="asset.current_checkout" label="应归还">
            <span :class="{ overdue: asset.current_checkout.is_overdue }">
              {{ fmtTime(asset.current_checkout.due_at) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item v-if="asset.note" label="备注">{{ asset.note }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never">
        <template v-if="!asset.is_checked_out">
          <div v-if="asset.status !== 'in_stock'" class="muted">
            设备当前为「{{ asset.status_label }}」,不可借出。
          </div>
          <template v-else>
            <el-form label-position="top">
              <el-form-item label="预计归还时间(可留空)">
                <el-date-picker
                  v-model="dueAt"
                  type="datetime"
                  placeholder="选择时间"
                  style="width: 100%"
                  :shortcuts="dueShortcuts"
                />
              </el-form-item>
            </el-form>
            <el-button type="primary" size="large" style="width: 100%" :loading="acting" @click="doCheckout">
              借出到我名下
            </el-button>
          </template>
        </template>

        <template v-else>
          <div class="muted borrowed">
            由 {{ displayName(asset.current_checkout.user) }} 借出中
          </div>
          <el-button type="success" size="large" style="width: 100%" :loading="acting" @click="doCheckin">
            办理归还
          </el-button>
          <div class="muted hint">任何人都可以代为归还,系统会记录经办人。</div>
        </template>
      </el-card>

      <el-card shadow="never">
        <div class="row-between">
          <div>
            <div><strong>盘库</strong></div>
            <div v-if="asset.last_check" class="muted small">
              上次 {{ fmtTime(asset.last_check.checked_at) }} ·
              {{ displayName(asset.last_check.checked_by) }}
            </div>
            <div v-else class="muted small">从未盘库</div>
          </div>
          <el-button type="warning" @click="checkVisible = true">盘库</el-button>
        </div>
        <div v-if="checks.length" class="checks">
          <div v-for="c in checks.slice(0, 5)" :key="c.id" class="record">
            <div class="row-between">
              <span>{{ displayName(c.checked_by) }}</span>
              <el-tag v-if="c.pending" size="small" type="danger">差异待处理</el-tag>
              <el-tag v-else-if="c.has_discrepancy" size="small" type="warning">已修正</el-tag>
              <el-tag v-else size="small" type="success">无误</el-tag>
            </div>
            <div class="muted small">
              {{ fmtTime(c.checked_at) }}
              <template v-if="c.observed_location"> · {{ c.observed_location }}</template>
            </div>
            <div v-if="c.note" class="muted small">{{ c.note }}</div>
          </div>
        </div>
      </el-card>

      <el-card shadow="never">
        <div class="m-title" style="margin-top: 0">流转历史</div>
        <el-empty v-if="!history.length" description="暂无借还记录" :image-size="60" />
        <div v-for="record in history" :key="record.id" class="record">
          <div class="row-between">
            <strong>{{ displayName(record.user) }}</strong>
            <el-tag v-if="!record.checked_in_at" size="small" type="warning">未归还</el-tag>
          </div>
          <div class="muted">
            借出 {{ fmtTime(record.checked_out_at) }}
            <template v-if="record.checked_in_at"> · 归还 {{ fmtTime(record.checked_in_at) }}</template>
          </div>
          <div v-if="record.checkin_operator && record.checkin_operator.id !== record.user.id" class="muted">
            经办人:{{ displayName(record.checkin_operator) }}
          </div>
        </div>
      </el-card>
    </template>

    <CheckDialog v-model="checkVisible" :asset="asset" narrow @done="load" />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

import CheckDialog from '../../components/CheckDialog.vue'
import { api, toast } from '../../api'
import { displayStatus, fmtTime } from '../../format'
import { displayName } from '../../store'

const route = useRoute()

const asset = ref(null)
const history = ref([])
const checks = ref([])
const checkVisible = ref(false)
const loading = ref(true)
const acting = ref(false)
const error = ref('')
const dueAt = ref(null)

const badge = computed(() => displayStatus(asset.value))

const dueShortcuts = [
  { text: '今天下班', value: () => atHour(0, 18) },
  { text: '明天', value: () => atHour(1, 18) },
  { text: '一周后', value: () => atHour(7, 18) },
]

function atHour(dayOffset, hour) {
  const d = new Date()
  d.setDate(d.getDate() + dayOffset)
  d.setHours(hour, 0, 0, 0)
  return d
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    asset.value = await api.getAssetByTag(route.params.tag)
    ;[history.value, checks.value] = await Promise.all([
      api.assetHistory(asset.value.id),
      api.assetChecks(asset.value.id),
    ])
  } catch (err) {
    asset.value = null
    error.value = err.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function doCheckout() {
  acting.value = true
  try {
    await api.checkout(asset.value.id, {
      due_at: dueAt.value ? new Date(dueAt.value).toISOString() : null,
    })
    ElMessage.success('已借出')
    dueAt.value = null
    await load()
  } catch (err) {
    toast(err)
    // 并发场景下多半是被别人抢先借走了,刷新一次让页面反映真实状态
    if (err.status === 409) await load()
  } finally {
    acting.value = false
  }
}

async function doCheckin() {
  acting.value = true
  try {
    await api.checkin(asset.value.id, {})
    ElMessage.success('已归还')
    await load()
  } catch (err) {
    toast(err)
    if (err.status === 409) await load()
  } finally {
    acting.value = false
  }
}

watch(() => route.params.tag, load, { immediate: true })
</script>

<style scoped>
.tag { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #6b7280; }
.name { margin: 4px 0 0; font-size: 18px; }
.overdue { color: #f56c6c; font-weight: 600; }
.borrowed { margin-bottom: 12px; }
.hint { font-size: 12px; margin-top: 8px; text-align: center; }
.record { padding: 10px 0; border-bottom: 1px solid #f0f0f0; }
.checks { margin-top: 8px; }
.small { font-size: 12px; }
.record:last-child { border-bottom: none; }
</style>

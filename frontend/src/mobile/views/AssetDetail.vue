<template>
  <!-- 扫码后的落地页:设备详情 + 借出/归还/盘库(PRD 3.4)。 -->
  <div class="detail">
    <van-nav-bar title="设备详情" left-arrow right-text="继续扫码" @click-left="$router.back()"
      @click-right="$router.replace('/scan')" />

    <van-skeleton v-if="loading" title :row="6" style="padding: 20px" />

    <van-empty v-else-if="error" :description="error" image="error" />

    <template v-else-if="asset">
      <div class="hero">
        <div class="hero__tag tag-mono">{{ asset.asset_tag }}</div>
        <div class="hero__name">{{ asset.name }}</div>
        <van-tag :type="badge.type" size="large" round>{{ badge.label }}</van-tag>
      </div>

      <van-notice-bar
        v-if="openRepair"
        left-icon="warning-o"
        wrapable
        :scrollable="false"
        :text="`维修中:${openRepair.symptom}(已 ${openRepair.days_open} 天)`"
      />

      <van-cell-group inset class="block">
        <van-cell title="分类" :value="asset.category_name || '—'" />
        <van-cell title="品牌型号" :value="[asset.brand, asset.model].filter(Boolean).join(' ') || '—'" />
        <van-cell title="序列号" :value="asset.serial_no || '—'" />
        <van-cell title="存放位置" :value="asset.location || '—'" />
        <van-cell title="采购公司" :value="asset.company ? asset.company.name : '—'" />
        <van-cell v-if="asset.warranty_until" title="保修到期">
          <template #value>
            <span :class="{ expired: asset.warranty_valid === false }">
              {{ asset.warranty_until }}{{ asset.warranty_valid === false ? '(已过保)' : '' }}
            </span>
          </template>
        </van-cell>
        <van-cell title="长期责任人" :value="asset.owner ? displayName(asset.owner) : '—'" />
        <van-cell v-if="asset.note" title="备注" :label="asset.note" />
      </van-cell-group>

      <van-cell-group v-if="asset.current_checkout" inset class="block">
        <van-cell title="当前借用人" :value="displayName(asset.current_checkout.user)" />
        <van-cell title="借出时间" :value="fmtTime(asset.current_checkout.checked_out_at)" />
        <van-cell title="应归还">
          <template #value>
            <span :class="{ overdue: asset.current_checkout.is_overdue }">
              {{ fmtTime(asset.current_checkout.due_at) }}
            </span>
          </template>
        </van-cell>
      </van-cell-group>

      <!-- 主操作 -->
      <div class="actions">
        <template v-if="!asset.is_checked_out">
          <van-notice-bar
            v-if="asset.status !== 'in_stock'"
            wrapable
            :scrollable="false"
            left-icon="info-o"
            :text="`设备当前为「${asset.status_label}」,不可借出。`"
          />
          <template v-else>
            <van-cell-group inset>
              <van-field
                :model-value="dueLabel"
                label="预计归还"
                placeholder="可留空"
                readonly
                is-link
                @click="duePicker = true"
              />
            </van-cell-group>
            <van-button round block type="primary" :loading="acting" @click="doCheckout">
              借出到我名下
            </van-button>
          </template>
        </template>

        <template v-else>
          <van-button round block type="success" :loading="acting" @click="doCheckin">
            办理归还
          </van-button>
          <p class="muted tip">任何人都可以代为归还,系统会记录经办人。</p>
        </template>

        <van-button round block plain @click="checkVisible = true">盘库</van-button>

        <van-button
          v-if="!openRepair"
          round
          block
          plain
          type="danger"
          @click="repairVisible = true"
        >
          报修
        </van-button>

        <div class="row2">
          <van-button round block plain icon="qr" @click="qrVisible = true">标签</van-button>
          <van-button v-if="admin" round block plain icon="more-o" @click="moreVisible = true">
            更多
          </van-button>
        </div>
        <p v-if="asset.last_check" class="muted tip">
          上次盘库 {{ fmtTime(asset.last_check.checked_at) }} ·
          {{ displayName(asset.last_check.checked_by) }}
        </p>
        <p v-else class="muted tip">这台设备从未盘库</p>
      </div>

      <van-tabs v-model:active="tab" class="block">
        <van-tab title="借还历史">
          <van-empty v-if="!history.length" description="暂无借还记录" :image-size="60" />
          <van-cell-group v-else>
            <van-cell v-for="r in history" :key="r.id" :title="displayName(r.user)">
              <template #label>
                借出 {{ fmtTime(r.checked_out_at) }}
                <template v-if="r.checked_in_at"> · 归还 {{ fmtTime(r.checked_in_at) }}</template>
                <div v-if="r.checkin_operator && r.checkin_operator.id !== r.user.id">
                  经办人:{{ displayName(r.checkin_operator) }}
                </div>
              </template>
              <template #right-icon>
                <van-tag v-if="!r.checked_in_at" type="warning">未归还</van-tag>
              </template>
            </van-cell>
          </van-cell-group>
        </van-tab>

        <van-tab title="报修">
          <van-empty v-if="!repairs.length" description="没有报修记录" :image-size="60" />
          <van-cell-group v-else>
            <van-cell v-for="r in repairs" :key="r.id" :title="r.symptom">
              <template #label>
                {{ displayName(r.reported_by) }} 报于 {{ fmtTime(r.reported_at) }}
                <div v-if="r.vendor">送修:{{ r.vendor.name }}</div>
                <div v-if="r.cost_yuan !== null">费用:{{ r.cost_yuan }} 元
                  <span v-if="r.under_warranty">(保修)</span>
                </div>
              </template>
              <template #right-icon>
                <van-tag v-if="r.is_open" type="danger">维修中 {{ r.days_open }}天</van-tag>
                <van-tag v-else type="success">{{ r.result_label }}</van-tag>
              </template>
            </van-cell>
          </van-cell-group>
        </van-tab>

        <van-tab title="盘库记录">
          <van-empty v-if="!checks.length" description="暂无盘库记录" :image-size="60" />
          <van-cell-group v-else>
            <van-cell v-for="c in checks" :key="c.id" :title="displayName(c.checked_by)">
              <template #label>
                {{ fmtTime(c.checked_at) }}
                <template v-if="c.observed_location"> · {{ c.observed_location }}</template>
                <div v-if="c.note">{{ c.note }}</div>
              </template>
              <template #right-icon>
                <van-tag v-if="c.pending" type="danger">差异待处理</van-tag>
                <van-tag v-else-if="c.has_discrepancy" type="warning">已修正</van-tag>
                <van-tag v-else type="success">无误</van-tag>
              </template>
            </van-cell>
          </van-cell-group>
        </van-tab>
      </van-tabs>
    </template>

    <van-popup v-model:show="duePicker" position="bottom" round>
      <van-date-picker
        v-model="dueValue"
        title="预计归还日期"
        :min-date="today"
        @cancel="duePicker = false"
        @confirm="onDueConfirm"
      />
    </van-popup>

    <!-- 标签:补打、或现场核对条码扫不扫得出来 -->
    <van-popup v-model:show="qrVisible" round teleport="body">
      <div v-if="asset" class="qr">
        <img :src="labelSrc" alt="条码" class="qr__img" />
        <div class="qr__tag tag-mono">{{ asset.asset_tag }}</div>
        <div class="muted qr__code">条码号 {{ asset.barcode }}</div>
        <p class="muted qr__note">
          条码里只有那 6 位数字,没有链接也没有设备信息。标签上要同时印
          <b>{{ asset.asset_tag }}</b> —— 条码磨花了还能手输。
        </p>
      </div>
    </van-popup>

    <van-action-sheet
      v-model:show="moreVisible"
      :actions="moreActions"
      cancel-text="取消"
      close-on-click-action
      @select="onMore"
    />

    <RepairSheet v-model:show="repairVisible" :asset="asset" @done="load" />

    <CheckSheet v-model:show="checkVisible" :asset="asset" @done="load" />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ActionSheet as VanActionSheet,
  Button as VanButton,
  Cell as VanCell,
  CellGroup as VanCellGroup,
  DatePicker as VanDatePicker,
  Empty as VanEmpty,
  Field as VanField,
  NavBar as VanNavBar,
  NoticeBar as VanNoticeBar,
  Popup as VanPopup,
  Skeleton as VanSkeleton,
  Tab as VanTab,
  Tabs as VanTabs,
  Tag as VanTag,
  showConfirmDialog,
  showFailToast,
  showSuccessToast,
} from 'vant'

import CheckSheet from '../components/CheckSheet.vue'
import RepairSheet from '../components/RepairSheet.vue'
import { api, ApiError } from '../../api'
import { displayStatus, fmtTime } from '../../format'
import { displayName, isAdmin, markAssetsDirty } from '../../store'

const route = useRoute()
const router = useRouter()
const admin = isAdmin()

const qrVisible = ref(false)
const moreVisible = ref(false)
const moreActions = [
  { name: '编辑', key: 'edit' },
  { name: '复制为新设备', key: 'duplicate' },
  { name: '删除', key: 'delete', color: '#ee0a24' },
]

const asset = ref(null)
const history = ref([])
const checks = ref([])
const loading = ref(true)
const acting = ref(false)
const error = ref('')
const tab = ref(0)
const checkVisible = ref(false)
const repairVisible = ref(false)
const repairs = ref([])
const openRepair = computed(() => repairs.value.find((r) => r.is_open) || null)

const today = new Date()
const duePicker = ref(false)
const dueValue = ref([])
const dueAt = ref(null)

const badge = computed(() => displayStatus(asset.value))
const dueLabel = computed(() => (dueAt.value ? dueAt.value.toLocaleDateString('zh-CN') : ''))
const labelSrc = computed(() => (asset.value ? api.labelUrl(asset.value.id) : ''))

async function onMore(action) {
  if (action.key === 'edit') {
    router.push({ name: 'asset-edit', params: { id: asset.value.id } })
    return
  }
  if (action.key === 'duplicate') {
    router.push({ name: 'asset-new', query: { from: asset.value.id } })
    return
  }
  try {
    await showConfirmDialog({
      title: '删除设备',
      message: `确认删除「${asset.value.asset_tag} ${asset.value.name}」?删除后不再出现在台账中,借还与盘库历史仍保留。`,
      confirmButtonText: '删除',
      confirmButtonColor: '#ee0a24',
    })
  } catch {
    return
  }
  try {
    await api.deleteAsset(asset.value.id)
    showSuccessToast('已删除')
    markAssetsDirty()
    router.replace('/assets')
  } catch (err) {
    showFailToast(err instanceof ApiError ? err.detail : String(err))
  }
}

function onDueConfirm({ selectedValues }) {
  const [y, m, d] = selectedValues.map(Number)
  const date = new Date(y, m - 1, d, 18, 0, 0, 0) // 默认当天 18:00 下班前
  dueAt.value = date
  duePicker.value = false
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    asset.value = await api.getAssetByTag(route.params.tag)
    ;[history.value, checks.value, repairs.value] = await Promise.all([
      api.assetHistory(asset.value.id),
      api.assetChecks(asset.value.id),
      api.assetRepairs(asset.value.id),
    ])
  } catch (err) {
    asset.value = null
    error.value = err instanceof ApiError ? err.detail : '加载失败'
  } finally {
    loading.value = false
  }
}

async function doCheckout() {
  acting.value = true
  try {
    await api.checkout(asset.value.id, {
      due_at: dueAt.value ? dueAt.value.toISOString() : null,
    })
    showSuccessToast('已借出')
    dueAt.value = null
    await load()
  } catch (err) {
    showFailToast(err instanceof ApiError ? err.detail : String(err))
    // 并发场景下多半是被别人抢先借走了,刷新一次让页面反映真实状态
    if (err instanceof ApiError && err.status === 409) await load()
  } finally {
    acting.value = false
  }
}

async function doCheckin() {
  acting.value = true
  try {
    await api.checkin(asset.value.id, {})
    showSuccessToast('已归还')
    await load()
  } catch (err) {
    showFailToast(err instanceof ApiError ? err.detail : String(err))
    if (err instanceof ApiError && err.status === 409) await load()
  } finally {
    acting.value = false
  }
}

watch(() => route.params.tag, load, { immediate: true })
</script>

<style scoped>
.detail { padding-bottom: env(safe-area-inset-bottom); }
.hero { background: #1f2937; color: #fff; padding: 20px 16px 24px; }
.hero__tag { font-size: 13px; opacity: 0.7; }
.hero__name { font-size: 20px; font-weight: 600; margin: 4px 0 10px; }
.block { margin-top: 12px; }
.actions { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.tip { font-size: 12px; text-align: center; margin: 0; }
.row2 { display: flex; gap: 12px; }
.qr { padding: 24px; text-align: center; width: 300px; }
.qr__img { width: 100%; }
.qr__code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.qr__tag { font-size: 18px; font-weight: 600; margin: 10px 0; }
.qr__note { font-size: 12px; line-height: 1.6; text-align: left; margin: 0; }
.overdue { color: #ee0a24; font-weight: 600; }
.expired { color: #ee0a24; }
</style>

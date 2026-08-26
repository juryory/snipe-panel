<template>
  <!-- 移动版台账:搜索 + 卡片列表 + 上拉加载。手机上不再需要跳回桌面后台。 -->
  <div>
    <van-nav-bar title="设备台账">
      <template #right>
        <span @click="filterShow = true">
          筛选<span v-if="activeCount">({{ activeCount }})</span>
        </span>
      </template>
    </van-nav-bar>

    <van-search
      v-model="filters.q"
      placeholder="搜索编号 / 名称 / SN / 责任人"
      show-action
      @search="reload"
      @clear="reload"
    >
      <template #action><div @click="reload">搜索</div></template>
    </van-search>

    <div v-if="activeCount" class="chips">
      <van-tag
        v-for="chip in chips"
        :key="chip.key"
        closeable
        type="primary"
        size="medium"
        @close="clearOne(chip.key)"
      >
        {{ chip.label }}
      </van-tag>
    </div>

    <van-pull-refresh v-model="refreshing" @refresh="reload">
      <van-list
        v-model:loading="loading"
        :finished="finished"
        :finished-text="rows.length ? '没有更多了' : ''"
        :error="error"
        error-text="加载失败,点击重试"
        @load="loadMore"
      >
        <van-empty v-if="finished && !rows.length" description="没有符合条件的设备" />

        <div v-for="row in rows" :key="row.id" class="card" @click="open(row)">
          <div class="card__top">
            <div class="card__id">
              <div class="tag-mono muted">{{ row.asset_tag }}</div>
              <div class="card__name">{{ row.name }}</div>
            </div>
            <van-tag :type="badge(row).type" size="medium">{{ badge(row).label }}</van-tag>
          </div>
          <div class="card__meta muted">
            <div>
              {{ row.category_name }}
              <template v-if="row.brand || row.model">
                · {{ [row.brand, row.model].filter(Boolean).join(' ') }}
              </template>
            </div>
            <div v-if="row.location">位置:{{ row.location }}</div>
            <div v-if="row.owner">责任人:{{ displayName(row.owner) }}</div>
            <div v-if="row.current_checkout">
              借用人:{{ displayName(row.current_checkout.user) }}
            </div>
            <div>
              盘库:
              <template v-if="row.last_check">{{ fmtTime(row.last_check.checked_at) }}</template>
              <template v-else>从未盘库</template>
            </div>
          </div>
        </div>
      </van-list>
    </van-pull-refresh>

    <van-popup v-model:show="filterShow" position="bottom" round safe-area-inset-bottom>
      <div class="filter">
        <div class="filter__title">筛选</div>
        <van-cell-group inset>
          <van-field :model-value="labelOf('category')" label="分类" readonly is-link
            @click="openPicker('category')" />
          <van-field :model-value="labelOf('company')" label="采购公司" readonly is-link
            @click="openPicker('company')" />
          <van-field :model-value="labelOf('status')" label="状态" readonly is-link
            @click="openPicker('status')" />
          <van-field :model-value="labelOf('checked_out')" label="借出情况" readonly is-link
            @click="openPicker('checked_out')" />
          <van-field :model-value="labelOf('unchecked')" label="盘库情况" readonly is-link
            @click="openPicker('unchecked')" />
        </van-cell-group>
        <div class="filter__actions">
          <van-button block plain @click="resetFilters">重置</van-button>
          <van-button block type="primary" @click="applyFilters">查看结果</van-button>
        </div>
      </div>
    </van-popup>

    <van-popup v-model:show="pickerShow" position="bottom" round>
      <van-picker
        :columns="pickerColumns"
        @cancel="pickerShow = false"
        @confirm="onPick"
      />
    </van-popup>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Button as VanButton,
  CellGroup as VanCellGroup,
  Empty as VanEmpty,
  Field as VanField,
  List as VanList,
  NavBar as VanNavBar,
  Picker as VanPicker,
  Popup as VanPopup,
  PullRefresh as VanPullRefresh,
  Search as VanSearch,
  Tag as VanTag,
  showFailToast,
} from 'vant'

import { api, ApiError } from '../../api'
import { displayStatus, fmtTime } from '../../format'
import { displayName } from '../../store'

defineOptions({ name: 'MobileAssets' })

const PAGE_SIZE = 20
const router = useRouter()

const rows = ref([])
const page = ref(0)
const finished = ref(false)
const loading = ref(false)
const refreshing = ref(false)
const error = ref(false)

const categories = ref([])
const companies = ref([])
const filters = reactive({
  q: '',
  category_id: null,
  company_id: null,
  status: null,
  checked_out: null,
  unchecked_days: null,
})

const filterShow = ref(false)
const pickerShow = ref(false)
const pickerField = ref('')

const STATUS = [
  { text: '在库', value: 'in_stock' },
  { text: '维修', value: 'repair' },
  { text: '报废', value: 'retired' },
]
const BORROW = [
  { text: '借出中', value: true },
  { text: '未借出', value: false },
]
const UNCHECKED = [
  { text: '超 30 天未盘库', value: 30 },
  { text: '超 90 天未盘库', value: 90 },
  { text: '超 180 天未盘库', value: 180 },
]

const badge = (row) => displayStatus(row)

const activeCount = computed(
  () =>
    [
      filters.category_id,
      filters.company_id,
      filters.status,
      filters.checked_out,
      filters.unchecked_days,
    ].filter((v) => v !== null && v !== undefined).length,
)

const chips = computed(() => {
  const out = []
  if (filters.category_id !== null) out.push({ key: 'category', label: labelOf('category') })
  if (filters.company_id !== null) out.push({ key: 'company', label: labelOf('company') })
  if (filters.status !== null) out.push({ key: 'status', label: labelOf('status') })
  if (filters.checked_out !== null) out.push({ key: 'checked_out', label: labelOf('checked_out') })
  if (filters.unchecked_days !== null) out.push({ key: 'unchecked', label: labelOf('unchecked') })
  return out
})

function labelOf(field) {
  if (field === 'category') {
    const hit = categories.value.find((c) => c.id === filters.category_id)
    return hit ? hit.name : ''
  }
  if (field === 'company') {
    const hit = companies.value.find((c) => c.id === filters.company_id)
    return hit ? hit.name : ''
  }
  if (field === 'status') {
    const hit = STATUS.find((s) => s.value === filters.status)
    return hit ? hit.text : ''
  }
  if (field === 'checked_out') {
    const hit = BORROW.find((s) => s.value === filters.checked_out)
    return hit ? hit.text : ''
  }
  const hit = UNCHECKED.find((s) => s.value === filters.unchecked_days)
  return hit ? hit.text : ''
}

const pickerColumns = computed(() => {
  const clear = [{ text: '不限', value: null }]
  if (pickerField.value === 'category') {
    return clear.concat(categories.value.map((c) => ({ text: c.name, value: c.id })))
  }
  if (pickerField.value === 'company') {
    return clear.concat(companies.value.map((c) => ({ text: c.name, value: c.id })))
  }
  if (pickerField.value === 'status') return clear.concat(STATUS)
  if (pickerField.value === 'checked_out') return clear.concat(BORROW)
  return clear.concat(UNCHECKED)
})

function openPicker(field) {
  pickerField.value = field
  pickerShow.value = true
}

function onPick({ selectedOptions }) {
  const value = selectedOptions[0].value
  const map = {
    category: 'category_id',
    company: 'company_id',
    status: 'status',
    checked_out: 'checked_out',
    unchecked: 'unchecked_days',
  }
  filters[map[pickerField.value]] = value
  pickerShow.value = false
}

function clearOne(field) {
  const map = {
    category: 'category_id',
    company: 'company_id',
    status: 'status',
    checked_out: 'checked_out',
    unchecked: 'unchecked_days',
  }
  filters[map[field]] = null
  reload()
}

function applyFilters() {
  filterShow.value = false
  reload()
}

function resetFilters() {
  Object.assign(filters, {
    category_id: null,
    company_id: null,
    status: null,
    checked_out: null,
    unchecked_days: null,
  })
  filterShow.value = false
  reload()
}

/** 重新从第一页拉。van-list 靠 finished/loading 驱动,重置后它会自己触发 load。 */
function reload() {
  rows.value = []
  page.value = 0
  finished.value = false
  error.value = false
  loading.value = true
  loadMore()
}

async function loadMore() {
  try {
    const next = page.value + 1
    const data = await api.listAssets({
      q: filters.q,
      category_id: filters.category_id,
      company_id: filters.company_id,
      status: filters.status,
      checked_out: filters.checked_out,
      unchecked_days: filters.unchecked_days,
      page: next,
      page_size: PAGE_SIZE,
    })
    rows.value = next === 1 ? data.items : rows.value.concat(data.items)
    page.value = next
    finished.value = rows.value.length >= data.total
  } catch (err) {
    error.value = true
    showFailToast(err instanceof ApiError ? err.detail : String(err))
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function open(row) {
  router.push(`/a/${encodeURIComponent(row.asset_tag)}`)
}

onMounted(async () => {
  try {
    ;[categories.value, companies.value] = await Promise.all([
      api.listCategories(),
      api.listCompanies(),
    ])
  } catch {
    // 筛选项拉不到不影响浏览列表
  }
})
</script>

<style scoped>
.chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 16px 8px; }
.card {
  background: #fff;
  margin: 8px 12px;
  padding: 12px;
  border-radius: 8px;
}
.card__top { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; }
.card__id { min-width: 0; }
.card__name { font-weight: 600; margin-top: 2px; word-break: break-all; }
.card__meta { font-size: 12px; line-height: 1.9; margin-top: 6px; }
.filter { padding: 20px 0 16px; }
.filter__title { text-align: center; font-size: 17px; font-weight: 600; margin-bottom: 12px; }
.filter__actions { display: flex; gap: 12px; padding: 20px 16px 0; }
</style>

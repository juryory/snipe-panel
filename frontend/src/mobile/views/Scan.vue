<template>
  <!--
    PRD 3.4:首页即取景框 —— 打开页面摄像头就启动,不要先给菜单让人点。
    取景框正下方常驻手动输入编号入口(标签磨损、对焦失败、权限被拒时的兜底)。
  -->
  <div>
    <van-nav-bar :title="inventoryMode ? '盘库模式' : '扫码'" />

    <div class="pad">
      <van-notice-bar v-if="cameraError" wrapable :scrollable="false" left-icon="warning-o"
        :text="cameraError" />

      <QrScanner
        v-if="!cameraError"
        :key="continuous ? 'continuous' : 'single'"
        :continuous="continuous"
        @decode="onDecode"
        @error="(m) => (cameraError = m)"
      />

      <van-cell-group inset class="block">
        <van-cell title="连续扫码">
          <template #right-icon><van-switch v-model="continuous" size="22" /></template>
        </van-cell>
        <van-cell title="成套借用" :label="kitHint">
          <template #right-icon>
            <van-switch v-model="kitMode" size="22" :disabled="!continuous || inventoryMode" />
          </template>
        </van-cell>
        <van-cell title="盘库模式" :label="inventoryHint">
          <template #right-icon>
            <van-switch v-model="inventoryMode" size="22" :disabled="!continuous" />
          </template>
        </van-cell>
      </van-cell-group>

      <van-cell-group inset class="block">
        <van-field
          v-model="manualTag"
          center
          clearable
          label="编号"
          placeholder="例如 PC-0001"
          @keyup.enter="onManual"
        >
          <template #button>
            <van-button size="small" type="primary" :loading="looking" @click="onManual">
              {{ continuous ? '录入' : '查询' }}
            </van-button>
          </template>
        </van-field>
      </van-cell-group>
      <div class="muted hint">扫不出来?编号就印在条码下面,直接输进去。</div>

      <template v-if="continuous && scanned.length">
        <div class="listhead">
          <span>
            {{ inventoryMode ? `已盘 ${okCount} 台` : `已扫 ${scanned.length} 台` }}
            <span v-if="inventoryMode && failCount" class="fail">· {{ failCount }} 台未成功</span>
          </span>
          <van-button size="mini" plain type="danger" @click="scanned = []">清空</van-button>
        </div>

        <div v-if="kitMode && borrowable.length" class="kitbar">
          <van-button block round type="primary" :loading="borrowing" @click="borrowAll">
            把这 {{ borrowable.length }} 件一起借出
          </van-button>
          <div class="muted kitbar__hint">
            全有或全无:中间任何一件借不了就整批取消,不会借走一半。
          </div>
        </div>

        <van-cell-group inset>
          <van-cell v-for="item in scanned" :key="item.key" :border="true">
            <template #title>
              <span class="tag-mono">{{ item.tag }}</span>
              <van-tag v-if="item.state === 'checked'" type="success" style="margin-left: 6px">已盘</van-tag>
              <van-tag v-else-if="item.state === 'borrowed'" type="primary" style="margin-left: 6px">已借出</van-tag>
              <van-tag v-else-if="item.state === 'pending'" type="warning" style="margin-left: 6px">处理中</van-tag>
              <van-tag v-else-if="item.state === 'error'" type="danger" style="margin-left: 6px">失败</van-tag>
            </template>
            <template #label>
              <div>{{ item.name || item.error }}</div>
              <div v-if="item.location" class="muted">位置:{{ item.location }}</div>
            </template>
            <template #right-icon>
              <div v-if="item.asset" class="rowactions">
                <van-button size="mini" plain type="warning" @click="openFix(item)">有问题</van-button>
                <van-button size="mini" plain @click="$router.push(`/a/${item.tag}`)">详情</van-button>
              </div>
            </template>
          </van-cell>
        </van-cell-group>
      </template>
    </div>

    <CheckSheet v-model:show="fixVisible" :asset="fixAsset" @done="onFixed" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Button as VanButton,
  Cell as VanCell,
  CellGroup as VanCellGroup,
  Field as VanField,
  NavBar as VanNavBar,
  NoticeBar as VanNoticeBar,
  Switch as VanSwitch,
  Tag as VanTag,
  showFailToast,
  showSuccessToast,
  showToast,
} from 'vant'

import CheckSheet from '../components/CheckSheet.vue'
import QrScanner from '../../components/QrScanner.vue'
import { api, ApiError } from '../../api'

defineOptions({ name: 'MobileScan' })

const router = useRouter()

const cameraError = ref('')
const continuous = ref(false)
const inventoryMode = ref(false)
const scanned = ref([])
const manualTag = ref('')
const looking = ref(false)

const fixVisible = ref(false)
const fixAsset = ref(null)
let fixingKey = null

const okCount = computed(() => scanned.value.filter((i) => i.state === 'checked').length)
const failCount = computed(() => scanned.value.filter((i) => i.state === 'error').length)
const inventoryHint = computed(() =>
  continuous.value ? '扫到即记一条「确认无误」,对不上的点「有问题」再改' : '需要先打开连续扫码',
)
const kitHint = computed(() => {
  if (!continuous.value) return '需要先打开连续扫码'
  if (inventoryMode.value) return '盘库模式下不可用'
  return '扫齐相机、镜头、电池,再一次性借出'
})

const kitMode = ref(false)
const borrowing = ref(false)
// 已扫到、还没借出去、且当前可借的
const borrowable = computed(() =>
  scanned.value.filter((i) => i.asset && !i.asset.is_checked_out && i.state !== 'borrowed'),
)

async function borrowAll() {
  borrowing.value = true
  try {
    const items = borrowable.value
    await api.checkoutKit({ asset_ids: items.map((i) => i.asset.id) })
    items.forEach((i) => (i.state = 'borrowed'))
    showSuccessToast(`已借出 ${items.length} 件`)
  } catch (err) {
    showFailToast(err instanceof ApiError ? err.detail : String(err))
  } finally {
    borrowing.value = false
  }
}

async function onDecode(text) {
  if (continuous.value) {
    await collect(text)
    return
  }
  router.push(`/a/${encodeURIComponent(text)}`)
}

/**
 * 连续模式:留在本页逐条列出。
 * 盘库模式下顺手提交一条「确认无误」—— 盘点的真实动作是拿着手机连扫几百台,
 * 每台都点进详情再点盘库根本坚持不下来。
 */
async function collect(tag) {
  if (scanned.value.some((item) => item.tag === tag)) return
  const entry = {
    key: `${tag}-${Date.now()}`,
    tag,
    name: '',
    location: '',
    asset: null,
    error: '',
    state: 'pending',
  }
  scanned.value.unshift(entry)

  try {
    const asset = await api.getAssetByTag(tag)
    entry.asset = asset
    entry.name = asset.name
    entry.location = asset.location
    if (inventoryMode.value) {
      await api.checkAsset(asset.id, {}) // 空 body = 与台账一致
      entry.state = 'checked'
    } else {
      entry.state = 'found'
    }
  } catch (err) {
    entry.error = err instanceof ApiError ? err.detail : '失败'
    entry.state = 'error'
  }
}

async function onManual() {
  const tag = (manualTag.value || '').trim()
  if (!tag) {
    showToast('请输入资产编号')
    return
  }
  looking.value = true
  try {
    if (continuous.value) {
      await collect(tag)
      manualTag.value = ''
    } else {
      // 先查一次,编号不存在就地提示,免得跳进详情页再报错
      await api.getAssetByTag(tag)
      router.push(`/a/${encodeURIComponent(tag)}`)
    }
  } catch (err) {
    showFailToast(err instanceof ApiError ? err.detail : String(err))
  } finally {
    looking.value = false
  }
}

function openFix(item) {
  fixAsset.value = item.asset
  fixingKey = item.key
  fixVisible.value = true
}

function onFixed() {
  const item = scanned.value.find((i) => i.key === fixingKey)
  if (item) item.state = 'checked'
  fixingKey = null
}
</script>

<style scoped>
.block { margin-top: 12px; }
.hint { font-size: 12px; padding: 8px 16px 0; line-height: 1.6; }
.listhead {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 16px 8px;
  font-weight: 600;
}
.rowactions { display: flex; gap: 6px; align-items: center; }
.kitbar { padding: 0 16px 12px; }
.kitbar__hint { font-size: 12px; line-height: 1.6; margin-top: 8px; text-align: center; }
.fail { color: #ee0a24; font-weight: normal; }
</style>

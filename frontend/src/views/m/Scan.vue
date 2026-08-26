<template>
  <!--
    PRD 3.4:移动端首页即取景框 —— 打开页面摄像头就启动,不要先给菜单让人点。
    取景框正下方常驻手动输入编号入口(标签磨损、对焦失败、权限被拒时的兜底)。
  -->
  <div class="m-page stack">
    <div class="row-between">
      <strong>{{ inventoryMode ? '盘库' : '扫码' }}</strong>
      <div>
        <el-button link @click="$router.push('/m/mine')">我的设备</el-button>
        <el-dropdown @command="onAccount">
          <el-button link type="primary">{{ myName }} ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="install">装到手机桌面</el-dropdown-item>
              <el-dropdown-item v-if="admin" command="admin">后台管理</el-dropdown-item>
              <el-dropdown-item command="password">修改密码</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <el-alert v-if="cameraError" type="warning" :closable="false" show-icon :title="cameraError" />

    <QrScanner
      v-if="!cameraError"
      ref="scanner"
      :key="continuous ? 'continuous' : 'single'"
      :continuous="continuous"
      @decode="onDecode"
      @error="onCameraError"
    />

    <el-card shadow="never">
      <div class="row-between">
        <el-checkbox v-model="continuous">连续扫码</el-checkbox>
        <el-checkbox v-model="inventoryMode" :disabled="!continuous">盘库模式</el-checkbox>
      </div>
      <div v-if="inventoryMode" class="muted hint">
        每扫到一台就直接记一条「确认无误」的盘库。位置或状态对不上的,点那一行的
        「有问题」再改。
      </div>
      <div v-else-if="continuous" class="muted hint">扫到的设备会列在下面,不跳转。</div>
    </el-card>

    <el-card shadow="never">
      <div class="muted manual__label">扫不出来?直接输编号(印在二维码右边)</div>
      <div class="manual">
        <el-input
          v-model="manualTag"
          placeholder="例如 PC-0001"
          size="large"
          clearable
          @keyup.enter="onManual"
        />
        <el-button type="primary" size="large" :loading="looking" @click="onManual">
          {{ continuous ? '录入' : '查询' }}
        </el-button>
      </div>
    </el-card>

    <template v-if="continuous && scanned.length">
      <div class="row-between">
        <div class="m-title" style="margin: 0">
          {{ inventoryMode ? `已盘 ${okCount} 台` : `已扫 ${scanned.length} 台` }}
          <span v-if="inventoryMode && failCount" class="fail"> · {{ failCount }} 台未成功</span>
        </div>
        <el-button link type="danger" @click="scanned = []">清空</el-button>
      </div>

      <el-card v-for="item in scanned" :key="item.key" shadow="never" class="hit">
        <div class="row-between">
          <div class="hit__main">
            <div class="hit__tag">
              {{ item.tag }}
              <el-tag v-if="item.state === 'checked'" size="small" type="success">已盘</el-tag>
              <el-tag v-else-if="item.state === 'pending'" size="small" type="warning">处理中</el-tag>
              <el-tag v-else-if="item.state === 'error'" size="small" type="danger">失败</el-tag>
            </div>
            <div class="muted small">{{ item.name || item.error }}</div>
            <div v-if="item.location" class="muted small">位置:{{ item.location }}</div>
          </div>
          <div class="hit__actions">
            <el-button v-if="item.asset" link type="warning" @click="openFix(item)">有问题</el-button>
            <el-button v-if="item.asset" link type="primary" @click="$router.push(`/m/a/${item.tag}`)">
              详情
            </el-button>
          </div>
        </div>
      </el-card>
    </template>

    <CheckDialog v-model="fixVisible" :asset="fixAsset" narrow @done="onFixed" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import CheckDialog from '../../components/CheckDialog.vue'
import QrScanner from '../../components/QrScanner.vue'
import { api, toast } from '../../api'
import { displayName, isAdmin, session } from '../../store'

const router = useRouter()
const admin = isAdmin()
const myName = computed(() => displayName(session.user))

const scanner = ref(null)
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

function onCameraError(message) {
  cameraError.value = message
}

async function onDecode(text) {
  if (continuous.value) {
    await collect(text)
    return
  }
  router.push(`/m/a/${encodeURIComponent(text)}`)
}

/**
 * 连续模式:留在本页逐条列出。
 * 盘库模式下顺手提交一条「确认无误」的盘库 —— 盘点的真实动作是拿着手机连扫
 * 几百台,每台都点进详情再点盘库根本坚持不下来。
 */
async function collect(tag) {
  const existing = scanned.value.find((item) => item.tag === tag)
  if (existing) return
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
      // 空 body = 与台账一致
      await api.checkAsset(asset.id, {})
      entry.state = 'checked'
    } else {
      entry.state = 'found'
    }
  } catch (err) {
    entry.error = err.detail || '失败'
    entry.state = 'error'
  }
}

async function onManual() {
  const tag = (manualTag.value || '').trim()
  if (!tag) {
    ElMessage.warning('请输入资产编号')
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
      router.push(`/m/a/${encodeURIComponent(tag)}`)
    }
  } catch (err) {
    toast(err)
  } finally {
    looking.value = false
  }
}

/** 移动端此前没有任何退出入口 —— 普通用户看不到后台的导航栏,只能清缓存。 */
async function onAccount(command) {
  if (command === 'install') {
    router.push({ name: 'm-install' })
    return
  }
  if (command === 'admin') {
    router.push('/admin/assets')
    return
  }
  if (command === 'password') {
    router.push({ name: 'change-password' })
    return
  }
  try {
    await api.logout()
  } catch (err) {
    toast(err)
  }
  session.user = null
  router.replace({ name: 'login' })
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
.manual { display: flex; gap: 8px; }
.manual__label { font-size: 13px; margin-bottom: 8px; }
.hint { font-size: 12px; line-height: 1.6; margin-top: 8px; }
.hit + .hit { margin-top: 8px; }
.hit__main { min-width: 0; }
.hit__tag {
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  display: flex;
  align-items: center;
  gap: 6px;
}
.hit__actions { white-space: nowrap; }
.small { font-size: 12px; }
.fail { color: #f56c6c; }
</style>

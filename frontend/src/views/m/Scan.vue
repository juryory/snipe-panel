<template>
  <!--
    PRD 3.4:移动端首页即取景框 —— 打开页面摄像头就启动,不要先给菜单让人点。
    取景框正下方常驻手动输入编号入口(标签磨损、对焦失败、权限被拒时的兜底)。
  -->
  <div class="m-page stack">
    <div class="row-between">
      <strong>扫码</strong>
      <div>
        <el-button link @click="$router.push('/m/mine')">我的设备</el-button>
        <el-button v-if="admin" link @click="$router.push('/admin/assets')">后台</el-button>
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

    <div class="row-between">
      <el-checkbox v-model="continuous">连续扫码(盘点用)</el-checkbox>
      <el-button v-if="continuous && scanned.length" link type="danger" @click="scanned = []">
        清空({{ scanned.length }})
      </el-button>
    </div>

    <el-card shadow="never">
      <div class="muted manual__label">扫不出来?直接输编号(印在二维码右边)</div>
      <div class="manual">
        <el-input
          v-model="manualTag"
          placeholder="例如 PC-0001"
          size="large"
          clearable
          @keyup.enter="openTag(manualTag)"
        />
        <el-button type="primary" size="large" :loading="looking" @click="openTag(manualTag)">
          查询
        </el-button>
      </div>
    </el-card>

    <template v-if="continuous && scanned.length">
      <div class="m-title">已扫 {{ scanned.length }} 台</div>
      <el-card v-for="item in scanned" :key="item.key" shadow="never" class="hit">
        <div class="row-between">
          <div>
            <div class="hit__tag">{{ item.tag }}</div>
            <div class="muted">{{ item.name || item.error }}</div>
          </div>
          <el-button v-if="item.id" link type="primary" @click="$router.push(`/m/a/${item.tag}`)">
            详情
          </el-button>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import QrScanner from '../../components/QrScanner.vue'
import { api, toast } from '../../api'
import { isAdmin } from '../../store'

const router = useRouter()
const admin = isAdmin()

const scanner = ref(null)
const cameraError = ref('')
const continuous = ref(false)
const scanned = ref([])
const manualTag = ref('')
const looking = ref(false)

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

/** 连续扫码:留在本页,把扫到的设备逐条列出来(PRD 3.4 盘点场景)。 */
async function collect(tag) {
  if (scanned.value.some((item) => item.tag === tag)) return
  const entry = { key: `${tag}-${Date.now()}`, tag, name: '', id: null, error: '' }
  scanned.value.unshift(entry)
  try {
    const asset = await api.getAssetByTag(tag)
    entry.id = asset.id
    entry.name = asset.name
  } catch (err) {
    entry.error = err.detail || '查询失败'
  }
}

async function openTag(raw) {
  const tag = (raw || '').trim()
  if (!tag) {
    ElMessage.warning('请输入资产编号')
    return
  }
  looking.value = true
  try {
    // 先查一次,编号不存在就地提示,免得跳进详情页再报错
    await api.getAssetByTag(tag)
    router.push(`/m/a/${encodeURIComponent(tag)}`)
  } catch (err) {
    toast(err)
  } finally {
    looking.value = false
  }
}
</script>

<style scoped>
.manual { display: flex; gap: 8px; }
.manual__label { font-size: 13px; margin-bottom: 8px; }
.hit + .hit { margin-top: 8px; }
.hit__tag { font-weight: 600; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>

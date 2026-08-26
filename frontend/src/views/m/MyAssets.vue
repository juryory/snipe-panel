<template>
  <!-- 我名下的设备 = 我借出未还的 + 我是长期责任人的(PRD 3.1 两种流转模式)。 -->
  <div class="m-page stack">
    <div class="row-between">
      <el-button link @click="$router.push('/m')">‹ 扫码</el-button>
      <strong>我的设备</strong>
      <span style="width: 48px"></span>
    </div>

    <el-skeleton v-if="loading" :rows="4" animated />
    <el-empty v-else-if="!assets.length" description="名下暂无设备" />

    <el-card v-for="asset in assets" :key="asset.id" shadow="never" @click="open(asset)">
      <div class="row-between">
        <div>
          <div class="tag">{{ asset.asset_tag }}</div>
          <div class="name">{{ asset.name }}</div>
          <div class="muted kind">{{ kindOf(asset) }}</div>
        </div>
        <el-tag :type="displayStatus(asset).type">{{ displayStatus(asset).label }}</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api, toast } from '../../api'
import { displayStatus } from '../../format'
import { session } from '../../store'

const router = useRouter()
const assets = ref([])
const loading = ref(true)

function kindOf(asset) {
  const mine = session.user && asset.owner && asset.owner.id === session.user.id
  if (mine && asset.is_checked_out) return '长期归属 · 借出中'
  if (mine) return '长期归属'
  return '临时借用'
}

function open(asset) {
  router.push(`/m/a/${encodeURIComponent(asset.asset_tag)}`)
}

onMounted(async () => {
  try {
    assets.value = await api.myAssets()
  } catch (err) {
    toast(err)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.tag { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #6b7280; font-size: 13px; }
.name { font-weight: 600; margin-top: 2px; }
.kind { font-size: 12px; margin-top: 2px; }
</style>

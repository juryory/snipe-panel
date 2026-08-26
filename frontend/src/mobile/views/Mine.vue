<template>
  <div>
    <van-nav-bar title="我的" />

    <div class="profile">
      <div class="profile__avatar">{{ initial }}</div>
      <div class="profile__info">
        <div class="profile__name">
          {{ name }}
          <van-tag v-if="admin" type="warning">管理员</van-tag>
        </div>
        <div class="profile__sub muted">
          {{ session.user ? session.user.username : '' }}
          <template v-if="session.user && session.user.department">
            · {{ session.user.department }}
          </template>
        </div>
      </div>
    </div>

    <van-cell-group inset class="block">
      <van-cell title="我名下的设备" :value="`${assets.length} 台`" is-link @click="listShow = true" />
    </van-cell-group>

    <van-cell-group inset class="block">
      <van-cell title="装到手机桌面" is-link icon="down" @click="$router.push('/install')" />
      <van-cell title="修改密码" is-link icon="lock" @click="$router.push('/change-password')" />
      <van-cell v-if="admin" title="后台管理" is-link icon="setting-o" @click="toAdmin" />
    </van-cell-group>

    <div class="logout">
      <van-button block round type="danger" plain @click="logout">退出登录</van-button>
    </div>

    <van-popup v-model:show="listShow" position="bottom" round :style="{ height: '72%' }"
      safe-area-inset-bottom>
      <div class="sheet">
        <div class="sheet__title">我名下的设备</div>
        <p class="muted sheet__sub">包含我借出未还的,以及我是长期责任人的</p>
        <van-empty v-if="!assets.length" description="名下暂无设备" />
        <van-cell-group v-else>
          <van-cell
            v-for="a in assets"
            :key="a.id"
            is-link
            @click="open(a)"
          >
            <template #title>
              <span class="tag-mono muted">{{ a.asset_tag }}</span>
              <div class="sheet__name">{{ a.name }}</div>
            </template>
            <template #label>{{ kindOf(a) }}</template>
            <template #right-icon>
              <van-tag :type="displayStatus(a).type">{{ displayStatus(a).label }}</van-tag>
            </template>
          </van-cell>
        </van-cell-group>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Button as VanButton,
  Cell as VanCell,
  CellGroup as VanCellGroup,
  Empty as VanEmpty,
  NavBar as VanNavBar,
  Popup as VanPopup,
  Tag as VanTag,
  showConfirmDialog,
  showFailToast,
} from 'vant'

import { api, ApiError } from '../../api'
import { displayStatus } from '../../format'
import { displayName, isAdmin, session } from '../../store'

const router = useRouter()
const admin = isAdmin()
const assets = ref([])
const listShow = ref(false)

const name = computed(() => displayName(session.user))
const initial = computed(() => (name.value || '?').slice(0, 1))

function kindOf(asset) {
  const mine = session.user && asset.owner && asset.owner.id === session.user.id
  if (mine && asset.is_checked_out) return '长期归属 · 借出中'
  if (mine) return '长期归属'
  return '临时借用'
}

function open(asset) {
  listShow.value = false
  router.push(`/a/${encodeURIComponent(asset.asset_tag)}`)
}

/** 后台是另一个入口(index.html),必须整页跳转,不能走前端路由。 */
function toAdmin() {
  window.location.href = '/admin/assets'
}

async function logout() {
  try {
    await showConfirmDialog({ title: '退出登录', message: '确认退出当前账号?' })
  } catch {
    return
  }
  try {
    await api.logout()
  } catch {
    // 退出接口失败也要把本地状态清掉,不然会卡在登录态
  }
  session.user = null
  router.replace({ name: 'login' })
}

onMounted(async () => {
  try {
    assets.value = await api.myAssets()
  } catch (err) {
    showFailToast(err instanceof ApiError ? err.detail : String(err))
  }
})
</script>

<style scoped>
.profile { display: flex; align-items: center; gap: 14px; padding: 20px 16px; background: #fff; }
.profile__avatar {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: #1f2937;
  color: #fff;
  font-size: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.profile__name { font-size: 17px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.profile__sub { font-size: 12px; margin-top: 4px; }
.block { margin-top: 12px; }
.logout { padding: 24px 16px; }
.sheet { padding: 20px 0; }
.sheet__title { text-align: center; font-size: 17px; font-weight: 600; }
.sheet__sub { text-align: center; font-size: 12px; margin: 4px 0 12px; }
.sheet__name { font-weight: 600; margin-top: 2px; }
</style>

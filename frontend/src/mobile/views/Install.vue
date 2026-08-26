<template>
  <!--
    PRD 3.4:「添加到主屏幕」引导。
    二维码里没有 URL,员工无法用微信扫一扫直接进来,必须先打开本系统 ——
    装到桌面是降低这个摩擦最有效的一招。
  -->
  <div>
    <van-nav-bar title="装到手机桌面" left-arrow @click-left="$router.back()" />

    <van-notice-bar v-if="installed" left-icon="passed" wrapable :scrollable="false"
      text="已经是桌面应用模式,不用再装了。" />

    <div v-else-if="canPrompt" class="pad">
      <van-button round block type="primary" @click="promptInstall">安装到桌面</van-button>
    </div>

    <van-cell-group inset class="block">
      <van-cell title="装了有什么好处" />
      <div class="body">
        <ul>
          <li>桌面有独立图标,不用记网址、不用翻书签</li>
          <li>打开就是扫码取景框,少两步</li>
          <li>全屏运行,没有浏览器地址栏挤占屏幕</li>
          <li>前端资源本地缓存,二次打开快很多</li>
        </ul>
      </div>
    </van-cell-group>

    <van-cell-group inset class="block">
      <van-cell title="iPhone / iPad(Safari)" />
      <div class="body">
        <ol>
          <li><b>必须用 Safari 打开</b>,微信或 Chrome 里都装不了</li>
          <li>点底部中间的「分享」按钮(方框向上箭头)</li>
          <li>菜单里向下滑,找到「<b>添加到主屏幕</b>」</li>
          <li>右上角点「添加」</li>
        </ol>
        <p class="muted">
          装好后第一次打开需要重新登录一次 —— iOS 上桌面应用和 Safari
          的登录状态是分开的。
        </p>
      </div>
    </van-cell-group>

    <van-cell-group inset class="block">
      <van-cell title="安卓(Chrome / Edge)" />
      <div class="body">
        <ol>
          <li>用 Chrome 打开本页面</li>
          <li>点右上角「⋮」菜单</li>
          <li>选「<b>安装应用</b>」或「添加到主屏幕」</li>
          <li>确认安装</li>
        </ol>
        <p class="muted">国产手机自带浏览器和微信内置浏览器大多不支持,请换用 Chrome。</p>
      </div>
    </van-cell-group>

    <van-cell-group inset class="block">
      <van-cell title="装不了 / 摄像头打不开?" />
      <div class="body">
        <p class="muted">
          两者都要求页面通过 <b>HTTPS</b> 访问。如果地址栏是 http:// 开头或带着
          IP 地址,浏览器会同时禁掉安装和摄像头 —— 这是浏览器的硬性规定,
          不是系统故障。请用公司配发的正式域名打开。
        </p>
        <p class="muted">
          摄像头实在用不了也不影响干活:扫码页一直有「手动输入编号」,
          编号就印在二维码右边。
        </p>
      </div>
    </van-cell-group>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import {
  Button as VanButton,
  Cell as VanCell,
  CellGroup as VanCellGroup,
  NavBar as VanNavBar,
  NoticeBar as VanNoticeBar,
} from 'vant'

const canPrompt = ref(false)
const installed = ref(false)
let deferred = null

function onBeforeInstallPrompt(e) {
  // Chrome 满足安装条件时抛这个事件,拦下来自己控制时机
  e.preventDefault()
  deferred = e
  canPrompt.value = true
}

async function promptInstall() {
  if (!deferred) return
  deferred.prompt()
  const { outcome } = await deferred.userChoice
  if (outcome === 'accepted') installed.value = true
  deferred = null
  canPrompt.value = false
}

onMounted(() => {
  installed.value =
    window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true
  window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt)
})

onBeforeUnmount(() => window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt))
</script>

<style scoped>
.block { margin-top: 12px; }
.body { padding: 0 16px 16px; font-size: 14px; line-height: 1.9; }
.body ul, .body ol { margin: 0; padding-left: 20px; }
.body p { margin: 10px 0 0; font-size: 13px; line-height: 1.7; }
</style>

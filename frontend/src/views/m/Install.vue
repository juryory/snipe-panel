<template>
  <!--
    PRD 3.4:「添加到主屏幕」图文引导。
    二维码里没有 URL,员工无法用微信扫一扫直接进来,必须先打开本系统 ——
    所以「怎么让人无摩擦地打开」是这个模块的核心,装到桌面是最有效的一招。
  -->
  <div class="m-page stack">
    <div class="row-between">
      <el-button link @click="$router.back()">‹ 返回</el-button>
      <strong>装到手机桌面</strong>
      <span style="width: 48px"></span>
    </div>

    <el-alert v-if="installed" type="success" :closable="false" show-icon
      title="已经是桌面应用模式,不用再装了。" />

    <el-card v-else-if="canPrompt" shadow="never">
      <p class="lead">你的浏览器支持一键安装。</p>
      <el-button type="primary" size="large" style="width: 100%" @click="promptInstall">
        安装到桌面
      </el-button>
    </el-card>

    <el-card shadow="never">
      <div class="m-title" style="margin-top: 0">装了有什么好处</div>
      <ul class="list">
        <li>桌面有独立图标,不用记网址、不用翻浏览器书签</li>
        <li>打开就是扫码取景框,少两步</li>
        <li>全屏运行,没有浏览器地址栏挤占屏幕</li>
        <li>前端资源本地缓存,二次打开快很多</li>
      </ul>
    </el-card>

    <el-card shadow="never">
      <div class="m-title" style="margin-top: 0">iPhone / iPad(Safari)</div>
      <ol class="list">
        <li><strong>必须用 Safari 打开</strong>,微信或 Chrome 里都装不了</li>
        <li>点底部中间的「分享」按钮(方框向上箭头)</li>
        <li>在菜单里向下滑,找到「<strong>添加到主屏幕</strong>」</li>
        <li>右上角点「添加」</li>
      </ol>
      <el-alert type="info" :closable="false" show-icon style="margin-top: 8px"
        title="装好后第一次打开需要重新登录一次 —— iOS 上桌面应用和 Safari 的登录状态是分开的。" />
    </el-card>

    <el-card shadow="never">
      <div class="m-title" style="margin-top: 0">安卓(Chrome / Edge)</div>
      <ol class="list">
        <li>用 Chrome 打开本页面</li>
        <li>点右上角「⋮」菜单</li>
        <li>选「<strong>安装应用</strong>」或「添加到主屏幕」</li>
        <li>确认安装</li>
      </ol>
      <p class="muted note">
        国产手机自带浏览器(以及微信内置浏览器)大多不支持,请换用 Chrome。
      </p>
    </el-card>

    <el-card shadow="never">
      <div class="m-title" style="margin-top: 0">装不了 / 摄像头打不开?</div>
      <p class="muted note">
        两者都要求页面通过 <strong>HTTPS</strong> 访问。如果地址栏是
        <code>http://</code> 开头或带着 IP 地址,浏览器会同时禁掉安装和摄像头 ——
        这是浏览器的硬性规定,不是系统故障。请用公司配发的正式域名打开。
      </p>
      <p class="muted note">
        摄像头实在用不了也不影响干活:扫码页下方一直有「手动输入编号」,
        编号就印在二维码右边。
      </p>
    </el-card>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const canPrompt = ref(false)
const installed = ref(false)
let deferred = null

function onBeforeInstallPrompt(e) {
  // Chrome 会在满足安装条件时抛这个事件,拦下来自己控制时机
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
  // standalone 说明已经是从桌面图标打开的
  installed.value =
    window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true
  window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt)
})
</script>

<style scoped>
.lead { margin: 0 0 12px; }
.list { margin: 0; padding-left: 20px; line-height: 1.9; }
.note { font-size: 13px; line-height: 1.7; }
code { background: #f0f0f0; padding: 1px 4px; border-radius: 3px; }
</style>

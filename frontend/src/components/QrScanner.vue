<template>
  <!--
    取景框。PRD 3.4:
    - 优先用浏览器原生 BarcodeDetector(Android Chrome 支持,性能最佳)
    - 不支持或不认这些码制时回退 @zxing/browser
    - 摄像头需要安全上下文(HTTPS 或 localhost),否则 getUserMedia 直接抛错

    只认 QR:资产标签是我们自己印的,限定单一码制能少很多误读 —— 设备上往往
    还贴着厂商的条码,放开码制在盘库连扫时很容易扫错东西。
  -->
  <div class="scanner">
    <video ref="videoEl" class="scanner__video" playsinline muted autoplay></video>
    <div class="scanner__frame"></div>
    <p v-if="hint" class="scanner__hint">{{ hint }}</p>
  </div>
</template>

<script setup>
import { onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'

const props = defineProps({
  // 连续扫描:扫完不停,继续扫下一台(PRD 3.4,盘点用)
  continuous: { type: Boolean, default: false },
})
const emit = defineEmits(['decode', 'error'])

const videoEl = ref(null)
const hint = ref('正在启动摄像头…')

let stream = null
let zxingControls = null
let rafId = null
let stopped = false
let lastText = ''
let lastAt = 0

// 摄像头当前是否已开。start/stop 会被多个来源触发(挂载、keep-alive 激活、
// 页面重新可见),不去重的话会同时开出好几路流。
let running = false
// 组件是否处于「应该开着摄像头」的状态。被 keep-alive 切走后置 false,
// 这样即便此时页面重新可见也不该偷偷把摄像头打开。
let active = false

function handleDecode(text) {
  const value = (text || '').trim()
  if (!value) return
  // 同一个码 1.5 秒内只上报一次,否则连续扫描模式会疯狂重复触发
  const now = Date.now()
  if (value === lastText && now - lastAt < 1500) return
  lastText = value
  lastAt = now

  if (navigator.vibrate) navigator.vibrate(60)
  emit('decode', value)
  if (!props.continuous) stop()
}

async function useBarcodeDetector() {
  if (!('BarcodeDetector' in window)) return false
  let supported = []
  try {
    supported = await window.BarcodeDetector.getSupportedFormats()
  } catch {
    return false
  }
  if (!supported.includes('qr_code')) return false

  const detector = new window.BarcodeDetector({ formats: ['qr_code'] })
  const tick = async () => {
    if (stopped) return
    try {
      const codes = await detector.detect(videoEl.value)
      if (codes.length) handleDecode(codes[0].rawValue)
    } catch {
      // 单帧解析失败无所谓,继续下一帧
    }
    if (!stopped) rafId = requestAnimationFrame(tick)
  }
  rafId = requestAnimationFrame(tick)
  return true
}


async function useZxing() {
  const { BrowserQRCodeReader } = await import('@zxing/browser')
  const reader = new BrowserQRCodeReader()
  zxingControls = await reader.decodeFromVideoElement(videoEl.value, (result) => {
    if (result) handleDecode(result.getText())
  })
}


async function start() {
  if (running) return
  running = true
  stopped = false
  hint.value = '正在启动摄像头…'
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    running = false
    // 最常见的原因是页面不在 HTTPS 下(PRD 3.4)
    hint.value = ''
    emit('error', '当前浏览器无法调用摄像头。请确认页面通过 HTTPS 打开,或改用手动输入编号。')
    return
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    })
    // 等待期间可能已经被切走了(keep-alive 或切到别的 App),这时要把
    // 刚拿到的流立刻还回去,否则摄像头会在后台一直亮着
    if (!active) {
      stream.getTracks().forEach((t) => t.stop())
      stream = null
      running = false
      return
    }
    videoEl.value.srcObject = stream
    await videoEl.value.play()
  } catch (err) {
    running = false
    hint.value = ''
    const denied = err && err.name === 'NotAllowedError'
    emit(
      'error',
      denied
        ? '摄像头权限被拒绝。请在浏览器设置中允许访问摄像头,或改用手动输入。'
        : `无法打开摄像头(${(err && err.name) || '未知错误'})。请改用手动输入。`,
    )
    return
  }

  hint.value = '将二维码对准取景框'
  const native = await useBarcodeDetector()
  if (!native) {
    try {
      await useZxing()
    } catch (err) {
      hint.value = ''
      emit('error', `扫码组件启动失败:${(err && err.message) || err}`)
    }
  }
}

/** 切到别的 App 或锁屏时系统会回收摄像头,回来时 video 上挂的是条死流,画面全黑。 */
function onVisibilityChange() {
  if (document.hidden) {
    stop()
  } else if (active) {
    start()
  }
}

function stop() {
  stopped = true
  running = false
  if (rafId) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
  if (zxingControls) {
    zxingControls.stop()
    zxingControls = null
  }
  if (stream) {
    stream.getTracks().forEach((t) => t.stop())
    stream = null
  }
  if (videoEl.value) videoEl.value.srcObject = null
}

onMounted(() => {
  active = true
  start()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

// keep-alive 下的扫码页:切走时组件不销毁,onBeforeUnmount 不会触发,
// 不在这里关掉的话摄像头会一直在后台占着;切回来时 onMounted 也不再执行,
// 而 keep-alive 会把 DOM 摘出文档,<video> 一脱离文档就暂停 —— 回来就是黑屏。
onActivated(() => {
  active = true
  start()
})
onDeactivated(() => {
  active = false
  stop()
})

onBeforeUnmount(() => {
  active = false
  stop()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})

defineExpose({ start, stop })
</script>

<style scoped>
.scanner {
  position: relative;
  width: 100%;
  aspect-ratio: 3 / 4;
  max-height: 58vh;
  background: #000;
  border-radius: 12px;
  overflow: hidden;
}
.scanner__video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.scanner__frame {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 62%;
  aspect-ratio: 1;
  border: 3px solid rgba(255, 255, 255, 0.9);
  border-radius: 10px;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.35);
}
.scanner__hint {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 12px;
  margin: 0;
  text-align: center;
  color: #fff;
  font-size: 14px;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
}
</style>

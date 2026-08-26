<template>
  <!--
    取景框。PRD 3.4:
    - 优先用浏览器原生 BarcodeDetector(Android Chrome 支持,性能最佳)
    - 不支持或不认这些码制时回退 @zxing/browser
    - 摄像头需要安全上下文(HTTPS 或 localhost),否则 getUserMedia 直接抛错

    formats 默认只认 QR:资产标签是我们自己印的,限定单一码制能少很多误读。
    录序列号则要放开 —— 厂商贴的 SN 条码什么码制都有(一维码、DataMatrix)。
  -->
  <div class="scanner">
    <video ref="videoEl" class="scanner__video" playsinline muted autoplay></video>
    <div class="scanner__frame" :class="{ 'scanner__frame--wide': wideFrame }"></div>
    <p v-if="hint" class="scanner__hint">{{ hint }}</p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  // 连续扫描:扫完不停,继续扫下一台(PRD 3.4,盘点用)
  continuous: { type: Boolean, default: false },
  // BarcodeDetector 的码制名,ZXing 那边会映射过去
  formats: { type: Array, default: () => ['qr_code'] },
})
const emit = defineEmits(['decode', 'error'])

const videoEl = ref(null)
const hint = ref('正在启动摄像头…')

// 只扫方形码时用方形取景框;带一维码时用宽框,否则会让人以为要把长条塞进方框
const wideFrame = computed(() =>
  props.formats.some((f) => !['qr_code', 'data_matrix', 'aztec'].includes(f)),
)

let stream = null
let zxingControls = null
let rafId = null
let stopped = false
let lastText = ''
let lastAt = 0

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
  const usable = props.formats.filter((f) => supported.includes(f))
  // 只支持一部分码制时也不能用 —— 漏掉的那种扫不出来,用户只会以为是坏的
  if (usable.length !== props.formats.length) return false

  const detector = new window.BarcodeDetector({ formats: usable })
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
  const [{ BrowserMultiFormatReader, BrowserQRCodeReader }, { BarcodeFormat, DecodeHintType }] =
    await Promise.all([import('@zxing/browser'), import('@zxing/library')])

  let reader
  if (props.formats.length === 1 && props.formats[0] === 'qr_code') {
    reader = new BrowserQRCodeReader()
  } else {
    const nameToFormat = {
      qr_code: BarcodeFormat.QR_CODE,
      data_matrix: BarcodeFormat.DATA_MATRIX,
      aztec: BarcodeFormat.AZTEC,
      pdf417: BarcodeFormat.PDF_417,
      code_128: BarcodeFormat.CODE_128,
      code_39: BarcodeFormat.CODE_39,
      code_93: BarcodeFormat.CODE_93,
      codabar: BarcodeFormat.CODABAR,
      itf: BarcodeFormat.ITF,
      ean_13: BarcodeFormat.EAN_13,
      ean_8: BarcodeFormat.EAN_8,
      upc_a: BarcodeFormat.UPC_A,
      upc_e: BarcodeFormat.UPC_E,
    }
    const wanted = props.formats.map((f) => nameToFormat[f]).filter((f) => f !== undefined)
    const hints = new Map()
    hints.set(DecodeHintType.POSSIBLE_FORMATS, wanted)
    // DataMatrix 和小尺寸一维码不开 TRY_HARDER 基本扫不出来
    hints.set(DecodeHintType.TRY_HARDER, true)
    reader = new BrowserMultiFormatReader(hints)
  }

  zxingControls = await reader.decodeFromVideoElement(videoEl.value, (result) => {
    if (result) handleDecode(result.getText())
  })
}

async function start() {
  stopped = false
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    // 最常见的原因是页面不在 HTTPS 下(PRD 3.4)
    hint.value = ''
    emit('error', '当前浏览器无法调用摄像头。请确认页面通过 HTTPS 打开,或改用手动输入。')
    return
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    })
    videoEl.value.srcObject = stream
    await videoEl.value.play()
  } catch (err) {
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

  hint.value = wideFrame.value ? '把条码对准取景框' : '将二维码对准取景框'
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

function stop() {
  stopped = true
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

onMounted(start)
onBeforeUnmount(stop)
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
.scanner__frame--wide {
  width: 82%;
  aspect-ratio: 5 / 2;
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

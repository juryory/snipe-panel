<template>
  <!--
    输入框 + 扫码按钮。用于录序列号:厂商贴的 SN 条码码制五花八门
    (一维 Code128 / Code39、二维码、DataMatrix),所以这里放开码制。
  -->
  <div class="scan-input">
    <el-input
      :model-value="modelValue"
      :placeholder="placeholder"
      clearable
      @update:model-value="(v) => emit('update:modelValue', v)"
    />
    <el-button @click="open">扫码</el-button>

    <el-dialog v-model="visible" :title="title" width="420px" @closed="onClosed">
      <el-alert v-if="error" type="warning" :closable="false" show-icon :title="error" />
      <QrScanner
        v-else-if="visible"
        :key="scannerKey"
        :formats="FORMATS"
        continuous
        @decode="onDecode"
        @error="(m) => (error = m)"
      />
      <div class="muted hint">
        支持条形码、二维码、DataMatrix。扫到后会填入输入框,可再手动修改。
      </div>
      <div v-if="lastHit" class="hit">已扫到:<strong>{{ lastHit }}</strong></div>
      <template #footer>
        <el-button @click="visible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import QrScanner from './QrScanner.vue'

defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  title: { type: String, default: '扫码录入' },
})
const emit = defineEmits(['update:modelValue'])

// 常见的设备铭牌码制。放开太多会拖慢 ZXing 并增加误读,这几种覆盖绝大多数情况
const FORMATS = [
  'qr_code',
  'data_matrix',
  'code_128',
  'code_39',
  'code_93',
  'itf',
  'ean_13',
  'ean_8',
  'upc_a',
  'upc_e',
]

const visible = ref(false)
const error = ref('')
const lastHit = ref('')
const scannerKey = ref(0)

function open() {
  error.value = ''
  lastHit.value = ''
  scannerKey.value += 1 // 重新挂载,确保摄像头重新启动
  visible.value = true
}

function onDecode(text) {
  lastHit.value = text
  emit('update:modelValue', text)
  ElMessage.success(`已录入 ${text}`)
}

function onClosed() {
  error.value = ''
  lastHit.value = ''
}
</script>

<style scoped>
.scan-input { display: flex; gap: 8px; width: 100%; }
.hint { font-size: 12px; line-height: 1.6; margin-top: 8px; }
.hit { margin-top: 8px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>

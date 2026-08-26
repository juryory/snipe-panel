<template>
  <!--
    序列号输入 + 扫码。厂商贴的 SN 条码码制五花八门,所以这里放开一维码、
    二维码和 DataMatrix —— 与扫资产标签那个刻意只认 QR 的扫码器不同。
  -->
  <div>
    <van-field
      :model-value="modelValue"
      :label="fieldLabel"
      :placeholder="placeholder"
      clearable
      @update:model-value="(v) => emit('update:modelValue', v)"
    >
      <template #button>
        <van-button size="small" type="primary" plain @click="open">扫码</van-button>
      </template>
    </van-field>

    <van-popup v-model:show="show" position="bottom" round safe-area-inset-bottom teleport="body">
      <div class="sheet">
        <div class="sheet__title">扫序列号</div>
        <van-notice-bar v-if="error" wrapable :scrollable="false" left-icon="warning-o"
          :text="error" />
        <div v-else class="sheet__cam">
          <QrScanner :key="scanKey" :formats="FORMATS" continuous @decode="onDecode"
            @error="(m) => (error = m)" />
        </div>
        <p class="muted sheet__hint">
          支持条形码、二维码、DataMatrix。扫到会填进输入框,之后还能手改。
        </p>
        <p v-if="hit" class="sheet__hit">已扫到:<b class="tag-mono">{{ hit }}</b></p>
        <div class="sheet__actions">
          <van-button block round @click="show = false">完成</van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import {
  Button as VanButton,
  Field as VanField,
  NoticeBar as VanNoticeBar,
  Popup as VanPopup,
  showSuccessToast,
} from 'vant'

import QrScanner from '../../components/QrScanner.vue'

defineProps({
  modelValue: { type: String, default: '' },
  fieldLabel: { type: String, default: '序列号' },
  placeholder: { type: String, default: '可手输,或点扫码' },
})
const emit = defineEmits(['update:modelValue'])

// 常见的设备铭牌码制。放太多会拖慢 ZXing 并增加误读,这几种覆盖绝大多数情况
const FORMATS = [
  'qr_code', 'data_matrix', 'code_128', 'code_39', 'code_93',
  'itf', 'ean_13', 'ean_8', 'upc_a', 'upc_e',
]

const show = ref(false)
const error = ref('')
const hit = ref('')
const scanKey = ref(0)

function open() {
  error.value = ''
  hit.value = ''
  scanKey.value += 1 // 重新挂载,确保摄像头重新启动
  show.value = true
}

function onDecode(text) {
  hit.value = text
  emit('update:modelValue', text)
  showSuccessToast(`已录入 ${text}`)
}
</script>

<style scoped>
.sheet { padding: 20px 0 16px; }
.sheet__title { text-align: center; font-size: 17px; font-weight: 600; margin-bottom: 12px; }
.sheet__cam { padding: 0 16px; }
.sheet__hint { font-size: 12px; padding: 10px 20px 0; line-height: 1.6; margin: 0; }
.sheet__hit { text-align: center; margin: 8px 0 0; }
.sheet__actions { padding: 16px 16px 0; }
</style>

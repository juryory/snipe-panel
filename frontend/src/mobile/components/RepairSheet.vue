<template>
  <!-- 报修。发现设备坏的往往是借用人,所以任何登录用户都能提。 -->
  <van-popup
    :show="show"
    position="bottom"
    round
    safe-area-inset-bottom
    @update:show="(v) => emit('update:show', v)"
  >
    <div v-if="asset" class="sheet">
      <div class="sheet__title">
        报修 · <span class="tag-mono">{{ asset.asset_tag }}</span>
      </div>
      <div class="muted sheet__sub">{{ asset.name }}</div>

      <van-notice-bar
        v-if="asset.warranty_valid"
        left-icon="passed"
        wrapable
        :scrollable="false"
        :text="`保修到 ${asset.warranty_until},本次维修按保修处理`"
      />
      <van-notice-bar
        v-else-if="asset.warranty_valid === false"
        left-icon="info-o"
        wrapable
        :scrollable="false"
        :text="`保修已于 ${asset.warranty_until} 到期,本次维修可能自费`"
      />
      <van-notice-bar
        v-if="asset.is_checked_out"
        left-icon="info-o"
        wrapable
        :scrollable="false"
        text="设备正借出中。报修会先记下来,归还时才转为「维修」状态。"
      />

      <van-cell-group inset style="margin-top: 12px">
        <van-field
          v-model="form.symptom"
          label="故障描述"
          type="textarea"
          rows="3"
          autosize
          maxlength="500"
          show-word-limit
          placeholder="哪里坏了、什么情况下出现的"
        />
        <PickerField
          v-model="form.vendor_id"
          field-label="送修厂商"
          :options="vendorOptions"
          clearable
          placeholder="暂不指定"
        />
      </van-cell-group>
      <div class="muted sheet__hint">
        厂商可以之后再补。默认会带出这台设备的采购公司 —— 报修多半就找他们。
      </div>

      <div class="sheet__actions">
        <van-button block round type="danger" :loading="saving" :disabled="!form.symptom.trim()"
          @click="submit">
          提交报修
        </van-button>
      </div>
    </div>
  </van-popup>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  Button as VanButton,
  CellGroup as VanCellGroup,
  Field as VanField,
  NoticeBar as VanNoticeBar,
  Popup as VanPopup,
  showFailToast,
  showSuccessToast,
} from 'vant'

import PickerField from './PickerField.vue'
import { api, ApiError } from '../../api'

const props = defineProps({
  show: { type: Boolean, default: false },
  asset: { type: Object, default: null },
})
const emit = defineEmits(['update:show', 'done'])

const saving = ref(false)
const companies = ref([])
const form = reactive({ symptom: '', vendor_id: null })

const vendorOptions = computed(() =>
  companies.value.map((c) => ({ text: c.name, value: c.id })),
)

watch(
  () => [props.show, props.asset],
  async () => {
    if (!props.show || !props.asset) return
    form.symptom = ''
    // 报修默认找当初的采购公司
    form.vendor_id = props.asset.company ? props.asset.company.id : null
    if (!companies.value.length) {
      try {
        companies.value = await api.listCompanies()
      } catch {
        // 厂商列表拉不到不影响报修,之后可以再补
      }
    }
  },
  { immediate: true },
)

async function submit() {
  saving.value = true
  try {
    const record = await api.reportRepair(props.asset.id, {
      symptom: form.symptom.trim(),
      vendor_id: form.vendor_id,
    })
    showSuccessToast('已提交报修')
    emit('update:show', false)
    emit('done', record)
  } catch (err) {
    showFailToast(err instanceof ApiError ? err.detail : String(err))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.sheet { padding: 20px 0 16px; }
.sheet__title { font-size: 17px; font-weight: 600; text-align: center; }
.sheet__sub { text-align: center; font-size: 13px; margin: 4px 0 12px; }
.sheet__hint { font-size: 12px; padding: 8px 20px 0; line-height: 1.6; }
.sheet__actions { padding: 20px 16px 0; }
</style>

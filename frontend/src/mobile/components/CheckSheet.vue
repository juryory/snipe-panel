<template>
  <!--
    盘库表单(底部弹层)。位置/状态默认填台账现值 —— 绝大多数情况直接点
    「确认无误」就行,只有对不上时才改。
  -->
  <van-popup
    :show="show"
    position="bottom"
    round
    safe-area-inset-bottom
    @update:show="(v) => emit('update:show', v)"
  >
    <div v-if="asset" class="sheet">
      <div class="sheet__title">
        盘库 · <span class="tag-mono">{{ asset.asset_tag }}</span>
      </div>
      <div class="muted sheet__sub">{{ asset.name }}</div>

      <van-notice-bar
        v-if="asset.is_checked_out"
        wrapable
        :scrollable="false"
        left-icon="info-o"
        :text="`当前借给 ${displayName(asset.current_checkout.user)},在其手上盘到属于正常情况`"
      />
      <van-notice-bar
        v-if="!isAdminUser"
        wrapable
        :scrollable="false"
        left-icon="warning-o"
        text="你提交的差异会先挂起,由管理员确认后才写入台账。"
      />

      <van-cell-group inset style="margin-top: 12px">
        <van-field v-model="form.location" label="实际位置" placeholder="与台账一致就不用改" />
        <van-field
          :model-value="statusLabel"
          label="实际状态"
          readonly
          is-link
          :disabled="asset.is_checked_out"
          @click="!asset.is_checked_out && (statusPicker = true)"
        />
        <van-field
          v-model="form.note"
          label="使用情况"
          type="textarea"
          rows="2"
          autosize
          placeholder="外观磨损、功能异常、附件缺失等,没有就留空"
        />
      </van-cell-group>

      <div v-if="asset.is_checked_out" class="muted sheet__hint">
        设备借出中,状态不可修改 —— 借出中改状态会与未归还记录矛盾。
      </div>
      <div v-else-if="changed" class="sheet__hint sheet__hint--warn">
        与台账不一致,将记为差异。
      </div>

      <div class="sheet__actions">
        <van-button block round type="primary" :loading="saving" @click="submit">
          {{ changed ? '提交差异' : '确认无误' }}
        </van-button>
      </div>
    </div>

    <van-popup v-model:show="statusPicker" position="bottom" round>
      <van-picker
        :columns="STATUS_OPTIONS"
        @cancel="statusPicker = false"
        @confirm="onPickStatus"
      />
    </van-popup>
  </van-popup>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  Button as VanButton,
  CellGroup as VanCellGroup,
  Field as VanField,
  NoticeBar as VanNoticeBar,
  Picker as VanPicker,
  Popup as VanPopup,
  showFailToast,
  showSuccessToast,
  showToast,
} from 'vant'

import { api, ApiError } from '../../api'
import { displayName, isAdmin } from '../../store'

const STATUS_OPTIONS = [
  { text: '在库', value: 'in_stock' },
  { text: '维修', value: 'repair' },
  { text: '报废', value: 'retired' },
]

const props = defineProps({
  show: { type: Boolean, default: false },
  asset: { type: Object, default: null },
})
const emit = defineEmits(['update:show', 'done'])

const isAdminUser = isAdmin()
const saving = ref(false)
const statusPicker = ref(false)
const form = reactive({ location: '', status: 'in_stock', note: '' })

const statusLabel = computed(
  () => (STATUS_OPTIONS.find((o) => o.value === form.status) || {}).text || '',
)
const changed = computed(
  () =>
    props.asset &&
    (form.location !== (props.asset.location || '') || form.status !== props.asset.status),
)

// 每次打开都用台账现值重置,避免带上一台设备的残留
watch(
  () => [props.show, props.asset],
  () => {
    if (props.show && props.asset) {
      form.location = props.asset.location || ''
      form.status = props.asset.status
      form.note = ''
    }
  },
  { immediate: true },
)

function onPickStatus({ selectedOptions }) {
  form.status = selectedOptions[0].value
  statusPicker.value = false
}

async function submit() {
  saving.value = true
  try {
    const result = await api.checkAsset(props.asset.id, {
      observed_location: form.location,
      observed_status: form.status,
      note: form.note,
    })
    if (!result.has_discrepancy) showSuccessToast('已记录盘库')
    else if (result.applied) showSuccessToast('已记录并更新台账')
    else showToast('已记录差异,等管理员确认后写入台账')
    emit('update:show', false)
    emit('done', result)
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
.sheet__hint--warn { color: #ff976a; }
.sheet__actions { padding: 20px 16px 0; }
</style>

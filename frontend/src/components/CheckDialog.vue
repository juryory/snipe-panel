<template>
  <!--
    盘库表单。桌面后台和移动详情页共用。
    位置/状态留空即「与台账一致」,所以默认值直接填台账现值 —— 大多数情况
    直接点确认就行,只有对不上时才改。
  -->
  <el-dialog
    :model-value="modelValue"
    :title="asset ? `盘库 · ${asset.asset_tag}` : '盘库'"
    :width="narrow ? '92%' : '480px'"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <template v-if="asset">
      <div class="head">
        <strong>{{ asset.name }}</strong>
        <span class="muted"> · {{ asset.category_name }}</span>
      </div>

      <el-alert
        v-if="asset.is_checked_out"
        type="info"
        :closable="false"
        show-icon
        :title="`当前借给 ${displayName(asset.current_checkout.user)},在其手上盘到属于正常情况`"
        style="margin-bottom: 12px"
      />
      <el-alert
        v-if="!isAdminUser"
        type="warning"
        :closable="false"
        show-icon
        title="你提交的差异会先挂起,由管理员确认后才会写入台账。"
        style="margin-bottom: 12px"
      />

      <el-form :model="form" label-width="90px">
        <el-form-item label="实际位置">
          <el-input v-model="form.observed_location" placeholder="留空表示与台账一致" />
          <div v-if="locationChanged" class="muted hint">
            台账原为「{{ asset.location || '（空）' }}」,将记为差异
          </div>
        </el-form-item>

        <el-form-item label="实际状态">
          <el-select v-model="form.observed_status" style="width: 100%" :disabled="asset.is_checked_out">
            <el-option label="在库" value="in_stock" />
            <el-option label="维修" value="repair" />
            <el-option label="报废" value="retired" />
          </el-select>
          <div v-if="asset.is_checked_out" class="muted hint">
            设备借出中,状态不可在此修改（借出中改状态会与未归还记录矛盾）。
          </div>
          <div v-else-if="statusChanged" class="muted hint">
            台账原为「{{ asset.status_label }}」,将记为差异
          </div>
        </el-form-item>

        <el-form-item label="使用情况">
          <el-input
            v-model="form.note"
            type="textarea"
            :rows="2"
            placeholder="外观磨损、功能异常、附件缺失等,没有就留空"
          />
        </el-form-item>
      </el-form>
    </template>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">
        {{ hasChange ? '提交差异' : '确认无误' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { api, toast } from '../api'
import { displayName, isAdmin } from '../store'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  asset: { type: Object, default: null },
  narrow: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'done'])

const isAdminUser = isAdmin()
const saving = ref(false)
const form = reactive({ observed_location: '', observed_status: 'in_stock', note: '' })

const locationChanged = computed(
  () => props.asset && form.observed_location !== props.asset.location,
)
const statusChanged = computed(
  () => props.asset && form.observed_status !== props.asset.status,
)
const hasChange = computed(() => locationChanged.value || statusChanged.value)

// 每次打开都用台账现值重置,避免带上一台设备的残留
watch(
  () => [props.modelValue, props.asset],
  () => {
    if (props.modelValue && props.asset) {
      form.observed_location = props.asset.location || ''
      form.observed_status = props.asset.status
      form.note = ''
    }
  },
  { immediate: true },
)

async function submit() {
  saving.value = true
  try {
    const result = await api.checkAsset(props.asset.id, {
      observed_location: form.observed_location,
      observed_status: form.observed_status,
      note: form.note,
    })
    if (!result.has_discrepancy) {
      ElMessage.success('已记录盘库')
    } else if (result.applied) {
      ElMessage.success('已记录并更新台账')
    } else {
      ElMessage.warning('已记录差异,等管理员确认后写入台账')
    }
    emit('update:modelValue', false)
    emit('done', result)
  } catch (err) {
    toast(err)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.head { margin-bottom: 12px; }
.hint { font-size: 12px; line-height: 1.6; margin-top: 4px; }
</style>

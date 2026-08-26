<template>
  <!-- 只读输入框 + 底部选择器。表单里要选四五个东西,不抽出来会重复一堆模板。 -->
  <div>
    <van-field
      :model-value="label"
      :label="fieldLabel"
      :placeholder="placeholder"
      :required="required"
      readonly
      is-link
      @click="show = true"
    />
    <van-popup v-model:show="show" position="bottom" round teleport="body">
      <van-picker
        :title="fieldLabel"
        :columns="columns"
        :model-value="modelValue === null || modelValue === undefined ? [] : [modelValue]"
        @cancel="show = false"
        @confirm="onConfirm"
      />
    </van-popup>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Field as VanField, Picker as VanPicker, Popup as VanPopup } from 'vant'

const props = defineProps({
  modelValue: { type: [String, Number, Boolean, null], default: null },
  fieldLabel: { type: String, required: true },
  // [{ text, value }]
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '请选择' },
  required: { type: Boolean, default: false },
  // 允许「不指定」,选项顶部会多一条
  clearable: { type: Boolean, default: false },
  clearText: { type: String, default: '不指定' },
})
const emit = defineEmits(['update:modelValue'])

const show = ref(false)

const columns = computed(() =>
  props.clearable
    ? [{ text: props.clearText, value: null }].concat(props.options)
    : props.options,
)

const label = computed(() => {
  const hit = props.options.find((o) => o.value === props.modelValue)
  return hit ? hit.text : ''
})

function onConfirm({ selectedOptions }) {
  emit('update:modelValue', selectedOptions[0] ? selectedOptions[0].value : null)
  show.value = false
}
</script>

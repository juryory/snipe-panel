<template>
  <!--
    新增 / 编辑 / 复制设备。手机上用整页表单而不是弹层 —— 字段有十来个,
    弹层里滚动 + 唤起键盘会挤成一团。
  -->
  <div class="form">
    <van-nav-bar :title="title" left-arrow @click-left="$router.back()" />

    <van-skeleton v-if="loading" title :row="8" style="padding: 20px" />

    <van-form v-else @submit="submit">
      <van-cell-group inset class="block">
        <van-field
          v-model="form.name"
          label="设备名称"
          placeholder="如 ThinkPad X1 Carbon"
          required
          :rules="[{ required: true, message: '请填写设备名称' }]"
        />
        <PickerField
          v-model="form.category_id"
          field-label="分类"
          :options="categoryOptions"
          required
        />
        <van-field
          v-if="!editing"
          v-model="form.asset_tag"
          label="资产编号"
          placeholder="留空自动生成"
        />
        <van-field v-else label="资产编号" :model-value="form.asset_tag" readonly />
      </van-cell-group>

      <div class="muted hint">
        <template v-if="editing">编号一经生成不可修改 —— 标签已经贴在设备上了。</template>
        <template v-else-if="mode === 'duplicate'">
          已从「{{ sourceTag }}」复制字段。序列号没有带过来:SN 是每台实物独有的,
          复制过去会造出两台 SN 相同的设备。
        </template>
        <template v-else>
          只有导入存量设备、需要沿用旧编号时才填编号,否则留空按分类前缀自动生成。
        </template>
      </div>

      <van-cell-group inset class="block">
        <van-field v-model="form.brand" label="品牌" placeholder="如 Lenovo" />
        <van-field v-model="form.model" label="型号" placeholder="如 Gen11" />
        <van-field v-model="form.serial_no" label="序列号" placeholder="设备铭牌上的 SN" />
        <van-field v-model="form.location" label="存放位置" placeholder="如 库房 A" />
      </van-cell-group>

      <van-cell-group inset class="block">
        <PickerField
          v-model="form.owner_user_id"
          field-label="长期责任人"
          :options="userOptions"
          clearable
          placeholder="不指定"
        />
        <PickerField
          v-model="form.company_id"
          field-label="采购公司"
          :options="companyOptions"
          clearable
          placeholder="不指定"
        />
        <van-field
          :model-value="form.purchased_at || ''"
          label="采购日期"
          placeholder="不指定"
          readonly
          is-link
          @click="openDate('purchased_at')"
        />
        <van-field
          :model-value="form.warranty_until || ''"
          label="保修到期"
          placeholder="不指定"
          readonly
          is-link
          @click="openDate('warranty_until')"
        />
        <PickerField
          v-if="editing"
          v-model="form.status"
          field-label="状态"
          :options="STATUS"
        />
      </van-cell-group>

      <div v-if="editing" class="muted hint">
        「借出」不是设备状态,由借还记录决定,这里选不到。
      </div>
      <div class="muted hint">长期责任人是长期归属(如员工笔记本),借还流程不会修改它。</div>

      <van-cell-group inset class="block">
        <van-field
          v-model="form.note"
          label="备注"
          type="textarea"
          rows="2"
          autosize
          placeholder="选填"
        />
      </van-cell-group>

      <div class="actions">
        <van-button round block type="primary" native-type="submit" :loading="saving">
          保存
        </van-button>
      </div>
    </van-form>

    <van-popup v-model:show="datePicker" position="bottom" round teleport="body">
      <van-date-picker
        :title="dateField === 'purchased_at' ? '采购日期' : '保修到期'"
        :min-date="minDate"
        :max-date="maxDate"
        @cancel="datePicker = false"
        @confirm="onDate"
      />
    </van-popup>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Button as VanButton,
  CellGroup as VanCellGroup,
  DatePicker as VanDatePicker,
  Field as VanField,
  Form as VanForm,
  NavBar as VanNavBar,
  Popup as VanPopup,
  Skeleton as VanSkeleton,
  showFailToast,
  showSuccessToast,
  showToast,
} from 'vant'

import PickerField from '../components/PickerField.vue'
import { api, ApiError } from '../../api'
import { displayName, markAssetsDirty } from '../../store'

const STATUS = [
  { text: '在库', value: 'in_stock' },
  { text: '维修', value: 'repair' },
  { text: '报废', value: 'retired' },
]

const route = useRoute()
const router = useRouter()

const minDate = new Date(2000, 0, 1)
const maxDate = new Date(new Date().getFullYear() + 20, 11, 31)

const loading = ref(true)
const saving = ref(false)
const datePicker = ref(false)
const sourceTag = ref('')

const categories = ref([])
const companies = ref([])
const users = ref([])

// mode: create | edit | duplicate
const mode = computed(() => {
  if (route.name === 'asset-edit') return 'edit'
  return route.query.from ? 'duplicate' : 'create'
})
const editing = computed(() => mode.value === 'edit')
const title = computed(
  () => ({ edit: '编辑设备', duplicate: '复制设备', create: '新增设备' })[mode.value],
)

const form = reactive({
  id: null,
  asset_tag: '',
  name: '',
  category_id: null,
  brand: '',
  model: '',
  serial_no: '',
  location: '',
  owner_user_id: null,
  company_id: null,
  status: 'in_stock',
  purchased_at: null,
  warranty_until: null,
  note: '',
})

const categoryOptions = computed(() =>
  categories.value.map((c) => ({ text: `${c.name}(${c.tag_prefix})`, value: c.id })),
)
const companyOptions = computed(() =>
  companies.value.map((c) => ({ text: c.name, value: c.id })),
)
const userOptions = computed(() => users.value.map((u) => ({ text: displayName(u), value: u.id })))

const dateField = ref('purchased_at')

function openDate(field) {
  dateField.value = field
  datePicker.value = true
}

function onDate({ selectedValues }) {
  form[dateField.value] = selectedValues.join('-')
  datePicker.value = false
}

function fill(asset, { keepIdentity }) {
  Object.assign(form, {
    id: keepIdentity ? asset.id : null,
    asset_tag: keepIdentity ? asset.asset_tag : '',
    name: asset.name,
    category_id: asset.category_id,
    brand: asset.brand,
    model: asset.model,
    // 复制时不带 SN:每台实物的 SN 独有,复制过去报修保修会分不清是哪台
    serial_no: keepIdentity ? asset.serial_no : '',
    location: asset.location,
    owner_user_id: asset.owner ? asset.owner.id : null,
    company_id: asset.company ? asset.company.id : null,
    status: asset.status,
    purchased_at: asset.purchased_at,
    warranty_until: asset.warranty_until,
    note: asset.note,
  })
}

async function submit() {
  if (!form.category_id) {
    showToast('请选择分类')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      // asset_tag 不提交 —— 编号一经生成永不变更
      const { id, asset_tag, ...body } = form
      await api.updateAsset(id, body)
      showSuccessToast('已保存')
    } else {
      const { id, status, ...body } = form
      if (!body.asset_tag) delete body.asset_tag
      const created = await api.createAsset(body)
      showSuccessToast(`已创建 ${created.asset_tag}`)
    }
    markAssetsDirty()
    router.back()
  } catch (err) {
    showFailToast(err instanceof ApiError ? err.detail : String(err))
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    ;[categories.value, companies.value, users.value] = await Promise.all([
      api.listCategories(),
      api.listCompanies(),
      api.listUsers(''),
    ])
    const sourceId = route.params.id || route.query.from
    if (sourceId) {
      const asset = await api.getAsset(sourceId)
      sourceTag.value = asset.asset_tag
      fill(asset, { keepIdentity: editing.value })
    } else if (categories.value.length === 1) {
      form.category_id = categories.value[0].id
    }
  } catch (err) {
    showFailToast(err instanceof ApiError ? err.detail : String(err))
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.form { padding-bottom: calc(24px + env(safe-area-inset-bottom)); }
.block { margin-top: 12px; }
.hint { font-size: 12px; line-height: 1.7; padding: 8px 20px 0; }
.actions { padding: 24px 16px 0; }
</style>

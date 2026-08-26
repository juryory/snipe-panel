<template>
  <div class="stack">
    <el-card shadow="never">
      <div class="filters">
        <el-input
          v-model="filters.q"
          placeholder="搜索编号 / 名称 / SN / 责任人"
          clearable
          style="width: 260px"
          @keyup.enter="reload(1)"
          @clear="reload(1)"
        />
        <el-select v-model="filters.category_id" placeholder="全部分类" clearable style="width: 140px" @change="reload(1)">
          <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-select v-model="filters.company_id" placeholder="全部采购公司" clearable filterable style="width: 170px" @change="reload(1)">
          <el-option v-for="c in companies" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 130px" @change="reload(1)">
          <el-option label="在库" value="in_stock" />
          <el-option label="维修" value="repair" />
          <el-option label="报废" value="retired" />
        </el-select>
        <el-select v-model="filters.checked_out" placeholder="借出情况" clearable style="width: 130px" @change="reload(1)">
          <el-option label="借出中" :value="true" />
          <el-option label="未借出" :value="false" />
        </el-select>
        <el-button type="primary" @click="reload(1)">查询</el-button>

        <div class="filters__spacer"></div>

        <el-button :disabled="!selection.length" @click="exportSelected('csv')">
          导出编号 CSV({{ selection.length }})
        </el-button>
        <el-button :disabled="!selection.length" @click="exportSelected('zip')">导出二维码</el-button>
        <el-button v-if="admin" type="primary" @click="openForm()">新增设备</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table
        v-loading="loading"
        :data="rows"
        row-key="id"
        @selection-change="(rows) => (selection = rows)"
      >
        <el-table-column type="selection" width="46" />
        <el-table-column label="资产编号" width="120">
          <template #default="{ row }"><span class="tag">{{ row.asset_tag }}</span></template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="category_name" label="分类" width="100" />
        <el-table-column label="品牌型号" min-width="140">
          <template #default="{ row }">{{ [row.brand, row.model].filter(Boolean).join(' ') || '—' }}</template>
        </el-table-column>
        <el-table-column prop="serial_no" label="序列号" min-width="140" show-overflow-tooltip />
        <el-table-column label="采购公司" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.company ? row.company.name : '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="displayStatus(row).type" size="small">{{ displayStatus(row).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="责任人 / 借用人" min-width="150">
          <template #default="{ row }">
            <div v-if="row.owner">{{ displayName(row.owner) }}<span class="muted"> (长期)</span></div>
            <div v-if="row.current_checkout">
              {{ displayName(row.current_checkout.user) }}<span class="muted"> (借用)</span>
            </div>
            <span v-if="!row.owner && !row.current_checkout">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="showQr(row)">二维码</el-button>
            <el-button v-if="!row.is_checked_out" link type="primary" @click="openCheckout(row)">借出</el-button>
            <el-button v-else link type="success" @click="doCheckin(row)">归还</el-button>
            <el-button v-if="admin" link type="primary" @click="openForm(row)">编辑</el-button>
            <el-button v-if="admin" link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        style="margin-top: 12px; justify-content: flex-end"
        layout="total, sizes, prev, pager, next"
        :total="total"
        :current-page="page"
        :page-size="pageSize"
        :page-sizes="[20, 50, 100]"
        @current-change="reload"
        @size-change="(size) => { pageSize = size; reload(1) }"
      />
    </el-card>

    <!-- 新增 / 编辑 -->
    <el-dialog v-model="formVisible" :title="editing ? '编辑设备' : '新增设备'" width="560px">
      <el-form :model="form" label-width="96px">
        <el-form-item label="设备名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="分类" required>
          <el-select v-model="form.category_id" style="width: 100%">
            <el-option v-for="c in categories" :key="c.id" :label="`${c.name}(${c.tag_prefix})`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!editing" label="资产编号">
          <el-input v-model="form.asset_tag" placeholder="留空则按分类前缀自动生成" />
          <div class="muted hint">只有导入存量设备、需要沿用旧编号时才填。编号一经生成不可修改。</div>
        </el-form-item>
        <el-form-item v-else label="资产编号">
          <span class="tag">{{ form.asset_tag }}</span>
          <span class="muted hint" style="margin-left: 8px">标签已贴在设备上,不可修改</span>
        </el-form-item>
        <el-form-item label="品牌">
          <el-input v-model="form.brand" />
        </el-form-item>
        <el-form-item label="型号">
          <el-input v-model="form.model" />
        </el-form-item>
        <el-form-item label="序列号">
          <el-input v-model="form.serial_no" />
        </el-form-item>
        <el-form-item label="存放位置">
          <el-input v-model="form.location" />
        </el-form-item>
        <el-form-item label="长期责任人">
          <el-select v-model="form.owner_user_id" clearable filterable placeholder="不指定" style="width: 100%">
            <el-option v-for="u in users" :key="u.id" :label="displayName(u)" :value="u.id" />
          </el-select>
          <div class="muted hint">长期归属人(如员工笔记本)。借还流程不会修改这里。</div>
        </el-form-item>
        <el-form-item v-if="editing" label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="在库" value="in_stock" />
            <el-option label="维修" value="repair" />
            <el-option label="报废" value="retired" />
          </el-select>
          <div class="muted hint">「借出」不是设备状态,由借还记录决定,这里选不到。</div>
        </el-form-item>
        <el-form-item label="采购公司">
          <el-select v-model="form.company_id" clearable filterable placeholder="不指定" style="width: 100%">
            <el-option v-for="c in companies" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="采购日期">
          <el-date-picker v-model="form.purchased_at" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 二维码 -->
    <el-dialog v-model="qrVisible" title="设备二维码" width="360px">
      <div v-if="qrAsset" class="qr">
        <img :src="qrSrc" alt="二维码" class="qr__img" />
        <div class="tag qr__tag">{{ qrAsset.asset_tag }}</div>
        <p class="muted qr__note">
          二维码里只有这串编号,不含链接。用系统外的扫码器扫只会得到一串字符,查不到任何信息。
        </p>
        <el-button @click="downloadQr('png')">下载 PNG</el-button>
        <el-button @click="downloadQr('svg')">下载 SVG</el-button>
      </div>
    </el-dialog>

    <!-- 借出 -->
    <el-dialog v-model="checkoutVisible" title="借出设备" width="420px">
      <el-form v-if="checkoutAsset" label-width="96px">
        <el-form-item label="设备">
          <span class="tag">{{ checkoutAsset.asset_tag }}</span> {{ checkoutAsset.name }}
        </el-form-item>
        <el-form-item label="领用人">
          <el-select v-model="checkoutForm.user_id" filterable style="width: 100%">
            <el-option v-for="u in users" :key="u.id" :label="displayName(u)" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="预计归还">
          <el-date-picker v-model="checkoutForm.due_at" type="datetime" style="width: 100%" placeholder="可留空" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="checkoutVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doCheckout">确认借出</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { api, toast } from '../../api'
import { displayStatus } from '../../format'
import { displayName, isAdmin, session } from '../../store'

const admin = isAdmin()
const route = useRoute()

const rows = ref([])
const categories = ref([])
const users = ref([])
const selection = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const saving = ref(false)

const companies = ref([])
const filters = reactive({ q: '', category_id: null, company_id: null, status: null, checked_out: null })

const emptyForm = () => ({
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
  note: '',
})
const form = reactive(emptyForm())
const formVisible = ref(false)
const editing = ref(false)

const qrVisible = ref(false)
const qrAsset = ref(null)
const qrSrc = computed(() => (qrAsset.value ? api.qrcodeUrl(qrAsset.value.id, 'png', 10) : ''))

const checkoutVisible = ref(false)
const checkoutAsset = ref(null)
const checkoutForm = reactive({ user_id: null, due_at: null })

async function reload(toPage) {
  if (toPage) page.value = toPage
  loading.value = true
  try {
    const data = await api.listAssets({
      q: filters.q,
      category_id: filters.category_id,
      company_id: filters.company_id,
      status: filters.status,
      checked_out: filters.checked_out,
      page: page.value,
      page_size: pageSize.value,
    })
    rows.value = data.items
    total.value = data.total
  } catch (err) {
    toast(err)
  } finally {
    loading.value = false
  }
}

function openForm(row) {
  Object.assign(form, emptyForm())
  editing.value = !!row
  if (row) {
    Object.assign(form, {
      id: row.id,
      asset_tag: row.asset_tag,
      name: row.name,
      category_id: row.category_id,
      brand: row.brand,
      model: row.model,
      serial_no: row.serial_no,
      location: row.location,
      owner_user_id: row.owner ? row.owner.id : null,
      company_id: row.company ? row.company.id : null,
      status: row.status,
      purchased_at: row.purchased_at,
      note: row.note,
    })
  }
  formVisible.value = true
}

async function save() {
  if (!form.name || !form.category_id) {
    ElMessage.warning('请填写设备名称并选择分类')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      // asset_tag 不在提交字段里 —— 编号一经生成永不变更(PRD 3.2)
      const { id, asset_tag, ...body } = form
      await api.updateAsset(id, body)
      ElMessage.success('已保存')
    } else {
      const { id, status, ...body } = form
      if (!body.asset_tag) delete body.asset_tag
      const created = await api.createAsset(body)
      ElMessage.success(`已创建,资产编号 ${created.asset_tag}`)
    }
    formVisible.value = false
    await reload()
  } catch (err) {
    toast(err)
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除「${row.asset_tag} ${row.name}」?删除后不再出现在台账中,借还历史仍保留。`,
      '删除设备',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await api.deleteAsset(row.id)
    ElMessage.success('已删除')
    await reload()
  } catch (err) {
    toast(err)
  }
}

function showQr(row) {
  qrAsset.value = row
  qrVisible.value = true
}

function downloadQr(format) {
  // 走同域链接直接下载,Cookie 会自动带上
  const link = document.createElement('a')
  link.href = api.qrcodeUrl(qrAsset.value.id, format, format === 'png' ? 16 : 8)
  link.download = `${qrAsset.value.asset_tag}.${format}`
  link.click()
}

function openCheckout(row) {
  checkoutAsset.value = row
  checkoutForm.user_id = session.user ? session.user.id : null
  checkoutForm.due_at = null
  checkoutVisible.value = true
}

async function doCheckout() {
  saving.value = true
  try {
    await api.checkout(checkoutAsset.value.id, {
      user_id: checkoutForm.user_id,
      due_at: checkoutForm.due_at ? new Date(checkoutForm.due_at).toISOString() : null,
    })
    ElMessage.success('已借出')
    checkoutVisible.value = false
    await reload()
  } catch (err) {
    toast(err)
    if (err.status === 409) await reload()
  } finally {
    saving.value = false
  }
}

async function doCheckin(row) {
  try {
    await api.checkin(row.id, {})
    ElMessage.success('已归还')
    await reload()
  } catch (err) {
    toast(err)
    if (err.status === 409) await reload()
  }
}

async function exportSelected(fmt) {
  try {
    const res = await api.exportQrcodes(selection.value.map((r) => r.id), fmt)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fmt === 'csv' ? 'asset_tags.csv' : 'qrcodes.zip'
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    toast(err)
  }
}

onMounted(async () => {
  try {
    ;[categories.value, users.value, companies.value] = await Promise.all([
      api.listCategories(),
      api.listUsers(''),
      api.listCompanies(),
    ])
  } catch (err) {
    toast(err)
  }
  // 从采购公司页点「N 台」跳过来时带着 company_id,直接按该公司筛选
  const fromQuery = Number(route.query.company_id)
  if (fromQuery) filters.company_id = fromQuery
  await reload(1)
})
</script>

<style scoped>
.filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filters__spacer { flex: 1; }
.tag { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.hint { font-size: 12px; line-height: 1.5; }
.qr { text-align: center; }
.qr__img { width: 200px; height: 200px; image-rendering: pixelated; }
.qr__tag { font-size: 18px; font-weight: 600; margin: 8px 0; }
.qr__note { font-size: 12px; text-align: left; line-height: 1.6; }
</style>

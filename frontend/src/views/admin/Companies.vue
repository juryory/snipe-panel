<template>
  <el-card shadow="never">
    <div class="row-between" style="margin-bottom: 12px">
      <strong>采购公司</strong>
      <el-button v-if="admin" type="primary" @click="openForm()">新增公司</el-button>
    </div>

    <!-- 展开行按需拉取该公司名下的设备,不在列表接口里塞一堆嵌套数据 -->
    <el-table v-loading="loading" :data="rows" row-key="id" @expand-change="onExpand">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="sub">
            <el-skeleton v-if="assetsOf[row.id] === undefined" :rows="2" animated />
            <el-empty v-else-if="!assetsOf[row.id].length" description="该公司名下暂无设备" :image-size="60" />
            <el-table v-else :data="assetsOf[row.id]" size="small">
              <el-table-column label="资产编号" width="120">
                <template #default="{ row: a }"><span class="tag">{{ a.asset_tag }}</span></template>
              </el-table-column>
              <el-table-column prop="name" label="设备名称" min-width="160" />
              <el-table-column prop="category_name" label="分类" width="100" />
              <el-table-column label="品牌型号" min-width="140">
                <template #default="{ row: a }">
                  {{ [a.brand, a.model].filter(Boolean).join(' ') || '—' }}
                </template>
              </el-table-column>
              <el-table-column label="采购日期" width="120">
                <template #default="{ row: a }">{{ fmtDate(a.purchased_at) }}</template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row: a }">
                  <el-tag :type="displayStatus(a).type" size="small">{{ displayStatus(a).label }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="assetsOf[row.id] && assetsOf[row.id].length" class="sub__more">
              <el-button link type="primary" @click="gotoAssets(row)">在台账中查看全部</el-button>
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="name" label="公司名称" min-width="200" />
      <el-table-column prop="contact" label="联系人" width="120">
        <template #default="{ row }">{{ row.contact || '—' }}</template>
      </el-table-column>
      <el-table-column prop="phone" label="联系电话" width="150">
        <template #default="{ row }">{{ row.phone || '—' }}</template>
      </el-table-column>
      <el-table-column label="在册设备" width="110">
        <template #default="{ row }">
          <el-button v-if="row.asset_count" link type="primary" @click="gotoAssets(row)">
            {{ row.asset_count }} 台
          </el-button>
          <span v-else class="muted">0 台</span>
        </template>
      </el-table-column>
      <el-table-column prop="note" label="备注" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ row.note || '—' }}</template>
      </el-table-column>
      <el-table-column v-if="admin" label="操作" width="130" :fixed="narrow ? false : 'right'">
        <template #default="{ row }">
          <el-button link type="primary" @click="openForm(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" :title="editing ? '编辑公司' : '新增公司'" width="460px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="公司名称" required>
          <el-input v-model="form.name" placeholder="如 星光影视器材有限公司" />
        </el-form-item>
        <el-form-item label="联系人">
          <el-input v-model="form.contact" />
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input v-model="form.phone" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" placeholder="开票信息、售后政策等" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { api, toast } from '../../api'
import { useNarrow } from '../../useNarrow'
import { displayStatus, fmtDate } from '../../format'
import { isAdmin } from '../../store'

const router = useRouter()
const admin = isAdmin()

const narrow = useNarrow()
const rows = ref([])
const assetsOf = reactive({})
const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const editing = ref(false)
const form = reactive({ id: null, name: '', contact: '', phone: '', note: '' })

async function load() {
  loading.value = true
  try {
    rows.value = await api.listCompanies()
  } catch (err) {
    toast(err)
  } finally {
    loading.value = false
  }
}

async function onExpand(row, expanded) {
  const isOpen = Array.isArray(expanded) ? expanded.includes(row) : expanded
  if (!isOpen || assetsOf[row.id] !== undefined) return
  try {
    const data = await api.listAssets({ company_id: row.id, page_size: 20 })
    assetsOf[row.id] = data.items
  } catch (err) {
    assetsOf[row.id] = []
    toast(err)
  }
}

function gotoAssets(row) {
  router.push({ name: 'admin-assets', query: { company_id: row.id } })
}

function openForm(row) {
  editing.value = !!row
  Object.assign(form, {
    id: row ? row.id : null,
    name: row ? row.name : '',
    contact: row ? row.contact : '',
    phone: row ? row.phone : '',
    note: row ? row.note : '',
  })
  visible.value = true
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写公司名称')
    return
  }
  saving.value = true
  const body = { name: form.name, contact: form.contact, phone: form.phone, note: form.note }
  try {
    if (editing.value) {
      await api.updateCompany(form.id, body)
    } else {
      await api.createCompany(body)
    }
    ElMessage.success('已保存')
    visible.value = false
    await load()
  } catch (err) {
    toast(err)
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除采购公司「${row.name}」?`, '删除公司', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await api.deleteCompany(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (err) {
    toast(err)
  }
}

onMounted(load)
</script>

<style scoped>
.tag { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.sub { padding: 8px 16px 12px 48px; }
.sub__more { margin-top: 8px; text-align: right; }
</style>

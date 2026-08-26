<template>
  <el-card shadow="never">
    <div class="row-between" style="margin-bottom: 12px">
      <strong>设备分类</strong>
      <el-button type="primary" @click="openForm()">新增分类</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="编号前缀决定该分类下新设备的资产编号(如 PC → PC-0001)。前缀创建后不可修改 —— 已生成的编号永不变更,改前缀会让新旧设备编号规则不一致。"
      style="margin-bottom: 12px"
    />

    <el-table v-loading="loading" :data="rows">
      <el-table-column prop="name" label="分类名称" min-width="160" />
      <el-table-column label="编号前缀" width="120">
        <template #default="{ row }"><span class="tag">{{ row.tag_prefix }}</span></template>
      </el-table-column>
      <el-table-column label="当前流水号" width="120">
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>
      <el-table-column label="下一个编号" width="140">
        <template #default="{ row }">
          <span class="tag muted">{{ nextTag(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button link type="primary" @click="openForm(row)">重命名</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" :title="editing ? '重命名分类' : '新增分类'" width="420px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="分类名称" required>
          <el-input v-model="form.name" placeholder="如 相机" />
        </el-form-item>
        <el-form-item v-if="!editing" label="编号前缀" required>
          <el-input v-model="form.tag_prefix" placeholder="如 CAM" @input="form.tag_prefix = form.tag_prefix.toUpperCase()" />
          <div class="muted hint">只能是字母和数字。越短,二维码越稀疏,12mm 标签越好扫。</div>
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
import { ElMessage, ElMessageBox } from 'element-plus'

import { api, toast } from '../../api'

const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const editing = ref(false)
const form = reactive({ id: null, name: '', tag_prefix: '' })

function nextTag(row) {
  return `${row.tag_prefix}-${String(row.seq + 1).padStart(4, '0')}`
}

async function load() {
  loading.value = true
  try {
    rows.value = await api.listCategories()
  } catch (err) {
    toast(err)
  } finally {
    loading.value = false
  }
}

function openForm(row) {
  editing.value = !!row
  Object.assign(form, { id: row ? row.id : null, name: row ? row.name : '', tag_prefix: row ? row.tag_prefix : '' })
  visible.value = true
}

async function save() {
  if (!form.name || (!editing.value && !form.tag_prefix)) {
    ElMessage.warning('请填写完整')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await api.updateCategory(form.id, { name: form.name })
    } else {
      await api.createCategory({ name: form.name, tag_prefix: form.tag_prefix })
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
    await ElMessageBox.confirm(`确认删除分类「${row.name}」?`, '删除分类', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await api.deleteCategory(row.id)
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
.hint { font-size: 12px; }
</style>

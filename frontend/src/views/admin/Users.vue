<template>
  <el-card shadow="never">
    <div class="row-between" style="margin-bottom: 12px">
      <strong>用户管理</strong>
      <el-button type="primary" @click="openForm()">新增用户</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="系统不开放自助注册。管理员创建账号并把初始密码告知本人,对方首次登录必须修改密码。忘记密码请在这里重置。"
      style="margin-bottom: 12px"
    />

    <el-table v-loading="loading" :data="rows">
      <el-table-column prop="username" label="用户名" width="140" />
      <el-table-column prop="real_name" label="姓名" width="140" />
      <el-table-column prop="department" label="部门" min-width="140" />
      <el-table-column label="角色" width="110">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'warning' : 'info'" size="small">
            {{ row.role === 'admin' ? '管理员' : '普通用户' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="150">
        <template #default="{ row }">
          <el-tag v-if="!row.is_active" type="danger" size="small">已停用</el-tag>
          <el-tag v-else-if="row.must_change_password" type="warning" size="small">待首次改密</el-tag>
          <el-tag v-else type="success" size="small">正常</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240">
        <template #default="{ row }">
          <el-button link type="primary" @click="openForm(row)">编辑</el-button>
          <el-button link type="primary" @click="openReset(row)">重置密码</el-button>
          <el-button
            v-if="row.id !== me"
            link
            :type="row.is_active ? 'danger' : 'success'"
            @click="toggleActive(row)"
          >
            {{ row.is_active ? '停用' : '启用' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" :title="editing ? '编辑用户' : '新增用户'" width="440px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" :disabled="editing" />
        </el-form-item>
        <el-form-item v-if="!editing" label="初始密码" required>
          <el-input v-model="form.password" show-password />
          <div class="muted hint">至少 8 位。对方首次登录后会被要求修改。</div>
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.real_name" />
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="form.department" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="普通用户" value="user" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetVisible" title="重置密码" width="400px">
      <el-form label-width="90px">
        <el-form-item label="用户">
          {{ resetTarget ? (resetTarget.real_name || resetTarget.username) : '' }}
        </el-form-item>
        <el-form-item label="新密码" required>
          <el-input v-model="newPassword" show-password />
          <div class="muted hint">至少 8 位。重置后该用户下次登录须再次修改,账号锁定也会一并解除。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doReset">确认重置</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { api, toast } from '../../api'
import { session } from '../../store'

const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const editing = ref(false)
const resetVisible = ref(false)
const resetTarget = ref(null)
const newPassword = ref('')

const me = computed(() => (session.user ? session.user.id : null))
const form = reactive({ id: null, username: '', password: '', real_name: '', department: '', role: 'user' })

async function load() {
  loading.value = true
  try {
    rows.value = await api.listUsersDetail()
  } catch (err) {
    toast(err)
  } finally {
    loading.value = false
  }
}

function openForm(row) {
  editing.value = !!row
  Object.assign(form, {
    id: row ? row.id : null,
    username: row ? row.username : '',
    password: '',
    real_name: row ? row.real_name : '',
    department: row ? row.department : '',
    role: row ? row.role : 'user',
  })
  visible.value = true
}

async function save() {
  if (!form.username) {
    ElMessage.warning('请填写用户名')
    return
  }
  if (!editing.value && form.password.length < 8) {
    ElMessage.warning('初始密码至少 8 位')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await api.updateUser(form.id, {
        real_name: form.real_name,
        department: form.department,
        role: form.role,
      })
    } else {
      await api.createUser({
        username: form.username,
        password: form.password,
        real_name: form.real_name,
        department: form.department,
        role: form.role,
      })
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

function openReset(row) {
  resetTarget.value = row
  newPassword.value = ''
  resetVisible.value = true
}

async function doReset() {
  if (newPassword.value.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  saving.value = true
  try {
    await api.resetPassword(resetTarget.value.id, newPassword.value)
    ElMessage.success('已重置,请把新密码告知本人')
    resetVisible.value = false
    await load()
  } catch (err) {
    toast(err)
  } finally {
    saving.value = false
  }
}

async function toggleActive(row) {
  try {
    await api.updateUser(row.id, { is_active: !row.is_active })
    await load()
  } catch (err) {
    toast(err)
  }
}

onMounted(load)
</script>

<style scoped>
.hint { font-size: 12px; line-height: 1.5; }
</style>

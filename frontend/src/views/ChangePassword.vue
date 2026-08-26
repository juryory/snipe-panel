<template>
  <div class="pw">
    <el-card class="pw__card">
      <h2 class="pw__title">{{ forced ? '首次登录,请先修改密码' : '修改密码' }}</h2>
      <el-alert
        v-if="forced"
        type="warning"
        :closable="false"
        show-icon
        title="初始密码由管理员下发,修改后才能使用系统。"
        style="margin-bottom: 16px"
      />
      <el-form :model="form" label-position="top" @submit.prevent="submit">
        <el-form-item label="原密码">
          <el-input v-model="form.oldPassword" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="form.newPassword" type="password" show-password autocomplete="new-password" />
          <div class="muted pw__hint">至少 8 位</div>
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input
            v-model="form.confirm"
            type="password"
            show-password
            autocomplete="new-password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" style="width: 100%" :loading="loading" @click="submit">提交</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { api, toast } from '../api'
import { session } from '../store'

const router = useRouter()
const form = reactive({ oldPassword: '', newPassword: '', confirm: '' })
const loading = ref(false)
const forced = computed(() => !!(session.user && session.user.must_change_password))

async function submit() {
  if (form.newPassword.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  if (form.newPassword !== form.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  loading.value = true
  try {
    session.user = await api.changePassword(form.oldPassword, form.newPassword)
    ElMessage.success('密码已修改')
    router.replace('/admin/assets')
  } catch (err) {
    toast(err)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.pw {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.pw__card { width: 100%; max-width: 420px; }
.pw__title { margin: 0 0 16px; font-size: 18px; }
.pw__hint { font-size: 12px; }
</style>

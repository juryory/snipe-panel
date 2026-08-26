<template>
  <div class="login">
    <el-card class="login__card">
      <h2 class="login__title">设备资产管理系统</h2>
      <el-form :model="form" label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="username" size="large" clearable />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            autocomplete="current-password"
            size="large"
            show-password
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="submit">
          登录
        </el-button>
      </el-form>
      <p class="login__tip muted">忘记密码请联系管理员重置。</p>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { api, toast } from '../api'
import { session } from '../store'

const route = useRoute()
const router = useRouter()

const form = reactive({ username: '', password: '' })
const loading = ref(false)

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const user = await api.login(form.username.trim(), form.password)
    session.user = user
    session.loaded = true
    if (user.must_change_password) {
      router.replace({ name: 'change-password' })
      return
    }
    // 后台入口的登录页:手机上登进来就送去手机端
    if (window.matchMedia('(max-width: 768px)').matches && !route.query.redirect) {
      window.location.replace('/m/')
      return
    }
    router.replace(route.query.redirect || '/admin/assets')
  } catch (err) {
    toast(err)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.login__card { width: 100%; max-width: 380px; }
.login__title { margin: 0 0 20px; font-size: 20px; text-align: center; }
.login__tip { margin: 16px 0 0; font-size: 13px; text-align: center; }
</style>

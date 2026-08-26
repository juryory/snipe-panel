<template>
  <div class="login">
    <div class="login__head">
      <div class="login__logo">
        <van-icon name="scan" size="40" color="#fff" />
      </div>
      <h1 class="login__title">设备台账</h1>
      <p class="login__sub muted">扫码查看设备 · 办理借用与归还</p>
    </div>

    <van-form @submit="submit">
      <van-cell-group inset>
        <van-field
          v-model="form.username"
          name="username"
          label="用户名"
          placeholder="请输入用户名"
          autocomplete="username"
          :rules="[{ required: true, message: '请输入用户名' }]"
        />
        <van-field
          v-model="form.password"
          type="password"
          name="password"
          label="密码"
          placeholder="请输入密码"
          autocomplete="current-password"
          :rules="[{ required: true, message: '请输入密码' }]"
        />
      </van-cell-group>

      <div class="login__actions">
        <van-button round block type="primary" native-type="submit" :loading="loading">
          登录
        </van-button>
        <p class="login__tip muted">忘记密码请联系管理员重置</p>
      </div>
    </van-form>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Button as VanButton,
  CellGroup as VanCellGroup,
  Field as VanField,
  Form as VanForm,
  Icon as VanIcon,
  showFailToast,
} from 'vant'

import { api, ApiError } from '../../api'
import { session } from '../../store'

const route = useRoute()
const router = useRouter()

const form = reactive({ username: '', password: '' })
const loading = ref(false)

async function submit() {
  loading.value = true
  try {
    const user = await api.login(form.username.trim(), form.password)
    session.user = user
    session.loaded = true
    if (user.must_change_password) {
      router.replace({ name: 'change-password' })
      return
    }
    router.replace(route.query.redirect || '/scan')
  } catch (err) {
    showFailToast(err instanceof ApiError ? err.detail : String(err))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login { min-height: 100vh; padding-top: 12vh; }
.login__head { text-align: center; margin-bottom: 24px; }
.login__logo {
  width: 72px;
  height: 72px;
  margin: 0 auto 16px;
  border-radius: 18px;
  background: #1f2937;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login__title { margin: 0; font-size: 22px; }
.login__sub { margin: 6px 0 0; font-size: 13px; }
.login__actions { padding: 24px 16px 0; }
.login__tip { text-align: center; font-size: 12px; margin: 16px 0 0; }
</style>

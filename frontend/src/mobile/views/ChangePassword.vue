<template>
  <div>
    <van-nav-bar
      :title="forced ? '首次登录请改密' : '修改密码'"
      :left-arrow="!forced"
      @click-left="$router.back()"
    />

    <van-notice-bar
      v-if="forced"
      wrapable
      :scrollable="false"
      text="初始密码由管理员下发,修改后才能使用系统。"
    />

    <van-form @submit="submit">
      <van-cell-group inset style="margin-top: 12px">
        <van-field
          v-model="form.oldPassword"
          type="password"
          label="原密码"
          placeholder="请输入原密码"
          autocomplete="current-password"
          :rules="[{ required: true, message: '请输入原密码' }]"
        />
        <van-field
          v-model="form.newPassword"
          type="password"
          label="新密码"
          placeholder="至少 8 位"
          autocomplete="new-password"
          :rules="[{ validator: atLeast8, message: '新密码至少 8 位' }]"
        />
        <van-field
          v-model="form.confirm"
          type="password"
          label="确认密码"
          placeholder="再输入一次新密码"
          autocomplete="new-password"
          :rules="[{ validator: matches, message: '两次输入的新密码不一致' }]"
        />
      </van-cell-group>

      <div style="padding: 24px 16px 0">
        <van-button round block type="primary" native-type="submit" :loading="loading">
          提交
        </van-button>
      </div>
    </van-form>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Button as VanButton,
  CellGroup as VanCellGroup,
  Field as VanField,
  Form as VanForm,
  NavBar as VanNavBar,
  NoticeBar as VanNoticeBar,
  showFailToast,
  showSuccessToast,
} from 'vant'

import { api, ApiError } from '../../api'
import { session } from '../../store'

const router = useRouter()
const form = reactive({ oldPassword: '', newPassword: '', confirm: '' })
const loading = ref(false)
const forced = computed(() => !!(session.user && session.user.must_change_password))

const atLeast8 = (v) => (v || '').length >= 8
const matches = (v) => v === form.newPassword

async function submit() {
  loading.value = true
  try {
    session.user = await api.changePassword(form.oldPassword, form.newPassword)
    showSuccessToast('密码已修改')
    router.replace('/scan')
  } catch (err) {
    showFailToast(err instanceof ApiError ? err.detail : String(err))
  } finally {
    loading.value = false
  }
}
</script>

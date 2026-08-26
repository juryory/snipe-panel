<template>
  <!--
    移动端与桌面后台共用一套登录(PRD 3.7),但布局分开:
    /m/* 走无边框的移动布局,/admin/* 走带侧边导航的后台布局。
  -->
  <el-container v-if="isAdminLayout" class="shell">
    <el-header class="shell__header">
      <div class="shell__brand">设备资产管理系统</div>
      <el-menu mode="horizontal" :router="true" :default-active="$route.path" class="shell__menu">
        <el-menu-item index="/admin/assets">设备台账</el-menu-item>
        <el-menu-item index="/admin/checkouts">借还记录</el-menu-item>
        <el-menu-item v-if="admin" index="/admin/categories">分类</el-menu-item>
        <el-menu-item v-if="admin" index="/admin/users">用户</el-menu-item>
        <el-menu-item index="/m">扫码</el-menu-item>
      </el-menu>
      <el-dropdown @command="onCommand">
        <span class="shell__user">
          {{ name }}<el-tag v-if="admin" size="small" type="warning" style="margin-left: 6px">管理员</el-tag>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="password">修改密码</el-dropdown-item>
            <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>

  <router-view v-else />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, toast } from './api'
import { displayName, isAdmin, session } from './store'

const route = useRoute()
const router = useRouter()

const isAdminLayout = computed(() => route.path.startsWith('/admin') && !!session.user)
const admin = computed(() => isAdmin())
const name = computed(() => displayName(session.user))

async function onCommand(command) {
  if (command === 'password') {
    router.push({ name: 'change-password' })
    return
  }
  try {
    await api.logout()
  } catch (err) {
    toast(err)
  }
  session.user = null
  router.replace({ name: 'login' })
}
</script>

<style scoped>
.shell { min-height: 100vh; }
.shell__header {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.shell__brand { font-weight: 600; white-space: nowrap; }
.shell__menu { flex: 1; border-bottom: none; }
.shell__user { cursor: pointer; white-space: nowrap; }
</style>

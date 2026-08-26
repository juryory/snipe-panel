<template>
  <!--
    手机端外壳。底部标签栏是移动应用的标准导航,登录页和详情页这类
    「一次性」页面不显示(meta.plain)。
  -->
  <div :class="showTabs ? 'page' : 'page page--plain'">
    <router-view v-slot="{ Component }">
      <keep-alive :include="['MobileScan', 'MobileAssets']">
        <component :is="Component" />
      </keep-alive>
    </router-view>
  </div>

  <van-tabbar v-if="showTabs" route safe-area-inset-bottom>
    <van-tabbar-item to="/scan" icon="scan">扫码</van-tabbar-item>
    <van-tabbar-item to="/assets" icon="apps-o">台账</van-tabbar-item>
    <van-tabbar-item to="/mine" icon="user-o">我的</van-tabbar-item>
  </van-tabbar>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Tabbar as VanTabbar, TabbarItem as VanTabbarItem } from 'vant'

const route = useRoute()

const showTabs = computed(() => !route.meta.plain && route.name !== undefined)
</script>

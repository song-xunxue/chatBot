<script setup lang="ts">
/**
 * 移动端顶层布局(手机端管理面板):简易顶栏(标题)+ 内容区,无侧栏/oid 输入/登出。
 * 与 PC 端 MainLayout 对称但极简,为 /m/* 路由(代人代答等)提供共性外壳,便于将来扩展。
 * 鉴权由 router 守卫处理(query token 免登录);oid 由各页 useObject.ensureOid 自动取。
 * 作者: 李文煜
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { NLayout, NLayoutHeader, NLayoutContent } from 'naive-ui'

const route = useRoute()
// 顶栏标题取路由 meta.title(与 PC MainLayout 一致),默认回退
const title = computed(() => (route.meta.title as string) || 'MyChat 管理面板')
</script>

<template>
  <n-layout style="height: 100vh">
    <n-layout-header bordered style="height:48px;padding:0 12px;display:flex;align-items:center">
      <span style="font-weight:600;font-size:16px">{{ title }}</span>
    </n-layout-header>
    <n-layout-content content-style="padding:12px" :native-scrollbar="false">
      <router-view />
    </n-layout-content>
  </n-layout>
</template>

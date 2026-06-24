<script setup lang="ts">
/**
 * 主布局：左侧栏导航 + 顶栏（标题/登出）+ 内容区
 * 作者: 李文煜
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutHeader, NLayoutSider, NLayoutContent, NMenu, NButton, NSpace } from 'naive-ui'
import type { MenuOption } from 'naive-ui'

const route = useRoute()
const router = useRouter()

const menuOptions: MenuOption[] = [
  { label: '人设管理', key: 'persona' },
  { label: '插件管理', key: 'plugin' },
  { label: '记忆查看', key: 'memory' },
  { label: '模型配置', key: 'model' },
  { label: '对话历史', key: 'history' },
  { label: '代人聊天', key: 'roleplay' },
]

const activeKey = computed(() => (route.name as string) || 'persona')
const title = computed(() => (route.meta.title as string) || 'MyChat 管理面板')

function onSelect(key: string) {
  router.push({ name: key })
}
function logout() {
  localStorage.removeItem('access_token')
  router.push({ name: 'login' })
}
</script>

<template>
  <n-layout has-sider style="height: 100vh">
    <n-layout-sider bordered :width="200" content-style="padding:8px">
      <div style="padding:12px;font-weight:700;font-size:16px">🐱 MyChat</div>
      <n-menu :value="activeKey" :options="menuOptions" @update:value="onSelect" />
    </n-layout-sider>
    <n-layout>
      <n-layout-header bordered style="height:52px;padding:0 20px;display:flex;align-items:center;justify-content:space-between">
        <span style="font-weight:600">{{ title }}</span>
        <n-button size="small" quaternary @click="logout">登出</n-button>
      </n-layout-header>
      <n-layout-content content-style="padding:20px" :native-scrollbar="false">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

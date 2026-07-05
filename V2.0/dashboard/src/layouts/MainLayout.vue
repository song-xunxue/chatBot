<script setup lang="ts">
/**
 * 主布局(V2.0 M7):左侧栏导航 + 顶栏(标题/全局 oid/登出)+ 内容区。
 * 菜单:人设/历史/记忆/心情/插件/系统/代人代答/训练样本(评分已并入对话历史,2026-07-03)。
 * 作者: 李文煜
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutHeader, NLayoutSider, NLayoutContent, NMenu, NButton, NInput } from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import { useObject } from '@/composables/useObject'

const route = useRoute()
const router = useRouter()
const { oid, triggerReload } = useObject()   // 全局共享 object_id + 回车触发当前页刷新

const menuOptions: MenuOption[] = [
  { label: '人设管理', key: 'persona' },
  { label: '对话历史', key: 'history' },
  { label: '记忆查看', key: 'memory' },
  { label: '心情系统', key: 'mood' },
  { label: '插件管理', key: 'plugin' },
  { label: '系统配置', key: 'system' },
  { label: '代人代答', key: 'takeover' },
  { label: '训练样本', key: 'roleplay' },
]

const activeKey = computed(() => (route.name as string) || 'history')
const title = computed(() => (route.meta.title as string) || 'MyChat V2.0 管理面板')

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
      <div style="padding:12px;font-weight:700;font-size:16px">🐱 MyChat V2.0</div>
      <n-menu :value="activeKey" :options="menuOptions" @update:value="onSelect" />
    </n-layout-sider>
    <n-layout>
      <n-layout-header bordered style="height:52px;padding:0 20px;display:flex;align-items:center;justify-content:space-between">
        <span style="font-weight:600">{{ title }}</span>
        <div style="display:flex;align-items:center;gap:12px">
          <n-input v-model:value="oid" placeholder="object_id(共享,回车刷新)" size="small" style="width:240px" @keyup.enter="triggerReload" />
          <n-button size="small" quaternary @click="logout">登出</n-button>
        </div>
      </n-layout-header>
      <n-layout-content content-style="padding:20px" :native-scrollbar="false">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

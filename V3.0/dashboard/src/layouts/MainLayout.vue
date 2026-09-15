<script setup lang="ts">
/**
 * 主布局(V2.0 M7):左侧栏导航 + 顶栏(标题/全局 oid/登出)+ 内容区。
 * 菜单:人设/历史/记忆/心情/插件/系统/代人代答/训练样本(评分已并入对话历史,2026-07-03)。
 * 2026-09-15:NapCat 掉线红色横幅(60s 轮询;QQ 掉线期间消息静默丢失的教训)。
 * 作者: 李文煜
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutHeader, NLayoutSider, NLayoutContent, NMenu, NButton, NInput, NAlert } from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import { useObject } from '@/composables/useObject'
import { useNapcatWatch } from '@/composables/useNapcatWatch'

const route = useRoute()
const router = useRouter()
const { oid, triggerReload } = useObject()   // 全局共享 object_id + 回车触发当前页刷新
const { offline, detail } = useNapcatWatch() // NapCat 掉线横幅(60s 轮询,offline 常驻红条)

const menuOptions: MenuOption[] = [
  { label: '人设管理', key: 'persona' },
  { label: '对话历史', key: 'history' },
  { label: '记忆查看', key: 'memory' },
  { label: '心情系统', key: 'mood' },
  { label: '插件管理', key: 'plugin' },
  { label: '系统配置', key: 'system' },
  { label: '对话控制', key: 'takeover' },
]

const activeKey = computed(() => (route.name as string) || 'history')
const title = computed(() => (route.meta.title as string) || '清浔 3.0 管理面板')

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
      <div style="padding:12px;font-weight:700;font-size:16px">清浔 3.0</div>
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
      <n-alert v-if="offline" type="error" :show-icon="true" style="border-radius:0"
               title="清浔 QQ 已掉线,消息正在丢失!">
        {{ detail }} —— 请尽快打开 NapCat WebUI(http://43.140.219.99:6080/webui)扫码重登,
        并参考 Wiki:二维码刷新失败时重启 napcat-v4 容器再扫。
      </n-alert>
      <n-layout-content content-style="padding:20px" :native-scrollbar="false">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

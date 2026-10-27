<script setup lang="ts">
/**
 * 主布局(2026-09-16 暗色重设计,仿 NapCat WebUI):
 * 左侧栏(logo + 在线状态点 + 菜单胶囊高亮 + 底部版本/时钟)+ 顶栏(标题/全局 oid/登出)
 * + 掉线浮动胶囊(drop-in)+ 内容区路由过渡(page-fade)。
 * 菜单:人设/历史/记忆/心情/插件/系统/对话控制(评分已并入对话历史)。
 */
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutHeader, NLayoutSider, NLayoutContent, NMenu, NButton, NInput } from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import { useObject } from '@/composables/useObject'
import { useNapcatWatch } from '@/composables/useNapcatWatch'

const route = useRoute()
const router = useRouter()
const { oid, triggerReload } = useObject()   // 全局共享 object_id + 回车触发当前页刷新
const { offline, detail } = useNapcatWatch() // NapCat 掉线监控(60s 轮询;offline 顶栏下浮动胶囊)

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
const title = computed(() => (route.meta.title as string) || 'chatbotV3.0 管理面板')

// 底部小时钟(NapCat 风格侧栏脚注)
const clock = ref('')
let clockTimer: number | undefined
function tick() {
  clock.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
}
onMounted(() => {
  tick()
  clockTimer = window.setInterval(tick, 1000)
})
onUnmounted(() => {
  if (clockTimer) window.clearInterval(clockTimer)
})

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
    <n-layout-sider :width="216" content-style="display:flex;flex-direction:column;height:100%" class="side">
      <!-- logo 区:呼吸状态点(在线绿/掉线红)+ 标题 -->
      <div class="logo card-hover">
        <span class="dot" :class="{ 'dot-off': offline, 'pulse-dot': !offline }"></span>
        <span class="logo-text">chatbot <span class="logo-ver">3.0</span></span>
      </div>
      <n-menu :value="activeKey" :options="menuOptions" :indent="18" class="menu" @update:value="onSelect" />
      <!-- 脚注:版本 + 实时时钟 -->
      <div class="side-foot">
        <span>mychat-v3</span>
        <span class="clock">{{ clock }}</span>
      </div>
    </n-layout-sider>
    <n-layout>
      <n-layout-header bordered class="topbar">
        <span class="title">{{ title }}</span>
        <div style="display:flex;align-items:center;gap:12px">
          <n-input v-model:value="oid" placeholder="object_id(共享,回车刷新)" size="small" style="width:240px" @keyup.enter="triggerReload" />
          <n-button size="small" quaternary @click="logout">登出</n-button>
        </div>
      </n-layout-header>
      <!-- 掉线浮动胶囊(drop-in 动画;消息正在丢失的强提示) -->
      <div v-if="offline" class="offline-capsule drop-in">
        <span class="dot dot-off pulse-dot" style="width:8px;height:8px"></span>
        <b>QQ 已掉线,消息正在丢失!</b>
        <span class="offline-detail">{{ detail }} —— 打开 NapCat WebUI(6080)扫码重登;二维码刷新失败时重启 napcat-v4 容器</span>
      </div>
      <n-layout-content content-style="padding:20px" :native-scrollbar="false">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" :key="route.path" />
          </transition>
        </router-view>
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<style scoped>
.side {
  background: var(--card);
  border-right: 1px solid var(--border);
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 18px 12px;
  font-weight: 700;
  font-size: 17px;
  color: var(--text);
}
.logo-ver {
  font-size: 12px;
  font-weight: 500;
  color: var(--accent);
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 8px rgba(63, 198, 138, 0.8);
  flex-shrink: 0;
}
.dot-off {
  background: var(--danger);
  box-shadow: 0 0 8px rgba(229, 72, 77, 0.8);
}
.menu {
  flex: 1;
  padding: 4px 10px;
  background: transparent;
}
.side-foot {
  display: flex;
  justify-content: space-between;
  padding: 12px 18px;
  font-size: 11px;
  color: var(--text-faint);
  border-top: 1px solid var(--border);
}
.clock {
  font-variant-numeric: tabular-nums;
}
.topbar {
  height: 52px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--card);
}
.title {
  font-weight: 600;
  color: var(--text);
}
.offline-capsule {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 12px 20px 0;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--danger-dim);
  border: 1px solid rgba(229, 72, 77, 0.35);
  color: var(--text);
  font-size: 13px;
}
.offline-capsule b {
  color: var(--danger);
}
.offline-detail {
  color: var(--text-dim);
  font-size: 12px;
}
</style>

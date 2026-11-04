<script setup lang="ts">
/**
 * 主布局(2026-09-16 暗色重设计,仿 NapCat WebUI;2026-11-03 对齐 NextNapCatWebUI 交互):
 * 左侧栏(logo + 在线状态点 + 菜单 + 底部主题切换/登出)——**可折叠**(汉堡按钮,localStorage 记忆,
 * 折叠后仅图标) + **悬浮胶囊顶栏**(毛玻璃圆角条:汉堡/标题/全局 oid/登出,替代传统通栏)。
 * 掉线浮动胶囊 + 内容区路由过渡(page-fade)保留;主题切换经 App.vue provide 的 toggleTheme。
 * 菜单:人设/历史/记忆/心情/日记/世界书/插件/系统/对话控制(评分已并入对话历史)。
 * 日期: 2026-09-16

2026-11-03
变更说明:
  1. 对齐 NextNapCatWebUI:①侧栏可折叠(collapsed=68px 图标模式,localStorage「panel-side」);
     ②顶栏改悬浮胶囊条(sticky+毛玻璃+圆角,左侧汉堡切换侧栏);③侧栏底部加「切换主题」;
     ④侧栏底色走 --side-bg(浅粉/深黑随主题);⑤菜单加 emoji 图标(折叠态可见)
 */
import { computed, h, inject, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutSider, NLayoutContent, NMenu, NButton, NInput, NTooltip } from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import { useObject } from '@/composables/useObject'
import { useNapcatWatch } from '@/composables/useNapcatWatch'

const route = useRoute()
const router = useRouter()
const { oid, triggerReload } = useObject()   // 全局共享 object_id + 回车触发当前页刷新
const { offline, detail } = useNapcatWatch() // NapCat 掉线监控(60s 轮询)
const isDark = inject('isDark', ref(false))            // App.vue provide(双主题)
const toggleTheme = inject<() => void>('toggleTheme', () => {})

// —— 主题(App.vue provide;按钮放侧栏底部,NapCat「切换主题」同位) ——
const themeLabel = computed(() => (isDark.value ? '🌙 深色' : '☀️ 浅色'))

// —— 侧栏折叠(汉堡按钮;localStorage 记忆) ——
const collapsed = ref(localStorage.getItem('panel-side') === '1')
function toggleSide() {
  collapsed.value = !collapsed.value
  localStorage.setItem('panel-side', collapsed.value ? '1' : '0')
}

// 菜单(emoji 图标:折叠 68px 态仍可辨识;零依赖不引图标库)
const ICONS: Record<string, string> = {
  persona: '🎭', history: '💬', memory: '🧠', mood: '💗',
  plugin: '🧩', system: '⚙️', takeover: '🎛️',
}
const menuOptions: MenuOption[] = [
  { label: '人设管理', key: 'persona', icon: () => h('span', { class: 'mi' }, ICONS.persona) },
  { label: '对话历史', key: 'history', icon: () => h('span', { class: 'mi' }, ICONS.history) },
  { label: '记忆查看', key: 'memory', icon: () => h('span', { class: 'mi' }, ICONS.memory) },
  { label: '心情系统', key: 'mood', icon: () => h('span', { class: 'mi' }, ICONS.mood) },
  { label: '插件管理', key: 'plugin', icon: () => h('span', { class: 'mi' }, ICONS.plugin) },
  { label: '系统配置', key: 'system', icon: () => h('span', { class: 'mi' }, ICONS.system) },
  { label: '对话控制', key: 'takeover', icon: () => h('span', { class: 'mi' }, ICONS.takeover) },
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
    <n-layout-sider
      :width="216" :collapsed="collapsed" :collapsed-width="68" collapse-mode="width"
      content-style="display:flex;flex-direction:column;height:100%" class="side"
    >
      <!-- logo 区:呼吸状态点(在线粉/掉线红)+ 标题(折叠态只留点) -->
      <div class="logo">
        <span class="dot" :class="{ 'dot-off': offline, 'pulse-dot': !offline }"></span>
        <span v-if="!collapsed" class="logo-text">chatbot <span class="logo-ver">3.0</span></span>
      </div>
      <n-menu
        :value="activeKey" :options="menuOptions" :indent="18"
        :collapsed="collapsed" :collapsed-width="68" :collapsed-icon-size="20"
        class="menu" @update:value="onSelect"
      />
      <!-- 底部:主题切换(NapCat「切换主题」同位)+ 登出 + 时钟 -->
      <div class="side-foot">
        <n-tooltip v-if="collapsed" placement="right">
          <template #trigger>
            <button class="foot-btn" @click="toggleTheme">{{ isDark ? '🌙' : '☀️' }}</button>
          </template>
          切换主题(当前{{ themeLabel }})
        </n-tooltip>
        <template v-else>
          <button class="foot-btn foot-wide" @click="toggleTheme">{{ themeLabel }} 主题</button>
          <button class="foot-btn foot-wide" @click="logout">退出登录</button>
        </template>
        <span v-if="!collapsed" class="clock">{{ clock }}</span>
      </div>
    </n-layout-sider>
    <n-layout>
      <n-layout-content content-style="padding:16px 20px 20px" :native-scrollbar="false">
        <!-- 悬浮胶囊顶栏(sticky+毛玻璃+圆角,NextNapCatWebUI 同款形态):汉堡+标题+oid+登出 -->
        <div class="floating-bar">
          <button class="burger" :title="collapsed ? '展开侧栏' : '收起侧栏'" @click="toggleSide">
            {{ collapsed ? '☰' : '✕' }}
          </button>
          <span class="title">{{ title }}</span>
          <div class="bar-right">
            <n-input v-model:value="oid" placeholder="object_id(共享,回车刷新)" size="small" style="width:230px" @keyup.enter="triggerReload" />
            <n-button size="small" quaternary @click="logout">登出</n-button>
          </div>
        </div>
        <!-- 掉线浮动胶囊(drop-in 动画;消息正在丢失的强提示) -->
        <div v-if="offline" class="offline-capsule drop-in">
          <span class="dot dot-off pulse-dot" style="width:8px;height:8px"></span>
          <b>QQ 已掉线,消息正在丢失!</b>
          <span class="offline-detail">{{ detail }} —— 打开 NapCat WebUI(6080)扫码重登;二维码刷新失败时重启 napcat-v4 容器</span>
        </div>
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
  background: var(--side-bg);
  border-right: 1px solid var(--border);
  transition: background var(--dur-2, 0.2s) var(--ease, ease);
}
.logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 16px 12px 12px;
  font-weight: 700;
  font-size: 17px;
  color: var(--text);
}
.logo-text {
  white-space: nowrap;
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
  box-shadow: 0 0 8px rgba(236, 72, 153, 0.7);
  flex-shrink: 0;
}
.dot-off {
  background: var(--danger);
  box-shadow: 0 0 8px rgba(225, 29, 72, 0.7);
}
.menu {
  flex: 1;
  padding: 4px 10px;
  background: transparent;
}
/* 菜单 emoji 图标(折叠态可见性) */
.menu :deep(.mi) {
  font-size: 16px;
  line-height: 1;
}
.side-foot {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: stretch;
  padding: 12px 12px;
  font-size: 11px;
  color: var(--text-faint);
  border-top: 1px solid var(--border);
}
.foot-btn {
  border: none;
  background: var(--card);
  color: var(--text-dim);
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--dur-1, 0.12s);
}
.foot-btn:hover {
  background: var(--accent-dim);
  color: var(--accent);
}
.foot-wide {
  text-align: center;
}
.clock {
  text-align: center;
  font-variant-numeric: tabular-nums;
}
/* 悬浮胶囊顶栏(NextNapCatWebUI:圆角+毛玻璃+粉色阴影,sticky 浮于内容上方) */
.floating-bar {
  position: sticky;
  top: 8px;
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 46px;
  padding: 0 10px 0 6px;
  margin-bottom: 14px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--card) 78%, transparent);
  backdrop-filter: blur(10px);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-card);
}
.burger {
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-dim);
  font-size: 15px;
  cursor: pointer;
}
.burger:hover {
  background: var(--accent-dim);
  color: var(--accent);
}
.title {
  font-weight: 600;
  color: var(--text);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.offline-capsule {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 0 0 14px;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--danger-dim);
  border: 1px solid var(--danger);
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

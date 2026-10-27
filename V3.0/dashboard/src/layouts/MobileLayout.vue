<script setup lang="ts">
/**
 * 移动端顶层布局(手机端管理面板,2026-09-16 暗色重设计仿 NapCat):
 * 顶栏(标题)+ 掉线浮动胶囊(drop-in)+ 内容区(路由过渡)+ 底部 tab 毛玻璃导航。
 * 为 /m/* 路由(对话/历史/记忆/人设/心情/插件/系统)提供共性外壳。
 * 鉴权由 router 守卫处理(登录后回跳原页面);oid 由各页 useObject.ensureOid 自动取。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { NLayout, NLayoutHeader, NLayoutContent } from 'naive-ui'
import { useNapcatWatch } from '@/composables/useNapcatWatch'

const route = useRoute()
const { offline, detail } = useNapcatWatch() // NapCat 掉线监控(60s 轮询;offline 浮动胶囊)

// 底部导航七页(2026-09-08 全页适配):代答置首(手机最高频),与 /m/* 路由一一对应
const tabs = [
  { path: '/m/takeover', label: '对话' },
  { path: '/m/history', label: '历史' },
  { path: '/m/memory', label: '记忆' },
  { path: '/m/persona', label: '人设' },
  { path: '/m/mood', label: '心情' },
  { path: '/m/plugin', label: '插件' },
  { path: '/m/system', label: '系统' },
]
const activePath = computed(() => {
  // 按最长前缀匹配高亮(/m/history 命中 history,而非误高亮其它)
  const hit = tabs.filter((t) => route.path.startsWith(t.path))
  return hit.length ? hit[hit.length - 1].path : ''
})
</script>

<template>
  <n-layout style="height: 100vh; display: flex; flex-direction: column; background: var(--bg)">
    <n-layout-header class="m-topbar">
      <span class="m-title">{{ (route.meta.title as string) || 'chatbotV3.0 管理面板' }}</span>
      <span class="dot" :class="offline ? 'dot-off pulse-dot' : 'pulse-dot'"></span>
    </n-layout-header>
    <!-- 掉线浮动胶囊(drop-in 动画) -->
    <div v-if="offline" class="m-offline drop-in">
      <b>QQ 已掉线,消息正在丢失!</b>
      <span class="m-offline-detail">{{ detail }} —— 请在电脑上打开 NapCat WebUI 扫码重登</span>
    </div>
    <n-layout-content content-style="padding:12px;flex:1;min-height:0" :native-scrollbar="false" style="flex:1">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" :key="route.path" />
        </transition>
      </router-view>
    </n-layout-content>
    <!-- 底部 tab 导航:7 页短标签平铺,毛玻璃(backdrop-blur)+ safe-area 适配 iOS 全面屏 -->
    <nav class="m-tabbar">
      <router-link v-for="t in tabs" :key="t.path" :to="t.path"
                   class="m-tab" :class="{ active: activePath === t.path }">
        {{ t.label }}
      </router-link>
    </nav>
  </n-layout>
</template>

<style scoped>
.m-topbar {
  height: 48px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  background: var(--card);
  border-bottom: 1px solid var(--border);
}
.m-title {
  font-weight: 600;
  font-size: 16px;
  color: var(--text);
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 8px rgba(63, 198, 138, 0.8);
}
.dot-off {
  background: var(--danger);
  box-shadow: 0 0 8px rgba(229, 72, 77, 0.8);
}
.m-offline {
  margin: 10px 12px 0;
  padding: 9px 12px;
  border-radius: 10px;
  background: var(--danger-dim);
  border: 1px solid rgba(229, 72, 77, 0.35);
  font-size: 13px;
  color: var(--text);
  flex-shrink: 0;
}
.m-offline b {
  color: var(--danger);
  font-size: 13px;
}
.m-offline-detail {
  display: block;
  color: var(--text-dim);
  font-size: 12px;
  margin-top: 2px;
}
.m-tabbar {
  display: flex;
  flex-shrink: 0;
  /* 毛玻璃:半透明暗底 + 背景模糊(NapCat 风格浮动导航) */
  background: rgba(17, 17, 20, 0.78);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  border-top: 1px solid var(--border);
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
.m-tab {
  flex: 1;
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--text-dim);
  text-decoration: none;
  user-select: none;
  transition: color 0.12s ease-out;
}
.m-tab.active {
  color: var(--accent);
  font-weight: 600;
}
</style>

<script setup lang="ts">
/**
 * 移动端顶层布局(手机端管理面板):顶栏(标题)+ 内容区 + 底部 tab 导航,无侧栏/oid 输入/登出。
 * 为 /m/* 路由(代人代答/历史/记忆/人设/心情/插件/系统)提供共性外壳。
 * 鉴权由 router 守卫处理(登录后回跳原页面);oid 由各页 useObject.ensureOid 自动取。
 * 作者: 李文煜
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { NLayout, NLayoutHeader, NLayoutContent } from 'naive-ui'

const route = useRoute()
// 顶栏标题取路由 meta.title(与 PC MainLayout 一致),默认回退
const title = computed(() => (route.meta.title as string) || '清浔 3.0 管理面板')

// 底部导航七页(2026-09-08 全页适配):代答置首(手机最高频),与 /m/* 路由一一对应
const tabs = [
  { path: '/m/takeover', label: '代答' },
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
  <n-layout style="height: 100vh; display: flex; flex-direction: column">
    <n-layout-header bordered style="height:48px;padding:0 12px;display:flex;align-items:center;flex-shrink:0">
      <span style="font-weight:600;font-size:16px">{{ title }}</span>
    </n-layout-header>
    <n-layout-content content-style="padding:12px;flex:1;min-height:0" :native-scrollbar="false" style="flex:1">
      <router-view />
    </n-layout-content>
    <!-- 底部 tab 导航:7 页 2 字短标签平铺;safe-area 适配 iOS 全面屏 -->
    <nav class="m-tabbar">
      <router-link v-for="t in tabs" :key="t.path" :to="t.path"
                   class="m-tab" :class="{ active: activePath === t.path }">
        {{ t.label }}
      </router-link>
    </nav>
  </n-layout>
</template>

<style scoped>
.m-tabbar {
  display: flex;
  flex-shrink: 0;
  border-top: 1px solid #efeff5;
  background: #fff;
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
.m-tab {
  flex: 1;
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #666;
  text-decoration: none;
  user-select: none;
}
.m-tab.active {
  color: #18a058;
  font-weight: 600;
}
</style>

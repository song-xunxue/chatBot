/**
 * 路由 + access_token 鉴权守卫(V2.0 M7)
 * 菜单:人设/历史/记忆/心情/插件/系统/代人代答(训练样本已并入对话历史,2026-07-07)。
 * 作者: 李文煜
 */
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue') },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: '/history' },
      { path: 'persona', name: 'persona', component: () => import('@/views/Persona.vue'), meta: { title: '人设管理' } },
      { path: 'history', name: 'history', component: () => import('@/views/History.vue'), meta: { title: '对话历史' } },
      { path: 'memory', name: 'memory', component: () => import('@/views/Memory.vue'), meta: { title: '记忆查看' } },
      { path: 'mood', name: 'mood', component: () => import('@/views/Mood.vue'), meta: { title: '心情系统' } },
      { path: 'plugin', name: 'plugin', component: () => import('@/views/Plugin.vue'), meta: { title: '插件管理' } },
      { path: 'system', name: 'system', component: () => import('@/views/System.vue'), meta: { title: '系统配置' } },
      { path: 'takeover', name: 'takeover', component: () => import('@/views/Takeover.vue'), meta: { title: '代人代答' } },
    ],
  },
  // —— 移动端 /m/*(手机端管理面板,独立 MobileLayout+底部 tab 导航;走标准登录页鉴权)——
  // 2026-09-08 全页适配:七页对等 PC 端(窄屏重排),代答置首(手机最高频)
  {
    path: '/m',
    component: () => import('@/layouts/MobileLayout.vue'),
    children: [
      { path: '', redirect: '/m/takeover' },
      { path: 'takeover', name: 'm-takeover', component: () => import('@/views/TakeoverMobile.vue'), meta: { title: '代人代答', mobile: true } },
      { path: 'history', name: 'm-history', component: () => import('@/views/HistoryMobile.vue'), meta: { title: '对话历史', mobile: true } },
      { path: 'memory', name: 'm-memory', component: () => import('@/views/MemoryMobile.vue'), meta: { title: '记忆查看', mobile: true } },
      { path: 'persona', name: 'm-persona', component: () => import('@/views/PersonaMobile.vue'), meta: { title: '人设管理', mobile: true } },
      { path: 'mood', name: 'm-mood', component: () => import('@/views/MoodMobile.vue'), meta: { title: '心情系统', mobile: true } },
      { path: 'plugin', name: 'm-plugin', component: () => import('@/views/PluginMobile.vue'), meta: { title: '插件管理', mobile: true } },
      { path: 'system', name: 'm-system', component: () => import('@/views/SystemMobile.vue'), meta: { title: '系统配置', mobile: true } },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

// 鉴权守卫:无 token → 跳登录(带 redirect 回跳;移动端 /m/* 登录后回到原页面,比 URL ?token= 更安全)
router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  if (!token && to.name !== 'login') {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
})

export default router

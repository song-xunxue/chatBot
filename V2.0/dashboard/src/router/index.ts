/**
 * 路由 + access_token 鉴权守卫(V2.0 M7)
 * 菜单:人设/历史/记忆/心情/插件/系统/代人代答/训练样本(评分已并入对话历史,2026-07-03)。
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
      { path: 'roleplay', name: 'roleplay', component: () => import('@/views/Roleplay.vue'), meta: { title: '训练样本' } },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

// 鉴权守卫:无 token → 跳登录
router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  if (!token && to.name !== 'login') return { name: 'login' }
})

export default router

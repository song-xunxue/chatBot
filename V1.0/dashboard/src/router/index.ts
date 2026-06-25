/**
 * 路由 + access_token 鉴权守卫
 * 作者: 李文煜
 */
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue') },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: '/persona' },
      { path: 'persona', name: 'persona', component: () => import('@/views/Persona.vue'), meta: { title: '人设管理' } },
      { path: 'plugin', name: 'plugin', component: () => import('@/views/Plugin.vue'), meta: { title: '插件管理' } },
      { path: 'memory', name: 'memory', component: () => import('@/views/Memory.vue'), meta: { title: '记忆查看' } },
      { path: 'model', name: 'model', component: () => import('@/views/Model.vue'), meta: { title: '模型配置' } },
      { path: 'history', name: 'history', component: () => import('@/views/History.vue'), meta: { title: '对话历史' } },
      { path: 'roleplay', name: 'roleplay', component: () => import('@/views/Roleplay.vue'), meta: { title: '代人聊天' } },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

// 鉴权守卫：无 token → 跳登录
router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  if (!token && to.name !== 'login') return { name: 'login' }
})

export default router

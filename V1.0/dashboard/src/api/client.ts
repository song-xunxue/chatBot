/**
 * Axios 实例：自动注入 access_token（X-Access-Token 头），401 跳登录
 * baseURL 走 Vite dev proxy（/api → 服务端 :8000），生产可设 VITE_API_BASE
 * 作者: 李文煜
 */
import axios from 'axios'
import router from '@/router'

export const api = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE as string) || '',
  timeout: 30000,
})

api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('access_token')
  if (token) cfg.headers['X-Access-Token'] = token
  return cfg
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      router.push({ name: 'login' })
    }
    return Promise.reject(err)
  },
)

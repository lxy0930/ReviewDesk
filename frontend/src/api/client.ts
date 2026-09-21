import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'

const client = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE_URL ?? '') + '/api/v1',
  timeout: 30_000,  // 缩短超时时间，避免长时间占用连接
})

// 请求拦截器：注入 JWT（懒加载 store 避免循环依赖）
client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('edu-agent-token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截器：统一错误处理
client.interceptors.response.use(
  res => res,
  (error: AxiosError<{ detail: string }>) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail

    if (status === 401) {
      // 同时清除 Pinia store（响应式 token）和 localStorage，
      // 否则 auth.isLoggedIn 仍为 true，router.push('/login') 会被导航守卫重定向回 /dashboard
      useAuthStore().logout()
      router.push('/login').catch(() => {})
      return Promise.reject(error)
    }

    if (status === 403) {
      ElMessage.error('权限不足')
    } else if (status === 429) {
      ElMessage.warning('请求过于频繁，请稍后再试')
    } else if (status && status >= 500) {
      ElMessage.error(detail ?? '服务异常，请稍后重试')
    } else if (detail) {
      ElMessage.error(detail)
    }

    return Promise.reject(error)
  },
)

export default client

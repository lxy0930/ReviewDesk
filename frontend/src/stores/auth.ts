import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

interface UserInfo {
  userId: string
  role: 'student' | 'teacher' | 'admin'
  username?: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('edu-agent-token'))
  const user = ref<UserInfo | null>((() => {
    try {
      return JSON.parse(localStorage.getItem('edu-agent-user') ?? 'null')
    } catch {
      return null
    }
  })())

  const isLoggedIn = computed(() => !!token.value)
  const isTeacher = computed(() =>
    user.value?.role === 'teacher' || user.value?.role === 'admin'
  )

  function login(accessToken: string, userInfo: UserInfo) {
    token.value = accessToken
    user.value = userInfo
    localStorage.setItem('edu-agent-token', accessToken)
    localStorage.setItem('edu-agent-user', JSON.stringify(userInfo))
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('edu-agent-token')
    localStorage.removeItem('edu-agent-user')
  }

  return { token, user, isLoggedIn, isTeacher, login, logout }
})

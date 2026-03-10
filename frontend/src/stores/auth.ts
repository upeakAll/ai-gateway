import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserInfo } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<UserInfo | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  function setToken(newToken: string) {
    token.value = newToken
  }

  function setUser(newUser: UserInfo) {
    user.value = newUser
  }

  function logout() {
    token.value = null
    user.value = null
  }

  function getAuthHeader() {
    return token.value ? { Authorization: `Bearer ${token.value}` } : {}
  }

  return {
    token,
    user,
    isAuthenticated,
    setToken,
    setUser,
    logout,
    getAuthHeader
  }
}, {
  persist: true
})

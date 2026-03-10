import { api } from './client'
import type { LoginRequest, LoginResponse, UserInfo } from './types'

export const authApi = {
  login(data: LoginRequest) {
    const formData = new FormData()
    formData.append('username', data.username)
    formData.append('password', data.password)
    return api.post<LoginResponse>('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
  },

  me() {
    return api.get<UserInfo>('/auth/me')
  },

  logout() {
    return api.post('/auth/logout')
  }
}

import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

const instance: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor
instance.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore()
    const authHeader = authStore.getAuthHeader()
    config.headers = { ...config.headers, ...authHeader }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
instance.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    if (error.response) {
      const status = error.response.status

      if (status === 401) {
        const authStore = useAuthStore()
        authStore.logout()
        router.push({ name: 'login' })
        ElMessage.error('登录已过期，请重新登录')
      } else if (status === 403) {
        ElMessage.error('没有权限执行此操作')
      } else if (status === 404) {
        ElMessage.error('请求的资源不存在')
      } else if (status === 422) {
        const detail = error.response.data?.detail
        if (typeof detail === 'string') {
          ElMessage.error(detail)
        } else {
          ElMessage.error('请求参数验证失败')
        }
      } else if (status >= 500) {
        ElMessage.error('服务器错误，请稍后重试')
      }
    } else if (error.request) {
      ElMessage.error('网络连接失败')
    } else {
      ElMessage.error('请求发送失败')
    }

    return Promise.reject(error)
  }
)

export const api = {
  get<T>(url: string, config?: AxiosRequestConfig) {
    return instance.get<T>(url, config).then((res) => res.data)
  },

  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig) {
    return instance.post<T>(url, data, config).then((res) => res.data)
  },

  put<T>(url: string, data?: unknown, config?: AxiosRequestConfig) {
    return instance.put<T>(url, data, config).then((res) => res.data)
  },

  patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig) {
    return instance.patch<T>(url, data, config).then((res) => res.data)
  },

  delete<T>(url: string, config?: AxiosRequestConfig) {
    return instance.delete<T>(url, config).then((res) => res.data)
  }
}

export default instance

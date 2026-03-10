import { api } from './client'
import type { HealthStatus } from './types'

export const healthApi = {
  check() {
    return api.get<HealthStatus>('/health')
  },

  liveness() {
    return api.get<{ status: string }>('/health/live')
  },

  readiness() {
    return api.get<{ status: string }>('/health/ready')
  }
}

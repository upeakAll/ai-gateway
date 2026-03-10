import { api } from './client'
import type { UsageStatistics, UsageQuery } from './types'

export const usageApi = {
  getStatistics(params?: UsageQuery) {
    return api.get<UsageStatistics>('/dashboard/usage', { params })
  },

  getModels() {
    return api.get<string[]>('/v1/models')
  }
}

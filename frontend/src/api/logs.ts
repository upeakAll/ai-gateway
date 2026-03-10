import { api } from './client'
import type { UsageLog, UsageLogQuery, PaginatedResponse } from './types'

export const logsApi = {
  list(params?: UsageLogQuery) {
    return api.get<PaginatedResponse<UsageLog>>('/dashboard/logs', { params })
  },

  get(id: string) {
    return api.get<UsageLog>(`/dashboard/logs/${id}`)
  },

  export(params?: Omit<UsageLogQuery, 'page' | 'page_size'>) {
    return api.get<Blob>('/dashboard/logs/export', {
      params,
      responseType: 'blob'
    })
  }
}

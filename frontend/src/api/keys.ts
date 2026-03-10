import { api } from './client'
import type {
  APIKey,
  SubKey,
  CreateAPIKeyRequest,
  UpdateAPIKeyRequest,
  CreateSubKeyRequest,
  PaginatedResponse,
  PaginationParams
} from './types'

export const keysApi = {
  list(params?: PaginationParams & { tenant_id?: string }) {
    return api.get<PaginatedResponse<APIKey>>('/admin/keys', { params })
  },

  get(id: string) {
    return api.get<APIKey>(`/admin/keys/${id}`)
  },

  create(data: CreateAPIKeyRequest) {
    return api.post<APIKey>('/admin/keys', data)
  },

  update(id: string, data: UpdateAPIKeyRequest) {
    return api.patch<APIKey>(`/admin/keys/${id}`, data)
  },

  delete(id: string) {
    return api.delete(`/admin/keys/${id}`)
  },

  regenerate(id: string) {
    return api.post<APIKey>(`/admin/keys/${id}/regenerate`)
  },

  // Sub Keys
  listSubKeys(parentKeyId: string, params?: PaginationParams) {
    return api.get<PaginatedResponse<SubKey>>(`/admin/keys/${parentKeyId}/sub-keys`, { params })
  },

  createSubKey(parentKeyId: string, data: CreateSubKeyRequest) {
    return api.post<SubKey>(`/admin/keys/${parentKeyId}/sub-keys`, data)
  },

  deleteSubKey(parentKeyId: string, subKeyId: string) {
    return api.delete(`/admin/keys/${parentKeyId}/sub-keys/${subKeyId}`)
  }
}

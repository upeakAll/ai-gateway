import { api } from './client'
import type {
  Tenant,
  CreateTenantRequest,
  UpdateTenantRequest,
  PaginatedResponse,
  PaginationParams
} from './types'

export const tenantsApi = {
  list(params?: PaginationParams) {
    return api.get<PaginatedResponse<Tenant>>('/admin/tenants', { params })
  },

  get(id: string) {
    return api.get<Tenant>(`/admin/tenants/${id}`)
  },

  create(data: CreateTenantRequest) {
    return api.post<Tenant>('/admin/tenants', data)
  },

  update(id: string, data: UpdateTenantRequest) {
    return api.patch<Tenant>(`/admin/tenants/${id}`, data)
  },

  delete(id: string) {
    return api.delete(`/admin/tenants/${id}`)
  },

  addQuota(id: string, amount: number) {
    return api.post<Tenant>(`/admin/tenants/${id}/add-quota`, { amount })
  }
}

import { api } from './client'
import type {
  Channel,
  CreateChannelRequest,
  UpdateChannelRequest,
  ModelConfig,
  CreateModelConfigRequest,
  ChannelTestResult,
  PaginatedResponse,
  PaginationParams
} from './types'

export const channelsApi = {
  list(params?: PaginationParams & { provider?: string }) {
    return api.get<PaginatedResponse<Channel>>('/admin/channels', { params })
  },

  get(id: string) {
    return api.get<Channel>(`/admin/channels/${id}`)
  },

  create(data: CreateChannelRequest) {
    return api.post<Channel>('/admin/channels', data)
  },

  update(id: string, data: UpdateChannelRequest) {
    return api.patch<Channel>(`/admin/channels/${id}`, data)
  },

  delete(id: string) {
    return api.delete(`/admin/channels/${id}`)
  },

  test(id: string) {
    return api.post<ChannelTestResult>(`/admin/channels/${id}/test`)
  },

  resetCircuitBreaker(id: string) {
    return api.post<Channel>(`/admin/channels/${id}/reset-circuit-breaker`)
  },

  // Model configs
  listModelConfigs(channelId: string) {
    return api.get<ModelConfig[]>(`/admin/channels/${channelId}/models`)
  },

  createModelConfig(channelId: string, data: CreateModelConfigRequest) {
    return api.post<ModelConfig>(`/admin/channels/${channelId}/models`, data)
  },

  updateModelConfig(channelId: string, modelId: string, data: Partial<CreateModelConfigRequest>) {
    return api.patch<ModelConfig>(`/admin/channels/${channelId}/models/${modelId}`, data)
  },

  deleteModelConfig(channelId: string, modelId: string) {
    return api.delete(`/admin/channels/${channelId}/models/${modelId}`)
  }
}

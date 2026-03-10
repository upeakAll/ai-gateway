import { api } from './client'
import type {
  MCPServer,
  MCPTool,
  CreateMCPServerRequest,
  PaginatedResponse,
  PaginationParams
} from './types'

export const mcpApi = {
  listServers(params?: PaginationParams & { tenant_id?: string }) {
    return api.get<PaginatedResponse<MCPServer>>('/mcp/admin/servers', { params })
  },

  getServer(id: string) {
    return api.get<MCPServer>(`/mcp/admin/servers/${id}`)
  },

  createServer(data: CreateMCPServerRequest) {
    return api.post<MCPServer>('/mcp/admin/servers', data)
  },

  updateServer(id: string, data: Partial<CreateMCPServerRequest>) {
    return api.patch<MCPServer>(`/mcp/admin/servers/${id}`, data)
  },

  deleteServer(id: string) {
    return api.delete(`/mcp/admin/servers/${id}`)
  },

  generateFromOpenApi(serverId: string) {
    return api.post<MCPTool[]>(`/mcp/admin/servers/${serverId}/generate-from-openapi`)
  },

  listTools(serverId: string) {
    return api.get<MCPTool[]>(`/mcp/admin/servers/${serverId}/tools`)
  },

  updateTool(serverId: string, toolId: string, data: { allowed_roles?: string[] }) {
    return api.patch<MCPTool>(`/mcp/admin/servers/${serverId}/tools/${toolId}`, data)
  }
}

// User & Auth
export interface UserInfo {
  id: string
  username: string
  email: string
  role: string
  tenant_id?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

// Pagination
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface PaginationParams {
  page?: number
  page_size?: number
}

// Tenant
export interface Tenant {
  id: string
  name: string
  slug: string
  quota_total: number
  quota_used: number
  billing_mode: 'prepaid' | 'postpaid'
  routing_strategy: 'weighted' | 'cost_optimized' | 'fixed'
  fixed_channel_id?: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CreateTenantRequest {
  name: string
  slug: string
  quota_total?: number
  billing_mode?: 'prepaid' | 'postpaid'
  routing_strategy?: 'weighted' | 'cost_optimized' | 'fixed'
  fixed_channel_id?: string
}

export interface UpdateTenantRequest {
  name?: string
  quota_total?: number
  billing_mode?: 'prepaid' | 'postpaid'
  routing_strategy?: 'weighted' | 'cost_optimized' | 'fixed'
  fixed_channel_id?: string
  is_active?: boolean
}

// API Key
export interface APIKey {
  id: string
  tenant_id: string
  key: string
  name: string
  quota_total: number
  quota_used: number
  rpm_limit: number
  tpm_limit: number
  allowed_models: string[]
  is_active: boolean
  expires_at?: string
  created_at: string
  updated_at: string
}

export interface CreateAPIKeyRequest {
  tenant_id: string
  name: string
  quota_total?: number
  rpm_limit?: number
  tpm_limit?: number
  allowed_models?: string[]
  expires_at?: string
}

export interface UpdateAPIKeyRequest {
  name?: string
  quota_total?: number
  rpm_limit?: number
  tpm_limit?: number
  allowed_models?: string[]
  is_active?: boolean
  expires_at?: string
}

// Sub Key
export interface SubKey {
  id: string
  parent_key_id: string
  key: string
  name: string
  quota_total: number
  quota_used: number
  rpm_limit: number
  is_active: boolean
  created_at: string
}

export interface CreateSubKeyRequest {
  name: string
  quota_total?: number
  rpm_limit?: number
}

// Channel
export interface Channel {
  id: string
  tenant_id?: string
  provider: string
  name: string
  api_key: string
  api_base: string
  weight: number
  priority: number
  health_status: 'healthy' | 'degraded' | 'unhealthy'
  circuit_breaker_state: 'closed' | 'open' | 'half_open'
  avg_response_time: number
  total_requests: number
  success_requests: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CreateChannelRequest {
  tenant_id?: string
  provider: string
  name: string
  api_key: string
  api_base?: string
  weight?: number
  priority?: number
}

export interface UpdateChannelRequest {
  name?: string
  api_key?: string
  api_base?: string
  weight?: number
  priority?: number
  is_active?: boolean
}

export interface ChannelTestResult {
  success: boolean
  latency_ms: number
  error?: string
}

// Model Config
export interface ModelConfig {
  id: string
  channel_id: string
  model_name: string
  real_model_name: string
  input_price_per_1k: number
  output_price_per_1k: number
  max_tokens: number
  is_active: boolean
}

export interface CreateModelConfigRequest {
  model_name: string
  real_model_name: string
  input_price_per_1k?: number
  output_price_per_1k?: number
  max_tokens?: number
}

// Usage Log
export interface UsageLog {
  id: string
  request_id: string
  tenant_id: string
  api_key_id: string
  channel_id: string
  model_name: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost_usd: number
  latency_ms: number
  status: 'success' | 'error'
  error_message?: string
  created_at: string
}

export interface UsageLogQuery extends PaginationParams {
  tenant_id?: string
  api_key_id?: string
  channel_id?: string
  model_name?: string
  status?: 'success' | 'error'
  start_time?: string
  end_time?: string
}

// Usage Statistics
export interface UsageStatistics {
  total_requests: number
  total_tokens: number
  total_cost: number
  avg_latency_ms: number
  success_rate: number
  by_model: ModelUsage[]
  by_date: DateUsage[]
}

export interface ModelUsage {
  model_name: string
  requests: number
  tokens: number
  cost: number
}

export interface DateUsage {
  date: string
  requests: number
  tokens: number
  cost: number
}

export interface UsageQuery {
  tenant_id?: string
  start_date?: string
  end_date?: string
  group_by?: 'model' | 'date' | 'channel' | 'key'
}

// MCP Server
export interface MCPServer {
  id: string
  tenant_id: string
  name: string
  description?: string
  config_type: 'openapi' | 'custom'
  openapi_url?: string
  transport: 'sse' | 'http'
  status: 'active' | 'inactive' | 'error'
  created_at: string
  updated_at: string
}

export interface CreateMCPServerRequest {
  tenant_id: string
  name: string
  description?: string
  config_type: 'openapi' | 'custom'
  openapi_url?: string
  transport?: 'sse' | 'http'
}

export interface MCPTool {
  id: string
  server_id: string
  name: string
  description: string
  input_schema: Record<string, unknown>
  required_permission: string
  allowed_roles: string[]
}

// Health
export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy'
  version: string
  components: {
    database: 'up' | 'down'
    redis: 'up' | 'down'
  }
}

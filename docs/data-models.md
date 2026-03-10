# 数据模型

## ER 图

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   Tenant    │       │   APIKey    │       │   SubKey    │
├─────────────┤       ├─────────────┤       ├─────────────┤
│ id (PK)     │←──────│ tenant_id   │       │ parent_key  │
│ name        │       │ id (PK)     │←──────│ id (PK)     │
│ slug        │       │ key         │       │ key         │
│ quota_total │       │ name        │       │ name        │
│ quota_used  │       │ quota_total │       │ quota_total │
│ billing_mode│       │ quota_used  │       │ quota_used  │
│ routing_    │       │ rpm_limit   │       │ rpm_limit   │
│ strategy    │       │ tpm_limit   │       │ is_active   │
│ fixed_      │       │ allowed_    │       │ created_at  │
│ channel_id  │       │ models      │       └─────────────┘
│ is_active   │       │ is_active   │
│ created_at  │       │ expires_at  │       ┌─────────────┐
│ updated_at  │       │ created_at  │       │  MCPServer  │
└─────────────┘       │ updated_at  │       ├─────────────┤
                      └─────────────┘       │ id (PK)     │
                                            │ tenant_id   │
┌─────────────┐       ┌─────────────┐       │ name        │
│   Channel   │       │ ModelConfig │       │ config_type │
├─────────────┤       ├─────────────┤       │ openapi_url │
│ id (PK)     │←──────│ channel_id  │       │ transport   │
│ tenant_id   │       │ id (PK)     │       │ status      │
│ provider    │       │ model_name  │       │ created_at  │
│ name        │       │ real_model  │       └─────────────┘
│ api_key     │       │ input_price │
│ api_base    │       │ output_price│       ┌─────────────┐
│ weight      │       │ max_tokens  │       │   MCPTool   │
│ priority    │       │ is_active   │       ├─────────────┤
│ health_     │       └─────────────┘       │ id (PK)     │
│ status      │                             │ server_id   │
│ circuit_    │       ┌─────────────┐       │ name        │
│ breaker_    │       │  UsageLog   │       │ description │
│ state       │       ├─────────────┤       │ input_schema│
│ avg_        │       │ id (PK)     │       │ required_   │
│ response_   │       │ request_id  │       │ permission  │
│ time        │       │ tenant_id   │       │ allowed_    │
│ total_      │       │ api_key_id  │       │ roles       │
│ requests    │       │ channel_id  │       └─────────────┘
│ success_    │       │ model_name  │
│ requests    │       │ prompt_     │       ┌─────────────┐
│ is_active   │       │ tokens      │       │    Role     │
│ created_at  │       │ completion_ │       ├─────────────┤
│ updated_at  │       │ tokens      │       │ id (PK)     │
└─────────────┘       │ total_tokens│       │ name        │
                      │ cost_usd    │       │ description │
                      │ latency_ms  │       │ permissions │
                      │ status      │       │ is_system   │
                      │ error_msg   │       │ created_at  │
                      │ created_at  │       └─────────────┘
                      └─────────────┘
```

---

## 表结构详情

### tenants (租户表)

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    quota_total DECIMAL(12, 2) DEFAULT 0.00,
    quota_used DECIMAL(12, 2) DEFAULT 0.00,
    billing_mode VARCHAR(20) DEFAULT 'prepaid',  -- prepaid, postpaid
    routing_strategy VARCHAR(50) DEFAULT 'weighted',  -- weighted, cost_optimized, fixed
    fixed_channel_id UUID REFERENCES channels(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_tenants_slug ON tenants(slug);
CREATE INDEX idx_tenants_is_active ON tenants(is_active);
```

### api_keys (API Key 表)

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key VARCHAR(255) UNIQUE NOT NULL,  -- sk-xxx 格式
    name VARCHAR(255) NOT NULL,
    quota_total DECIMAL(12, 2) DEFAULT 0.00,
    quota_used DECIMAL(12, 2) DEFAULT 0.00,
    rpm_limit INTEGER DEFAULT 60,
    tpm_limit INTEGER DEFAULT 100000,
    allowed_models TEXT[],  -- 允许的模型列表
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_api_keys_tenant ON api_keys(tenant_id);
CREATE UNIQUE INDEX idx_api_keys_key ON api_keys(key);
CREATE INDEX idx_api_keys_is_active ON api_keys(is_active);
```

### sub_keys (子 Key 表)

```sql
CREATE TABLE sub_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    key VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    quota_total DECIMAL(12, 2) DEFAULT 0.00,
    quota_used DECIMAL(12, 2) DEFAULT 0.00,
    rpm_limit INTEGER DEFAULT 30,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_sub_keys_parent ON sub_keys(parent_key_id);
CREATE UNIQUE INDEX idx_sub_keys_key ON sub_keys(key);
```

### channels (渠道表)

```sql
CREATE TABLE channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    provider VARCHAR(50) NOT NULL,  -- openai, anthropic, azure, etc.
    name VARCHAR(255) NOT NULL,
    api_key VARCHAR(512) NOT NULL,  -- 加密存储
    api_base VARCHAR(512),
    weight INTEGER DEFAULT 100,
    priority INTEGER DEFAULT 1,
    health_status VARCHAR(20) DEFAULT 'healthy',  -- healthy, degraded, unhealthy
    circuit_breaker_state VARCHAR(20) DEFAULT 'closed',  -- closed, open, half_open
    avg_response_time INTEGER DEFAULT 0,  -- ms
    total_requests INTEGER DEFAULT 0,
    success_requests INTEGER DEFAULT 0,
    last_request_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_channels_provider ON channels(provider);
CREATE INDEX idx_channels_tenant ON channels(tenant_id);
CREATE INDEX idx_channels_is_active ON channels(is_active);
CREATE INDEX idx_channels_health ON channels(health_status);
```

### model_configs (模型配置表)

```sql
CREATE TABLE model_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,  -- 对外展示名称
    real_model_name VARCHAR(100) NOT NULL,  -- 实际调用的模型名
    input_price_per_1k DECIMAL(8, 6) DEFAULT 0.01,  -- 每1K输入token价格
    output_price_per_1k DECIMAL(8, 6) DEFAULT 0.03,  -- 每1K输出token价格
    max_tokens INTEGER DEFAULT 4096,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_model_configs_channel ON model_configs(channel_id);
CREATE UNIQUE INDEX idx_model_configs_name ON model_configs(channel_id, model_name);
```

### usage_logs (使用日志表)

```sql
-- 按月分区
CREATE TABLE usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL,
    tenant_id UUID NOT NULL,
    api_key_id UUID NOT NULL,
    channel_id UUID NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_usd DECIMAL(10, 6) DEFAULT 0.00,
    latency_ms INTEGER DEFAULT 0,
    status VARCHAR(20) NOT NULL,  -- success, error
    error_message TEXT,
    metadata JSONB,  -- 扩展字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
) PARTITION BY RANGE (created_at);

-- 创建月度分区
CREATE TABLE usage_logs_2026_03 PARTITION OF usage_logs
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE INDEX idx_usage_logs_tenant ON usage_logs(tenant_id);
CREATE INDEX idx_usage_logs_api_key ON usage_logs(api_key_id);
CREATE INDEX idx_usage_logs_channel ON usage_logs(channel_id);
CREATE INDEX idx_usage_logs_created ON usage_logs(created_at);
CREATE INDEX idx_usage_logs_status ON usage_logs(status);
```

### mcp_servers (MCP 服务器表)

```sql
CREATE TABLE mcp_servers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    config_type VARCHAR(20) NOT NULL,  -- openapi, custom
    openapi_url VARCHAR(512),
    transport VARCHAR(20) DEFAULT 'sse',  -- sse, http
    config JSONB,  -- 服务器配置
    status VARCHAR(20) DEFAULT 'active',  -- active, inactive, error
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_mcp_servers_tenant ON mcp_servers(tenant_id);
CREATE UNIQUE INDEX idx_mcp_servers_name ON mcp_servers(tenant_id, name);
```

### mcp_tools (MCP 工具表)

```sql
CREATE TABLE mcp_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    input_schema JSONB NOT NULL,  -- JSON Schema
    required_permission VARCHAR(100),
    allowed_roles TEXT[] DEFAULT ARRAY['admin', 'developer'],
    executor_type VARCHAR(20) DEFAULT 'http',  -- http, python
    executor_config JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_mcp_tools_server ON mcp_tools(server_id);
CREATE UNIQUE INDEX idx_mcp_tools_name ON mcp_tools(server_id, name);
```

### roles (角色表)

```sql
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    permissions TEXT[] NOT NULL,
    is_system BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 预置角色
INSERT INTO roles (name, description, permissions, is_system) VALUES
('admin', '管理员', ARRAY['*'], TRUE),
('developer', '开发者', ARRAY['keys:read', 'keys:write', 'logs:read', 'usage:read'], TRUE),
('viewer', '查看者', ARRAY['logs:read', 'usage:read'], TRUE);
```

---

## 索引策略

### 主键索引
- 所有表使用 UUID 主键
- 自动创建 B-tree 索引

### 外键索引
- 所有外键字段创建索引
- 支持级联查询优化

### 查询优化索引
- 时间范围查询: `created_at` 字段
- 状态过滤: `is_active`, `status` 字段
- 唯一约束: `slug`, `key`, `name` 组合

### 分区策略
- `usage_logs` 按月分区
- 自动创建下月分区
- 历史分区归档到冷存储

---

## 数据迁移

### 初始化迁移

```bash
cd backend
alembic upgrade head
```

### 创建新迁移

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### 回滚迁移

```bash
alembic downgrade -1  # 回滚一个版本
```

---

*最后更新: 2026-03-10*

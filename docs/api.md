# API 文档

## 基础信息

- **Base URL**: `http://localhost:8000`
- **认证方式**: Bearer Token (API Key)
- **内容类型**: `application/json`

---

## OpenAI 兼容 API

### Chat Completions

创建聊天补全。

```http
POST /v1/chat/completions
Authorization: Bearer sk-xxx
Content-Type: application/json
```

**请求体**

```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

**参数说明**

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| model | string | 是 | 模型名称 |
| messages | array | 是 | 消息列表 |
| temperature | number | 否 | 温度参数 (0-2) |
| max_tokens | integer | 否 | 最大生成 token 数 |
| stream | boolean | 否 | 是否流式响应 |
| top_p | number | 否 | Top-p 采样 |
| stop | array | 否 | 停止词列表 |

**响应 (非流式)**

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "gpt-4o",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 10,
    "total_tokens": 30
  }
}
```

**响应 (流式)**

```
data: {"id":"chatcmpl-xxx","choices":[{"delta":{"content":"Hello"},"index":0}]}

data: {"id":"chatcmpl-xxx","choices":[{"delta":{"content":"!"},"index":0}]}

data: [DONE]
```

---

### Embeddings

创建文本嵌入向量。

```http
POST /v1/embeddings
Authorization: Bearer sk-xxx
Content-Type: application/json
```

**请求体**

```json
{
  "model": "text-embedding-3-small",
  "input": "Hello world"
}
```

**响应**

```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.1, 0.2, 0.3, ...]
    }
  ],
  "model": "text-embedding-3-small",
  "usage": {
    "prompt_tokens": 2,
    "total_tokens": 2
  }
}
```

---

### Models

列出可用模型。

```http
GET /v1/models
Authorization: Bearer sk-xxx
```

**响应**

```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-4o",
      "object": "model",
      "created": 1700000000,
      "owned_by": "openai"
    }
  ]
}
```

---

## Anthropic 兼容 API

### Messages

创建消息 (Anthropic 格式)。

```http
POST /v1/messages
Authorization: Bearer sk-xxx
Content-Type: application/json
```

**请求体**

```json
{
  "model": "claude-3-5-sonnet-20241022",
  "max_tokens": 1024,
  "messages": [
    {"role": "user", "content": "Hello!"}
  ]
}
```

**响应**

```json
{
  "id": "msg_xxx",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Hello! How can I help you?"
    }
  ],
  "model": "claude-3-5-sonnet-20241022",
  "usage": {
    "input_tokens": 10,
    "output_tokens": 20
  }
}
```

---

## 管理 API

### 租户管理

#### 创建租户

```http
POST /admin/tenants
Content-Type: application/json
```

```json
{
  "name": "Acme Corp",
  "slug": "acme-corp",
  "quota_total": 1000.00,
  "billing_mode": "prepaid",
  "routing_strategy": "weighted"
}
```

#### 列出租户

```http
GET /admin/tenants?page=1&page_size=20
```

#### 获取租户

```http
GET /admin/tenants/{tenant_id}
```

#### 更新租户

```http
PATCH /admin/tenants/{tenant_id}
```

#### 删除租户

```http
DELETE /admin/tenants/{tenant_id}
```

#### 充值配额

```http
POST /admin/tenants/{tenant_id}/add-quota
```

```json
{
  "amount": 100.00
}
```

---

### API Key 管理

#### 创建 Key

```http
POST /admin/keys
```

```json
{
  "tenant_id": "xxx",
  "name": "Production Key",
  "quota_total": 100.00,
  "rpm_limit": 60,
  "tpm_limit": 100000,
  "allowed_models": ["gpt-4o", "gpt-3.5-turbo"]
}
```

#### 列出 Keys

```http
GET /admin/keys?page=1&page_size=20
```

#### 获取 Key

```http
GET /admin/keys/{key_id}
```

#### 更新 Key

```http
PATCH /admin/keys/{key_id}
```

#### 删除 Key

```http
DELETE /admin/keys/{key_id}
```

#### 重新生成 Key

```http
POST /admin/keys/{key_id}/regenerate
```

---

### 子 Key 管理

#### 列出子 Keys

```http
GET /admin/keys/{key_id}/sub-keys
```

#### 创建子 Key

```http
POST /admin/keys/{key_id}/sub-keys
```

```json
{
  "name": "Dev Sub Key",
  "quota_total": 10.00,
  "rpm_limit": 30
}
```

#### 删除子 Key

```http
DELETE /admin/keys/{key_id}/sub-keys/{sub_key_id}
```

---

### 渠道管理

#### 创建渠道

```http
POST /admin/channels
```

```json
{
  "provider": "openai",
  "name": "OpenAI Primary",
  "api_key": "sk-xxx",
  "api_base": "https://api.openai.com/v1",
  "weight": 100,
  "priority": 1
}
```

#### 列出渠道

```http
GET /admin/channels?page=1&page_size=20
```

#### 更新渠道

```http
PATCH /admin/channels/{channel_id}
```

#### 删除渠道

```http
DELETE /admin/channels/{channel_id}
```

#### 测试渠道

```http
POST /admin/channels/{channel_id}/test
```

**响应**

```json
{
  "success": true,
  "latency_ms": 250
}
```

#### 重置熔断器

```http
POST /admin/channels/{channel_id}/reset-circuit-breaker
```

---

### 模型配置

#### 列出模型配置

```http
GET /admin/channels/{channel_id}/models
```

#### 创建模型配置

```http
POST /admin/channels/{channel_id}/models
```

```json
{
  "model_name": "gpt-4o",
  "real_model_name": "gpt-4o-2024-08-06",
  "input_price_per_1k": 0.005,
  "output_price_per_1k": 0.015,
  "max_tokens": 128000
}
```

#### 删除模型配置

```http
DELETE /admin/channels/{channel_id}/models/{model_id}
```

---

## MCP API

### 服务器管理

#### 创建 MCP 服务器

```http
POST /mcp/admin/servers
```

```json
{
  "tenant_id": "xxx",
  "name": "Weather Tools",
  "description": "Weather information tools",
  "config_type": "openapi",
  "openapi_url": "https://api.weather.com/openapi.json",
  "transport": "sse"
}
```

#### 列出服务器

```http
GET /mcp/admin/servers
```

#### 删除服务器

```http
DELETE /mcp/admin/servers/{server_id}
```

#### 从 OpenAPI 生成工具

```http
POST /mcp/admin/servers/{server_id}/generate-from-openapi
```

### SSE 端点

MCP 客户端连接端点：

```
GET /mcp/{server_name}/sse
```

---

## 监控 API

### 健康检查

```http
GET /health
```

**响应**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "components": {
    "database": "up",
    "redis": "up"
  }
}
```

### 存活探针

```http
GET /health/live
```

### 就绪探针

```http
GET /health/ready
```

### Prometheus 指标

```http
GET /metrics
```

---

## 用量和日志 API

### 用量统计

```http
GET /dashboard/usage?start_date=2026-03-01&end_date=2026-03-10&group_by=model
```

**响应**

```json
{
  "total_requests": 10000,
  "total_tokens": 5000000,
  "total_cost": 125.50,
  "avg_latency_ms": 350,
  "success_rate": 0.995,
  "by_model": [
    {
      "model_name": "gpt-4o",
      "requests": 5000,
      "tokens": 3000000,
      "cost": 100.00
    }
  ],
  "by_date": [...]
}
```

### 日志查询

```http
GET /dashboard/logs?page=1&page_size=20&status=success&model_name=gpt-4o
```

**响应**

```json
{
  "items": [
    {
      "id": "xxx",
      "request_id": "req-xxx",
      "tenant_id": "tenant-xxx",
      "model_name": "gpt-4o",
      "prompt_tokens": 100,
      "completion_tokens": 200,
      "total_tokens": 300,
      "cost_usd": 0.0035,
      "latency_ms": 350,
      "status": "success",
      "created_at": "2026-03-10T10:00:00Z"
    }
  ],
  "total": 1000,
  "page": 1,
  "page_size": 20
}
```

### 日志导出

```http
GET /dashboard/logs/export?start_time=2026-03-01&end_time=2026-03-10
```

返回 CSV 文件下载。

---

## 错误响应

所有错误响应格式：

```json
{
  "detail": "Error message"
}
```

### 常见错误码

| 状态码 | 描述 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 422 | 参数验证失败 |
| 429 | 请求限流 |
| 500 | 服务器错误 |
| 502 | 上游服务错误 |
| 503 | 服务不可用 |

---

## 速率限制

响应头包含限流信息：

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 55
X-RateLimit-Reset: 1700000060
```

---

*最后更新: 2026-03-10*

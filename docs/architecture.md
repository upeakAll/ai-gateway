# 架构设计

## 系统架构图

```
                                    ┌─────────────────────────────────────────┐
                                    │              客户端应用                  │
                                    │   (Web/Mobile/CLI/第三方集成)            │
                                    └────────────────┬────────────────────────┘
                                                     │
                                                     ▼
                                    ┌─────────────────────────────────────────┐
                                    │              Nginx / Ingress            │
                                    │         (反向代理 + SSL终结)             │
                                    └────────────────┬────────────────────────┘
                                                     │
                                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────┐
│                              AI Gateway (FastAPI)                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │
│  │ Auth Layer  │  │ Rate Limiter│  │   Router    │  │  Resilience │               │
│  │ (API Key)   │→ │ (Redis)     │→ │ (策略选择)   │→ │ (重试/熔断) │               │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘               │
│                                                            │                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐      │
│  │                        Adapter Layer (适配器层)                          │      │
│  │  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │      │
│  │  │ OpenAI  │ │Anthropic │ │  Azure  │ │ Bedrock │ │ 国内厂商 │          │      │
│  │  └─────────┘ └──────────┘ └─────────┘ └─────────┘ └─────────┘          │      │
│  └─────────────────────────────────────────────────────────────────────────┘      │
│                                                            │                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │
│  │   Billing   │  │    MCP      │  │   Logging   │  │  Metrics    │               │
│  │  (计费扣费)  │  │  (协议支持) │  │  (日志记录)  │  │ (Prometheus)│               │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘               │
└────────────────────────────────────────────────────────────────────────────────────┘
                          │                              │
                          ▼                              ▼
          ┌──────────────────────────┐    ┌──────────────────────────┐
          │      PostgreSQL          │    │         Redis            │
          │  (租户/Key/渠道/日志)     │    │  (限流/缓存/会话)         │
          └──────────────────────────┘    └──────────────────────────┘
```

## 核心模块

### 1. API 层 (app/api/)

负责处理所有 HTTP 请求，包括：

- **OpenAI 兼容端点** (`/v1/chat/completions`, `/v1/embeddings`, `/v1/models`)
- **Anthropic 兼容端点** (`/v1/messages`)
- **管理端点** (`/admin/*`)
- **MCP 端点** (`/mcp/*`)
- **监控端点** (`/health`, `/metrics`, `/dashboard/*`)

### 2. 适配器层 (app/adapters/)

统一封装不同 LLM 提供商的 API 差异：

```
BaseAdapter (抽象基类)
├── OpenAIAdapter
├── AnthropicAdapter
├── AzureOpenAIAdapter
├── BedrockAdapter
├── AliyunAdapter (通义千问)
├── BaiduAdapter (文心一言)
├── ZhipuAdapter (智谱GLM)
├── DeepSeekAdapter
├── MiniMaxAdapter
├── MoonshotAdapter
├── BaichuanAdapter
├── OllamaAdapter
└── VLLMAdapter
```

### 3. 路由层 (app/routing/)

负责渠道选择和流量调度：

- **加权轮询** (Weighted Round Robin)
- **成本优先** (Cost Optimized)
- **延迟优先** (Latency Optimized)
- **固定路由** (Fixed Tenant)

### 4. 限流层 (app/storage/redis.py)

多级别限流控制：

```
请求 → Global限流 → Tenant限流 → Key限流 → Channel限流 → 处理
```

使用 Redis + Lua 脚本实现原子性限流。

### 5. 弹性策略层 (app/resilience/)

保证系统稳定性：

- **重试**: 指数退避 + 抖动
- **熔断器**: CLOSED → OPEN → HALF_OPEN 状态机
- **降级**: 模型降级、渠道降级、默认响应
- **健康检查**: 主动探测 + 被动统计

### 6. 计费层 (app/billing/)

精确的用量计费：

- **Token 级别计费**: 输入/输出分别定价
- **配额管理**: 预付费/后付费模式
- **发票生成**: 自动生成账单
- **用量统计**: 多维度报表

### 7. MCP 协议层 (app/mcp/)

完整实现 MCP 2025-03-26 版本：

- **传输层**: SSE + HTTP
- **工具**: 注册、执行、OpenAPI 生成
- **资源**: 静态/动态资源提供
- **提示词**: 模板化管理
- **权限**: RBAC + 工具级控制

## 数据流

### Chat Completion 请求流程

```
1. 客户端请求 → POST /v1/chat/completions
2. 认证中间件 → 验证 API Key，加载租户信息
3. 限流检查 → 多级别限流验证
4. 模型解析 → 确定目标模型
5. 渠道选择 → 根据路由策略选择渠道
6. 弹性包装 → 熔断器检查
7. 适配器调用 → 转换请求格式，调用上游 API
8. 响应转换 → 统一响应格式
9. 计费记录 → 记录 Token 消耗，扣减配额
10. 返回响应 → 流式或非流式返回
```

### 流式响应处理

```
客户端 ← SSE Stream ← AI Gateway ← SSE Stream ← LLM Provider
         ↑               ↑
         └── 心跳保活 ───┘
```

## 技术选型理由

| 组件 | 选择 | 理由 |
|------|------|------|
| Web框架 | FastAPI | 异步原生，高性能，自动文档 |
| ORM | SQLAlchemy 2.0 | 成熟稳定，异步支持，类型安全 |
| 数据库 | PostgreSQL | 企业级可靠性，JSON支持，扩展性 |
| 缓存 | Redis | 高性能，丰富数据结构，限流支持 |
| HTTP客户端 | httpx | 异步支持，HTTP/2，连接池 |
| 前端框架 | Vue 3 | 组合式API，TypeScript支持 |
| UI组件库 | Element Plus | 企业级组件，完整中文支持 |
| 状态管理 | Pinia | Vue 3 原生，TypeScript友好 |

## 扩展性设计

### 添加新的 LLM 提供商

1. 继承 `BaseAdapter` 类
2. 实现 `chat()`, `embed()`, `stream_chat()` 方法
3. 在 `AdapterRegistry` 注册

```python
class NewProviderAdapter(BaseAdapter):
    async def chat(self, request: ChatRequest) -> ChatResponse:
        # 实现调用逻辑
        pass

# 注册
registry.register("new_provider", NewProviderAdapter)
```

### 添加新的路由策略

1. 实现 `RoutingStrategy` 接口
2. 在 `ChannelSelector` 中注册

```python
class NewRoutingStrategy(RoutingStrategy):
    def select(self, channels: List[Channel], request: ChatRequest) -> Channel:
        # 实现选择逻辑
        pass
```

### 添加新的限流维度

1. 在限流中间件中添加检查点
2. 定义限流 Key 生成规则

## 性能优化

### 连接池

- PostgreSQL: `asyncpg` 连接池
- Redis: `redis-py` 连接池
- HTTP: `httpx` 连接池

### 缓存策略

- 模型配置缓存: Redis 5分钟
- 渠道状态缓存: Redis 30秒
- 健康检查结果: 内存缓存

### 异步处理

- 所有 I/O 操作异步化
- 并行请求处理
- 流式响应零拷贝

## 安全设计

### 认证

- API Key 认证 (sk-xxx 格式)
- OAuth2/OIDC 集成

### 授权

- 租户隔离
- RBAC 权限控制
- MCP 工具级权限

### 数据安全

- API Key 加密存储
- 日志脱敏
- 传输加密 (TLS)

---

*最后更新: 2026-03-10*

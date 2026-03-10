# AI Gateway 设计文档

## 文档目录

| 文档 | 描述 |
|------|------|
| [架构设计](./architecture.md) | 系统整体架构、模块划分、技术选型 |
| [API文档](./api.md) | 所有API端点详细说明 |
| [数据模型](./data-models.md) | 数据库表结构设计 |
| [适配器设计](./adapters.md) | LLM适配器框架和各厂商实现 |
| [MCP协议](./mcp-protocol.md) | MCP协议实现细节 |
| [弹性策略](./resilience.md) | 重试、熔断、降级策略 |
| [计费系统](./billing.md) | 计费模式和配额管理 |
| [前端设计](./frontend.md) | Vue 3前端架构 |
| [部署指南](./deployment.md) | Docker和Kubernetes部署 |
| [开发指南](./development.md) | 本地开发和测试 |

---

## 项目概述

AI Gateway 是一个生产级的企业AI网关系统，提供：

### 核心功能

- **多模型接入**: 支持 OpenAI、Anthropic、Azure、Bedrock 及国内主流厂商
- **统一API**: OpenAI 兼容的 `/v1/chat/completions` 接口
- **协议转换**: OpenAI 与 Anthropic 格式自动转换
- **限流控制**: Key/租户/渠道级别 RPM/TPM 限制
- **弹性策略**: 重试、熔断、降级完整支持
- **计费系统**: Token 级别精确计费，预付费/后付费模式
- **MCP协议**: 完整实现 2025-03-26 版本规范
- **用量看板**: 多维度统计和可视化

### 技术栈

**后端**
- Python 3.12 + FastAPI
- SQLAlchemy 2.0 (async)
- PostgreSQL + Redis
- Alembic 数据库迁移

**前端**
- Vue 3 + TypeScript
- Element Plus UI
- Pinia 状态管理
- ECharts 图表

**部署**
- Docker + Docker Compose
- Kubernetes (Deployment, Service, Ingress, HPA)

### 性能目标

- QPS: 100-1000
- 延迟: P99 < 50ms (不含LLM推理时间)
- 可用性: 99.9%

---

## 快速开始

```bash
# 后端开发
cd backend
uv sync
uv run uvicorn app.main:app --reload

# 前端开发
cd frontend
pnpm install
pnpm run dev

# Docker 部署
cd deploy/docker
docker-compose up -d
```

---

## 项目结构

```
ai-gateway/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── main.py            # 应用入口
│   │   ├── config.py          # 配置管理
│   │   ├── core/              # 核心模块
│   │   ├── models/            # 数据模型
│   │   ├── schemas/           # Pydantic 模式
│   │   ├── adapters/          # LLM 适配器
│   │   ├── routing/           # 路由策略
│   │   ├── resilience/        # 弹性策略
│   │   ├── mcp/               # MCP 协议
│   │   ├── billing/           # 计费模块
│   │   ├── services/          # 业务服务
│   │   ├── storage/           # 存储层
│   │   └── api/               # API 端点
│   ├── migrations/            # 数据库迁移
│   ├── tests/                 # 测试
│   └── pyproject.toml
├── frontend/                   # Vue 3 前端
│   ├── src/
│   │   ├── api/               # API 调用
│   │   ├── views/             # 页面
│   │   ├── stores/            # 状态管理
│   │   ├── router/            # 路由
│   │   └── layouts/           # 布局
│   └── package.json
├── deploy/                     # 部署配置
│   ├── docker/
│   └── k8s/
├── docs/                       # 文档
└── README.md
```

---

*最后更新: 2026-03-10*

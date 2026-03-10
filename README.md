# AI Gateway

A production-grade AI Gateway for managing LLM provider access with unified APIs, rate limiting, billing, and MCP protocol support.

## Features

- **Multi-Provider Support**: OpenAI, Anthropic, Azure OpenAI, AWS Bedrock, and domestic Chinese providers
- **OpenAI-Compatible API**: Drop-in replacement for OpenAI API clients
- **Rate Limiting**: Multi-level rate limiting (global, tenant, key, channel) with Redis-backed sliding windows
- **Flexible Routing**: Weighted round-robin, cost-optimized, latency-optimized, and fixed routing strategies
- **Token-Level Billing**: Precise quota management with prepaid and postpaid modes
- **MCP Protocol**: Full support for Model Context Protocol (2025-03-26) with SSE transport
- **Resilience**: Circuit breaker, retry with exponential backoff, and fallback support
- **Observability**: Prometheus metrics, structured logging, and comprehensive usage analytics

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 16+
- Redis 7+

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/ai-gateway.git
cd ai-gateway

# Install dependencies
make install

# Or with UV (faster)
make install-uv
```

### Local Development

```bash
# Start PostgreSQL and Redis
make db-setup

# Run database migrations
make migrate

# Start the development server
make dev
```

The API will be available at http://localhost:8000 with interactive docs at http://localhost:8000/docs.

### Docker Deployment

```bash
# Build and run all services
make docker-build
make docker-up

# View logs
make docker-logs

# Stop services
make docker-down
```

### Kubernetes Deployment

```bash
# Apply all resources
make k8s-apply

# View logs
make k8s-logs
```

## Configuration

Configuration is managed via environment variables. See `.env.example` for all available options.

Key configurations:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection URL | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `SECRET_KEY` | Secret key for JWT signing | Required (32+ chars) |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` |
| `RATE_LIMIT_DEFAULT_RPM` | Default requests per minute | `60` |

## API Usage

### Authentication

All API requests require an API key. Include it in the `Authorization` header:

```bash
curl -H "Authorization: Bearer sk-xxx" http://localhost:8000/v1/chat/completions
```

### Chat Completions

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Streaming

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'
```

### Embeddings

```bash
curl -X POST http://localhost:8000/v1/embeddings \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "text-embedding-3-small",
    "input": "Hello world"
  }'
```

## Admin API

### Create Tenant

```bash
curl -X POST http://localhost:8000/admin/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Company",
    "slug": "my-company",
    "quota_total": 100.00
  }'
```

### Create API Key

```bash
curl -X POST http://localhost:8000/admin/keys \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-uuid",
    "name": "Production Key",
    "rpm_limit": 100
  }'
```

### Create Channel

```bash
curl -X POST http://localhost:8000/admin/channels \
  -H "Content-Type: application/json" \
  -d '{
    "name": "OpenAI US",
    "provider": "openai",
    "api_key": "sk-openai-key",
    "weight": 1
  }'
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      AI Gateway                              │
├─────────────────────────────────────────────────────────────┤
│  API Layer                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ OpenAI   │ │Anthropic │ │  Admin   │ │   MCP    │       │
│  │ /v1/*    │ │/v1/msg   │ │/admin/*  │ │  /mcp/*  │       │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │
├───────┴────────────┴────────────┴────────────┴──────────────┤
│  Core Services                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ Adapter  │ │ Routing  │ │Rate Limit│ │ Billing  │       │
│  │ Registry │ │ Strategy │ │  Redis   │ │  Engine  │       │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │
├───────┴────────────┴────────────┴────────────┴──────────────┤
│  Provider Adapters                                          │
│  ┌────────┐ ┌─────────┐ ┌───────┐ ┌─────────┐ ┌─────────┐  │
│  │ OpenAI │ │Anthropic│ │ Azure │ │Bedrock  │ │ Chinese │  │
│  └────────┘ └─────────┘ └───────┘ └─────────┘ └─────────┘  │
├─────────────────────────────────────────────────────────────┤
│  Storage                                                    │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │   PostgreSQL    │  │      Redis      │                  │
│  │  (持久化数据)    │  │   (缓存/限流)    │                  │
│  └─────────────────┘  └─────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

## Development

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
cd backend && python -m pytest tests/unit_tests/test_security.py -v
```

### Code Quality

```bash
# Format code
make format

# Run linting
make lint
```

### Database Migrations

```bash
# Create a new migration
make migrate-new

# Apply migrations
make migrate

# Rollback one migration
make migrate-down
```

## Project Structure

```
ai-gateway/
├── backend/
│   ├── app/
│   │   ├── api/           # API endpoints
│   │   ├── adapters/      # LLM provider adapters
│   │   ├── core/          # Core utilities (security, exceptions)
│   │   ├── models/        # SQLAlchemy models
│   │   ├── routing/       # Channel routing strategies
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── storage/       # Database and Redis
│   │   └── main.py        # Application entry point
│   ├── migrations/        # Alembic migrations
│   ├── tests/             # Test files
│   └── pyproject.toml     # Dependencies
├── deploy/
│   ├── docker/            # Docker Compose files
│   └── k8s/               # Kubernetes manifests
└── Makefile               # Build commands
```

## Performance Targets

- **QPS**: 100-1000 requests per second
- **Latency**: P99 < 50ms (gateway overhead only)
- **Availability**: 99.9% uptime with multi-node deployment

## Security Considerations

1. **API Keys**: Always use HTTPS in production
2. **Secret Key**: Generate a secure random key (32+ characters)
3. **Database**: Use connection pooling and SSL
4. **Redis**: Enable authentication in production
5. **Rate Limiting**: Configure appropriate limits per tenant

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## Support

For issues and feature requests, please use [GitHub Issues](https://github.com/your-org/ai-gateway/issues).

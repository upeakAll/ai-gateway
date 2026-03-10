# 部署指南

## 环境要求

### 后端

- Python 3.12+
- PostgreSQL 15+
- Redis 7+

### 前端

- Node.js 20+
- pnpm 9+

### 容器

- Docker 24+
- Docker Compose 2.20+
- Kubernetes 1.28+ (可选)

---

## Docker Compose 部署

### 目录结构

```
deploy/docker/
├── docker-compose.yaml
├── nginx.conf
├── prometheus.yml
└── grafana/
    └── dashboards/
```

### docker-compose.yaml

```yaml
version: '3.8'

services:
  # PostgreSQL 数据库
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: aigateway
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: aigateway
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aigateway"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - backend

  # Redis 缓存
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - backend

  # 后端服务
  backend:
    build:
      context: ../../backend
      dockerfile: Dockerfile
    environment:
      DATABASE_URL: postgresql+asyncpg://aigateway:${DB_PASSWORD}@postgres:5432/aigateway
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: ${SECRET_KEY}
      API_KEY_SALT: ${API_KEY_SALT}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - backend
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 1G

  # 前端服务
  frontend:
    build:
      context: ../../frontend
      dockerfile: Dockerfile
    depends_on:
      - backend
    networks:
      - backend
    ports:
      - "80:80"

  # Prometheus 监控 (可选)
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
    networks:
      - backend
    ports:
      - "9090:9090"

volumes:
  postgres_data:
  redis_data:
  prometheus_data:

networks:
  backend:
    driver: bridge
```

### 启动服务

```bash
cd deploy/docker

# 创建环境变量文件
cat > .env << EOF
DB_PASSWORD=your_secure_password
SECRET_KEY=your_secret_key_at_least_32_chars
API_KEY_SALT=your_api_key_salt
EOF

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f backend

# 健康检查
curl http://localhost/health
```

### 停止服务

```bash
docker-compose down

# 删除数据卷
docker-compose down -v
```

---

## Kubernetes 部署

### Deployment

```yaml
# deploy/k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-gateway-backend
  namespace: ai-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ai-gateway-backend
  template:
    metadata:
      labels:
        app: ai-gateway-backend
    spec:
      containers:
      - name: backend
        image: ai-gateway/backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: ai-gateway-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: ai-gateway-secrets
              key: redis-url
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: ai-gateway-secrets
              key: secret-key
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-gateway-frontend
  namespace: ai-gateway
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ai-gateway-frontend
  template:
    metadata:
      labels:
        app: ai-gateway-frontend
    spec:
      containers:
      - name: frontend
        image: ai-gateway/frontend:latest
        ports:
        - containerPort: 80
```

### Service

```yaml
# deploy/k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: ai-gateway-backend
  namespace: ai-gateway
spec:
  selector:
    app: ai-gateway-backend
  ports:
  - port: 8000
    targetPort: 8000
  type: ClusterIP
---
apiVersion: v1
kind: Service
metadata:
  name: ai-gateway-frontend
  namespace: ai-gateway
spec:
  selector:
    app: ai-gateway-frontend
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
```

### Ingress

```yaml
# deploy/k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ai-gateway
  namespace: ai-gateway
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - api.yourdomain.com
    secretName: ai-gateway-tls
  rules:
  - host: api.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: ai-gateway-frontend
            port:
              number: 80
      - path: /v1
        pathType: Prefix
        backend:
          service:
            name: ai-gateway-backend
            port:
              number: 8000
      - path: /admin
        pathType: Prefix
        backend:
          service:
            name: ai-gateway-backend
            port:
              number: 8000
      - path: /mcp
        pathType: Prefix
        backend:
          service:
            name: ai-gateway-backend
            port:
              number: 8000
      - path: /dashboard
        pathType: Prefix
        backend:
          service:
            name: ai-gateway-backend
            port:
              number: 8000
      - path: /health
        pathType: Prefix
        backend:
          service:
            name: ai-gateway-backend
            port:
              number: 8000
---
# HPA 自动伸缩
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ai-gateway-backend-hpa
  namespace: ai-gateway
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ai-gateway-backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Secrets

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ai-gateway-secrets
  namespace: ai-gateway
type: Opaque
stringData:
  database-url: postgresql+asyncpg://aigateway:password@postgres:5432/aigateway
  redis-url: redis://redis:6379/0
  secret-key: your_secret_key_at_least_32_characters_long
```

### 部署命令

```bash
# 创建命名空间
kubectl create namespace ai-gateway

# 创建 Secret
kubectl apply -f secrets.yaml

# 部署应用
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml

# 查看状态
kubectl get pods -n ai-gateway
kubectl get ingress -n ai-gateway

# 查看日志
kubectl logs -f deployment/ai-gateway-backend -n ai-gateway
```

---

## 环境变量配置

### 后端环境变量

| 变量 | 描述 | 默认值 |
|------|------|--------|
| DATABASE_URL | PostgreSQL 连接串 | - |
| REDIS_URL | Redis 连接串 | redis://localhost:6379/0 |
| SECRET_KEY | JWT 密钥 | - |
| API_KEY_SALT | API Key 加密盐 | - |
| DEBUG | 调试模式 | false |
| LOG_LEVEL | 日志级别 | INFO |
| CORS_ORIGINS | 允许的跨域来源 | * |
| RATE_LIMIT_ENABLED | 启用限流 | true |
| CIRCUIT_BREAKER_ENABLED | 启用熔断 | true |

### 示例 .env

```bash
# Database
DATABASE_URL=postgresql+asyncpg://aigateway:password@localhost:5432/aigateway

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your_secret_key_at_least_32_characters_long_for_jwt_signing
API_KEY_SALT=your_api_key_salt_for_encryption

# App
DEBUG=false
LOG_LEVEL=INFO
CORS_ORIGINS=https://yourdomain.com

# Rate Limiting
RATE_LIMIT_ENABLED=true

# Resilience
CIRCUIT_BREAKER_ENABLED=true
```

---

## 数据库迁移

### Docker Compose

```bash
# 运行迁移
docker-compose exec backend alembic upgrade head

# 创建新迁移
docker-compose exec backend alembic revision --autogenerate -m "description"
```

### Kubernetes

```bash
# 临时 Pod 运行迁移
kubectl run migrate --rm -it --image=ai-gateway/backend:latest -n ai-gateway -- \
  alembic upgrade head
```

---

## 监控

### Prometheus 指标

访问 `/metrics` 端点获取 Prometheus 格式指标：

```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="POST",path="/v1/chat/completions",status="200"} 1234

# HELP http_request_duration_seconds HTTP request latency
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.1",path="/v1/chat/completions"} 100
http_request_duration_seconds_bucket{le="0.5",path="/v1/chat/completions"} 500

# HELP ai_gateway_tokens_total Total tokens processed
# TYPE ai_gateway_tokens_total counter
ai_gateway_tokens_total{type="prompt"} 1000000
ai_gateway_tokens_total{type="completion"} 500000

# HELP ai_gateway_cost_total Total cost in USD
# TYPE ai_gateway_cost_total counter
ai_gateway_cost_total 1234.56
```

### 健康检查

```bash
# 存活探针
curl http://localhost:8000/health/live

# 就绪探针
curl http://localhost:8000/health/ready

# 完整健康检查
curl http://localhost:8000/health
```

---

## 备份与恢复

### PostgreSQL 备份

```bash
# 备份
docker-compose exec postgres pg_dump -U aigateway aigateway > backup.sql

# 恢复
cat backup.sql | docker-compose exec -T postgres psql -U aigateway aigateway
```

### Redis 备份

```bash
# 触发 RDB 快照
docker-compose exec redis redis-cli BGSAVE

# 复制快照文件
docker cp ai-gateway-redis-1:/data/dump.rdb ./redis_backup.rdb
```

---

## 故障排查

### 常见问题

**1. 数据库连接失败**
```bash
# 检查数据库状态
docker-compose exec postgres pg_isready

# 查看数据库日志
docker-compose logs postgres
```

**2. Redis 连接失败**
```bash
# 检查 Redis 状态
docker-compose exec redis redis-cli ping

# 查看 Redis 日志
docker-compose logs redis
```

**3. 后端服务无法启动**
```bash
# 查看后端日志
docker-compose logs backend

# 检查环境变量
docker-compose exec backend env | grep -E 'DATABASE|REDIS|SECRET'
```

**4. 前端无法访问后端 API**
```bash
# 检查 Nginx 配置
docker-compose exec frontend nginx -t

# 查看 Nginx 日志
docker-compose logs frontend
```

---

*最后更新: 2026-03-10*

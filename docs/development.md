# 开发指南

## 环境准备

### 系统要求

- Python 3.12+
- Node.js 20+
- PostgreSQL 15+
- Redis 7+
- Git

### 安装依赖

#### Python 包管理器 (uv)

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或使用 pip
pip install uv
```

#### Node.js 包管理器 (pnpm)

```bash
# 安装 pnpm
npm install -g pnpm
```

---

## 后端开发

### 安装依赖

```bash
cd backend

# 使用 uv 安装依赖
uv sync

# 激活虚拟环境
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows
```

### 数据库配置

```bash
# 创建 PostgreSQL 数据库
createdb aigateway

# 运行迁移
alembic upgrade head

# 创建初始管理员 (可选)
python scripts/create_admin.py
```

### 启动开发服务器

```bash
# 启动后端服务 (热重载)
uvicorn app.main:app --reload --port 8000

# 或使用 uv
uv run uvicorn app.main:app --reload --port 8000
```

### 环境变量

创建 `.env` 文件：

```bash
# .env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/aigateway
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=dev_secret_key_for_development_only
API_KEY_SALT=dev_salt_for_api_keys
DEBUG=true
LOG_LEVEL=DEBUG
```

### 代码风格

```bash
# 格式化代码
ruff format .

# 检查代码
ruff check .

# 类型检查
mypy .
```

---

## 前端开发

### 安装依赖

```bash
cd frontend

# 使用 pnpm 安装依赖
pnpm install
```

### 启动开发服务器

```bash
# 启动前端开发服务器
pnpm run dev

# 访问 http://localhost:5173
```

### 代码风格

```bash
# 格式化代码
pnpm run format

# 检查代码
pnpm run lint
```

---

## 测试

### 后端测试

```bash
cd backend

# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit_tests/

# 运行集成测试
pytest tests/integration_tests/

# 带覆盖率
pytest --cov=app --cov-report=html

# 运行特定测试
pytest tests/unit_tests/test_security.py -v

# 并行运行
pytest -n auto
```

### 测试配置

`pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

### 测试 Fixtures

```python
# tests/conftest.py
import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with AsyncSession(engine) as session:
        yield session
```

---

## API 调试

### Swagger UI

访问 http://localhost:8000/docs 查看 Swagger UI。

### cURL 示例

```bash
# 健康检查
curl http://localhost:8000/health

# Chat Completion
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}]
  }'

# 流式响应
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

---

## 数据库迁移

### 创建迁移

```bash
# 自动生成迁移
alembic revision --autogenerate -m "add_new_table"

# 手动创建迁移
alembic revision -m "add_new_column"
```

### 运行迁移

```bash
# 升级到最新
alembic upgrade head

# 升级一个版本
alembic upgrade +1

# 回滚一个版本
alembic downgrade -1

# 回滚所有
alembic downgrade base

# 查看历史
alembic history
```

---

## 添加新的 LLM 适配器

### 1. 创建适配器文件

```python
# app/adapters/domestic/new_provider.py
from app.adapters.base import BaseAdapter, ChatRequest, ChatResponse

class NewProviderAdapter(BaseAdapter):
    PROVIDER = "new_provider"
    BASE_URL = "https://api.newprovider.com/v1"

    async def chat(self, request: ChatRequest) -> ChatResponse:
        # 实现聊天逻辑
        pass

    async def stream_chat(self, request: ChatRequest):
        # 实现流式聊天
        pass

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        # 实现嵌入
        pass
```

### 2. 注册适配器

```python
# app/adapters/__init__.py
from app.adapters.domestic.new_provider import NewProviderAdapter

AdapterRegistry.register("new_provider", NewProviderAdapter)
```

### 3. 添加测试

```python
# tests/unit_tests/test_adapters.py
import pytest
from app.adapters.domestic.new_provider import NewProviderAdapter

class TestNewProviderAdapter:
    @pytest.mark.asyncio
    async def test_chat(self, mock_httpx):
        adapter = NewProviderAdapter(mock_channel)
        response = await adapter.chat(mock_request)
        assert response.choices
```

---

## 添加新的 API 端点

### 1. 创建路由文件

```python
# app/api/new_feature.py
from fastapi import APIRouter, Depends
from app.schemas.new_feature import NewFeatureRequest, NewFeatureResponse

router = APIRouter(prefix="/new-feature", tags=["New Feature"])

@router.post("", response_model=NewFeatureResponse)
async def create_feature(
    request: NewFeatureRequest,
    current_user = Depends(get_current_user)
):
    # 实现逻辑
    pass
```

### 2. 注册路由

```python
# app/main.py
from app.api.new_feature import router as new_feature_router
app.include_router(new_feature_router, prefix="/api")
```

### 3. 添加 Schema

```python
# app/schemas/new_feature.py
from pydantic import BaseModel

class NewFeatureRequest(BaseModel):
    name: str
    value: int

class NewFeatureResponse(BaseModel):
    id: str
    name: str
    value: int
```

---

## 调试技巧

### 日志配置

```python
# app/config.py
class Settings(BaseSettings):
    LOG_LEVEL: str = "DEBUG" if DEBUG else "INFO"

# 配置日志
import logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### 调试模式

```python
# 启用调试模式
DEBUG=true uvicorn app.main:app --reload
```

### VS Code 配置

`.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "app.main:app",
        "--reload",
        "--port",
        "8000"
      ],
      "jinja": true,
      "justMyCode": false
    }
  ]
}
```

---

## Git 工作流

### 分支命名

- `main` - 主分支
- `develop` - 开发分支
- `feature/xxx` - 功能分支
- `bugfix/xxx` - 修复分支
- `release/x.x.x` - 发布分支

### 提交规范

```
feat: 添加新功能
fix: 修复 bug
docs: 文档更新
style: 代码格式化
refactor: 重构
test: 测试相关
chore: 构建/工具相关
```

### PR 流程

1. 从 `develop` 创建功能分支
2. 开发并测试
3. 提交 PR
4. Code Review
5. 合并到 `develop`
6. 发布时合并到 `main`

---

## 性能优化

### 数据库优化

```python
# 使用索引
class UsageLog(Base):
    __tablename__ = "usage_logs"
    # ...
    __table_args__ = (
        Index('idx_usage_logs_created', 'created_at'),
        Index('idx_usage_logs_tenant_model', 'tenant_id', 'model_name'),
    )
```

### 缓存策略

```python
# Redis 缓存
@cache(ttl=300)
async def get_model_config(channel_id: str, model: str):
    return await db.get(ModelConfig, channel_id=channel_id, model_name=model)
```

### 异步优化

```python
# 并行请求
async def get_all_data():
    results = await asyncio.gather(
        get_tenants(),
        get_channels(),
        get_usage_stats()
    )
    return results
```

---

## 常见问题

### Q: 数据库迁移失败

```bash
# 检查当前版本
alembic current

# 标记为最新
alembic stamp head
```

### Q: 端口被占用

```bash
# 查找占用进程
lsof -i :8000

# 终止进程
kill -9 <PID>
```

### Q: 依赖冲突

```bash
# 重新安装依赖
rm -rf .venv
uv sync
```

---

*最后更新: 2026-03-10*

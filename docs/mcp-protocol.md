# MCP 协议实现

## 概述

AI Gateway 完整实现了 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 2025-03-26 版本规范，允许 AI 模型通过标准化接口访问外部工具和资源。

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     AI Gateway                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    MCP Server                            ││
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌─────────┐ ││
│  │  │ Transport │ │  Session  │ │   Tools   │ │  Auth   │ ││
│  │  │  (SSE)    │ │  Manager  │ │  Registry │ │  (RBAC) │ ││
│  │  └───────────┘ └───────────┘ └───────────┘ └─────────┘ ││
│  └─────────────────────────────────────────────────────────┘│
│                          │                                   │
│  ┌───────────────────────┴───────────────────────────────┐  │
│  │                    MCP Resources                       │  │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐           │  │
│  │  │  Tools    │ │ Resources │ │  Prompts  │           │  │
│  │  │  (API调用) │ │ (数据源)   │ │ (模板)    │           │  │
│  │  └───────────┘ └───────────┘ └───────────┘           │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          ▲
                          │ SSE
                          │
              ┌───────────────────────┐
              │    MCP Client         │
              │   (AI Application)    │
              └───────────────────────┘
```

---

## 传输层

### SSE (Server-Sent Events)

MCP 使用 SSE 作为主要传输方式，支持双向通信。

**端点**: `GET /mcp/{server_name}/sse`

**连接流程**:

```
Client                              Server
   │                                   │
   │──── GET /mcp/my-server/sse ──────→│
   │←─── 200 OK (SSE stream) ──────────│
   │                                   │
   │←─── event: endpoint ─────────────│  ← 发送消息端点
   │     data: /mcp/message?session=xxx│
   │                                   │
   │──── POST /mcp/message ───────────→│  ← 发送 JSON-RPC
   │     Body: {"jsonrpc":"2.0",...}   │
   │←─── event: message ───────────────│  ← 接收响应
   │     data: {"jsonrpc":"2.0",...}   │
   │                                   │
```

### 心跳机制

```python
# 每30秒发送心跳，防止连接超时
async def send_heartbeat():
    while True:
        await asyncio.sleep(30)
        yield "event: ping\ndata: {}\n\n"
```

---

## JSON-RPC 协议

MCP 使用 JSON-RPC 2.0 进行通信。

### 请求格式

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_weather",
    "arguments": {
      "city": "Beijing"
    }
  }
}
```

### 响应格式

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Beijing: 25°C, Sunny"
      }
    ]
  }
}
```

### 错误响应

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "Invalid params",
    "data": {"field": "city"}
  }
}
```

---

## MCP 方法

### 初始化

```json
// Request
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {}
    },
    "clientInfo": {
      "name": "my-client",
      "version": "1.0.0"
    }
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {},
      "resources": {},
      "prompts": {}
    },
    "serverInfo": {
      "name": "ai-gateway-mcp",
      "version": "1.0.0"
    }
  }
}
```

### 列出工具

```json
// Request
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list"
}

// Response
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "get_weather",
        "description": "Get weather information",
        "inputSchema": {
          "type": "object",
          "properties": {
            "city": {"type": "string"}
          },
          "required": ["city"]
        }
      }
    ]
  }
}
```

### 调用工具

```json
// Request
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_weather",
    "arguments": {
      "city": "Beijing"
    }
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Beijing: 25°C, Sunny"
      }
    ]
  }
}
```

### 列出资源

```json
// Request
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "resources/list"
}

// Response
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "resources": [
      {
        "uri": "file:///data/config.json",
        "name": "Configuration",
        "mimeType": "application/json"
      }
    ]
  }
}
```

### 读取资源

```json
// Request
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "resources/read",
  "params": {
    "uri": "file:///data/config.json"
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "contents": [
      {
        "uri": "file:///data/config.json",
        "mimeType": "application/json",
        "text": "{\"key\": \"value\"}"
      }
    ]
  }
}
```

### 列出提示词

```json
// Request
{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "prompts/list"
}

// Response
{
  "jsonrpc": "2.0",
  "id": 6,
  "result": {
    "prompts": [
      {
        "name": "code_review",
        "description": "Review code for issues",
        "arguments": [
          {
            "name": "code",
            "description": "Code to review",
            "required": true
          }
        ]
      }
    ]
  }
}
```

### 获取提示词

```json
// Request
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "prompts/get",
  "params": {
    "name": "code_review",
    "arguments": {
      "code": "def add(a, b): return a + b"
    }
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": 7,
  "result": {
    "description": "Review this code",
    "messages": [
      {
        "role": "user",
        "content": {
          "type": "text",
          "text": "Please review the following code:\n\ndef add(a, b): return a + b"
        }
      }
    ]
  }
}
```

---

## 工具注册

### 手动注册工具

```python
from app.mcp.tools.registry import ToolRegistry

registry = ToolRegistry()

@registry.register(
    name="get_weather",
    description="Get weather information for a city",
    input_schema={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name"
            }
        },
        "required": ["city"]
    },
    required_permission="weather:read"
)
async def get_weather(city: str) -> str:
    # 实现天气查询逻辑
    return f"{city}: 25°C, Sunny"
```

### 从 OpenAPI 自动生成

```python
from app.mcp.tools.openapi_gen import OpenAPIGenerator

generator = OpenAPIGenerator()

# 从 OpenAPI 规范生成工具
tools = await generator.generate_from_url(
    "https://api.example.com/openapi.json"
)

for tool in tools:
    registry.register_tool(tool)
```

---

## 工具执行器

### HTTP 执行器

```python
class HTTPToolExecutor:
    """HTTP 工具执行器"""

    async def execute(self, tool: MCPTool, arguments: dict) -> dict:
        config = tool.executor_config
        url = config["url_template"].format(**arguments)
        method = config.get("method", "GET")

        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, params=arguments)
            else:
                response = await client.post(url, json=arguments)

            return {
                "content": [{
                    "type": "text",
                    "text": response.text
                }]
            }
```

### Python 函数执行器

```python
class PythonToolExecutor:
    """Python 函数执行器"""

    async def execute(self, tool: MCPTool, arguments: dict) -> dict:
        # 获取注册的函数
        func = self.registry.get_function(tool.name)

        # 执行函数
        result = await func(**arguments)

        return {
            "content": [{
                "type": "text",
                "text": str(result)
            }]
        }
```

---

## RBAC 权限控制

### 权限模型

```python
class MCPRBAC:
    """MCP RBAC 控制"""

    async def check_tool_access(
        self,
        user_roles: List[str],
        tool: MCPTool
    ) -> bool:
        """检查用户是否有权限调用工具"""

        # 检查角色是否在允许列表中
        if not set(user_roles) & set(tool.allowed_roles):
            return False

        # 检查特定权限
        if tool.required_permission:
            user_permissions = await self.get_permissions(user_roles)
            if tool.required_permission not in user_permissions:
                return False

        return True
```

### 角色配置

```yaml
roles:
  admin:
    permissions:
      - "*"
    mcp_tools:
      - "*"  # 所有工具

  developer:
    permissions:
      - "weather:read"
      - "calendar:read"
    mcp_tools:
      - "get_weather"
      - "get_calendar"

  viewer:
    permissions: []
    mcp_tools: []
```

---

## 会话管理

```python
class MCPSessionManager:
    """MCP 会话管理"""

    def __init__(self, redis: Redis):
        self.redis = redis
        self.session_ttl = 3600  # 1小时

    async def create_session(self, server_name: str) -> str:
        """创建新会话"""
        session_id = str(uuid.uuid4())
        session_data = {
            "server_name": server_name,
            "created_at": time.time(),
            "message_queue": []
        }
        await self.redis.setex(
            f"mcp:session:{session_id}",
            self.session_ttl,
            json.dumps(session_data)
        )
        return session_id

    async def get_session(self, session_id: str) -> Optional[dict]:
        """获取会话"""
        data = await self.redis.get(f"mcp:session:{session_id}")
        return json.loads(data) if data else None

    async def close_session(self, session_id: str):
        """关闭会话"""
        await self.redis.delete(f"mcp:session:{session_id}")
```

---

## 使用示例

### Python 客户端

```python
import httpx

class MCPClient:
    def __init__(self, base_url: str, server_name: str):
        self.base_url = base_url
        self.server_name = server_name
        self.session_endpoint = None
        self.request_id = 0

    async def connect(self):
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET", f"{self.base_url}/mcp/{self.server_name}/sse"
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        self.session_endpoint = line[5:].strip()
                        break

    async def call_tool(self, name: str, arguments: dict) -> dict:
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments}
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.session_endpoint,
                json=payload
            )
            return response.json()

# 使用
client = MCPClient("http://localhost:8000", "my-server")
await client.connect()
result = await client.call_tool("get_weather", {"city": "Beijing"})
print(result)
```

---

*最后更新: 2026-03-10*

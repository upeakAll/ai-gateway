# 适配器设计

## 架构概览

适配器层负责统一封装不同 LLM 提供商的 API 差异，提供一致的调用接口。

```
                    ┌─────────────────────┐
                    │   Chat Endpoint     │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  AdapterRegistry    │
                    │  (根据provider选择)  │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ OpenAIAdapter │    │AnthropicAdptr │    │ Other Adapters│
└───────────────┘    └───────────────┘    └───────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  OpenAI API   │    │Anthropic API  │    │ Provider APIs │
└───────────────┘    └───────────────┘    └───────────────┘
```

---

## BaseAdapter 抽象基类

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from decimal import Decimal

class BaseAdapter(ABC):
    """LLM 适配器基类"""

    def __init__(self, channel: Channel):
        self.channel = channel
        self.http_client = httpx.AsyncClient()

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        同步聊天补全

        Args:
            request: 统一格式的聊天请求

        Returns:
            ChatResponse: 统一格式的响应
        """
        pass

    @abstractmethod
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatDelta]:
        """
        流式聊天补全

        Args:
            request: 统一格式的聊天请求

        Yields:
            ChatDelta: 流式响应增量
        """
        pass

    @abstractmethod
    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        """
        文本嵌入

        Args:
            request: 统一格式的嵌入请求

        Returns:
            EmbedResponse: 嵌入向量响应
        """
        pass

    async def close(self):
        """关闭连接"""
        await self.http_client.aclose()
```

---

## 统一请求/响应格式

### ChatRequest

```python
@dataclass
class ChatRequest:
    model: str                          # 模型名称
    messages: List[Message]             # 消息列表
    temperature: Optional[float] = 0.7  # 温度
    max_tokens: Optional[int] = None    # 最大token
    top_p: Optional[float] = None       # Top-p采样
    stop: Optional[List[str]] = None    # 停止词
    stream: bool = False                # 是否流式
    tools: Optional[List[Tool]] = None  # 工具定义
    metadata: Optional[dict] = None     # 扩展元数据

@dataclass
class Message:
    role: str              # system, user, assistant, tool
    content: str           # 文本内容
    name: Optional[str]    # 名称(用于tool消息)
    tool_calls: Optional[List[ToolCall]]  # 工具调用
    tool_call_id: Optional[str]           # 工具调用ID
```

### ChatResponse

```python
@dataclass
class ChatResponse:
    id: str                           # 响应ID
    model: str                        # 模型名称
    choices: List[Choice]             # 选择列表
    usage: Usage                      # Token使用量
    created: int                      # 创建时间戳

@dataclass
class Choice:
    index: int
    message: Message
    finish_reason: str                # stop, length, tool_calls

@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
```

### ChatDelta (流式)

```python
@dataclass
class ChatDelta:
    id: str
    model: str
    choices: List[DeltaChoice]

@dataclass
class DeltaChoice:
    index: int
    delta: DeltaMessage
    finish_reason: Optional[str]

@dataclass
class DeltaMessage:
    role: Optional[str]
    content: Optional[str]
    tool_calls: Optional[List[ToolCallDelta]]
```

---

## 适配器实现

### OpenAI Adapter

```python
class OpenAIAdapter(BaseAdapter):
    """OpenAI API 适配器"""

    PROVIDER = "openai"
    BASE_URL = "https://api.openai.com/v1"

    async def chat(self, request: ChatRequest) -> ChatResponse:
        url = f"{self.channel.api_base or self.BASE_URL}/chat/completions"

        # 转换为 OpenAI 格式
        openai_request = self._convert_request(request)

        response = await self.http_client.post(
            url,
            json=openai_request,
            headers=self._get_headers(),
            timeout=60.0
        )
        response.raise_for_status()

        # 转换响应格式
        return self._convert_response(response.json())

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatDelta]:
        url = f"{self.channel.api_base or self.BASE_URL}/chat/completions"

        openai_request = self._convert_request(request)
        openai_request["stream"] = True

        async with self.http_client.stream(
            "POST", url, json=openai_request,
            headers=self._get_headers(), timeout=60.0
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    yield self._convert_stream_delta(json.loads(data))

    def _convert_request(self, request: ChatRequest) -> dict:
        """转换为 OpenAI 请求格式"""
        return {
            "model": request.model,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stop": request.stop,
        }

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.channel.api_key}",
            "Content-Type": "application/json",
        }
```

### Anthropic Adapter

```python
class AnthropicAdapter(BaseAdapter):
    """Anthropic API 适配器，支持协议转换"""

    PROVIDER = "anthropic"
    BASE_URL = "https://api.anthropic.com/v1"

    async def chat(self, request: ChatRequest) -> ChatResponse:
        url = f"{self.channel.api_base or self.BASE_URL}/messages"

        # OpenAI 格式转 Anthropic 格式
        anthropic_request = self._convert_to_anthropic(request)

        response = await self.http_client.post(
            url,
            json=anthropic_request,
            headers=self._get_headers(),
            timeout=60.0
        )
        response.raise_for_status()

        # Anthropic 格式转回 OpenAI 格式
        return self._convert_to_openai(response.json())

    def _convert_to_anthropic(self, request: ChatRequest) -> dict:
        """OpenAI 格式转 Anthropic 格式"""
        # 分离 system 消息
        system = None
        messages = []

        for msg in request.messages:
            if msg.role == "system":
                system = msg.content
            else:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

        return {
            "model": request.model,
            "max_tokens": request.max_tokens or 4096,
            "system": system,
            "messages": messages,
        }

    def _convert_to_openai(self, response: dict) -> ChatResponse:
        """Anthropic 响应转 OpenAI 格式"""
        content = ""
        for block in response.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        return ChatResponse(
            id=response["id"],
            model=response["model"],
            choices=[Choice(
                index=0,
                message=Message(role="assistant", content=content),
                finish_reason="stop"
            )],
            usage=Usage(
                prompt_tokens=response["usage"]["input_tokens"],
                completion_tokens=response["usage"]["output_tokens"],
                total_tokens=response["usage"]["input_tokens"] + response["usage"]["output_tokens"]
            ),
            created=int(time.time())
        )

    def _get_headers(self) -> dict:
        return {
            "x-api-key": self.channel.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
```

### 国内厂商适配器示例 (DeepSeek)

```python
class DeepSeekAdapter(BaseAdapter):
    """DeepSeek API 适配器"""

    PROVIDER = "deepseek"
    BASE_URL = "https://api.deepseek.com/v1"

    # DeepSeek API 完全兼容 OpenAI 格式
    async def chat(self, request: ChatRequest) -> ChatResponse:
        # 直接使用 OpenAI 格式
        return await self._openai_compatible_chat(request)

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        # DeepSeek 暂不支持 embedding
        raise NotImplementedError("DeepSeek does not support embeddings")
```

---

## AdapterRegistry

适配器注册表负责管理和查找适配器。

```python
class AdapterRegistry:
    """适配器注册表"""

    _adapters: Dict[str, Type[BaseAdapter]] = {}

    @classmethod
    def register(cls, provider: str, adapter_class: Type[BaseAdapter]):
        """注册适配器"""
        cls._adapters[provider] = adapter_class

    @classmethod
    def get(cls, provider: str) -> Type[BaseAdapter]:
        """获取适配器类"""
        if provider not in cls._adapters:
            raise ValueError(f"Unknown provider: {provider}")
        return cls._adapters[provider]

    @classmethod
    def create(cls, channel: Channel) -> BaseAdapter:
        """创建适配器实例"""
        adapter_class = cls.get(channel.provider)
        return adapter_class(channel)

    @classmethod
    def list_providers(cls) -> List[str]:
        """列出所有支持的提供商"""
        return list(cls._adapters.keys())

# 自动注册所有适配器
AdapterRegistry.register("openai", OpenAIAdapter)
AdapterRegistry.register("anthropic", AnthropicAdapter)
AdapterRegistry.register("azure", AzureOpenAIAdapter)
AdapterRegistry.register("bedrock", BedrockAdapter)
AdapterRegistry.register("deepseek", DeepSeekAdapter)
# ... 更多适配器
```

---

## 支持的提供商

| 提供商 | Provider ID | 特性支持 |
|--------|-------------|----------|
| OpenAI | `openai` | Chat, Streaming, Embeddings |
| Anthropic | `anthropic` | Chat, Streaming (协议转换) |
| Azure OpenAI | `azure` | Chat, Streaming, Embeddings |
| AWS Bedrock | `bedrock` | Chat, Streaming (多模型) |
| 阿里云通义 | `aliyun` | Chat, Streaming, Embeddings |
| 百度文心 | `baidu` | Chat, Streaming (协议转换) |
| 智谱AI | `zhipu` | Chat, Streaming, Embeddings |
| DeepSeek | `deepseek` | Chat, Streaming |
| MiniMax | `minimax` | Chat, Streaming |
| Moonshot | `moonshot` | Chat, Streaming |
| 百川 | `baichuan` | Chat, Streaming |
| Ollama | `ollama` | Chat, Streaming, Embeddings |
| vLLM | `vllm` | Chat, Streaming |

---

## 协议转换

### OpenAI → Anthropic

```
OpenAI                           Anthropic
─────────────────────────────────────────────
{
  "model": "gpt-4",              {
  "messages": [                    "model": "claude-3",
    {"role": "system",             "system": "You are...",
     "content": "You are..."},     "max_tokens": 1024,
    {"role": "user",               "messages": [
     "content": "Hello"}             {"role": "user",
  ],                                  "content": "Hello"}
  "max_tokens": 1024              ]
}                                }
```

### 响应转换

```
Anthropic                        OpenAI
─────────────────────────────────────────────
{                                {
  "id": "msg_xxx",                 "id": "chatcmpl-xxx",
  "content": [                     "choices": [{
    {"type": "text",                 "message": {
     "text": "Hello"}                  "role": "assistant",
  ],                                   "content": "Hello"
  "usage": {                         },
    "input_tokens": 10,              "finish_reason": "stop"
    "output_tokens": 20            }],
  }                                "usage": {
}                                    "prompt_tokens": 10,
                                     "completion_tokens": 20,
                                     "total_tokens": 30
                                   }
                                 }
```

---

## 错误处理

适配器统一处理上游错误：

```python
class AdapterError(Exception):
    """适配器错误基类"""
    def __init__(self, message: str, provider: str, status_code: int = None):
        self.message = message
        self.provider = provider
        self.status_code = status_code
        super().__init__(message)

class RateLimitError(AdapterError):
    """限流错误"""
    def __init__(self, provider: str, retry_after: int = None):
        self.retry_after = retry_after
        super().__init__(f"Rate limited by {provider}", provider, 429)

class AuthenticationError(AdapterError):
    """认证错误"""
    def __init__(self, provider: str):
        super().__init__(f"Authentication failed for {provider}", provider, 401)

class ModelNotFoundError(AdapterError):
    """模型不存在"""
    def __init__(self, model: str, provider: str):
        super().__init__(f"Model {model} not found", provider, 404)
```

---

*最后更新: 2026-03-10*

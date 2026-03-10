"""Baidu (文心一言/ERNIE) adapter implementation."""

import json
import time
import uuid
from typing import Any, AsyncIterator

import httpx
import structlog

from app.adapters.base import (
    BaseAdapter,
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Embedding,
    EmbeddingRequest,
    EmbeddingResponse,
    MessageRole,
    StreamChunk,
    Usage,
)
from app.adapters.registry import AdapterRegistry, register_adapter
from app.config import settings
from app.core.exceptions import AdapterError, AdapterRateLimitError, AdapterTimeoutError
from app.models.channel import Provider

logger = structlog.get_logger()

# Baidu ERNIE models
BAIDU_MODELS = [
    "ernie-4.0-8k",
    "ernie-4.0",
    "ernie-3.5-8k",
    "ernie-3.5",
    "ernie-speed-8k",
    "ernie-speed-128k",
    "ernie-lite-8k",
    "ernie-tiny-8k",
    "ernie-char-8k",
    "embedding-v1",
]


@register_adapter(Provider.BAIDU)
class BaiduAdapter(BaseAdapter):
    """Baidu Wenxin Yiyan (文心一言/ERNIE) adapter."""

    provider = "baidu"

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, api_base, **kwargs)
        # api_key should be in format "access_key:secret_key"
        if ":" not in api_key:
            raise AdapterError(
                "Baidu API key must be in format 'access_key:secret_key'",
                provider=self.provider,
            )

        self.access_key, self.secret_key = api_key.split(":", 1)
        self.base_url = api_base or "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=settings.request_timeout_seconds,
                write=30.0,
                pool=10.0,
            ),
        )
        self._access_token: str | None = None
        self._token_expires: float = 0

    async def _get_access_token(self) -> str:
        """Get or refresh access token."""
        if self._access_token and time.time() < self._token_expires:
            return self._access_token

        response = await self._client.get(
            "https://aip.baidubce.com/oauth/2.0/token",
            params={
                "grant_type": "client_credentials",
                "client_id": self.access_key,
                "client_secret": self.secret_key,
            },
        )

        result = response.json()
        self._access_token = result.get("access_token")
        self._token_expires = time.time() + result.get("expires_in", 86400) - 60

        return self._access_token

    def _model_to_endpoint(self, model: str) -> str:
        """Convert model name to API endpoint."""
        model_mapping = {
            "ernie-4.0-8k": "completions_pro",
            "ernie-4.0": "completions_pro",
            "ernie-3.5-8k": "completions",
            "ernie-3.5": "completions",
            "ernie-speed-8k": "ernie_speed",
            "ernie-speed-128k": "ernie_speed",
            "ernie-lite-8k": "ernie_lite",
            "ernie-tiny-8k": "ernie_tiny",
            "ernie-char-8k": "ernie_char",
        }
        return model_mapping.get(model, "completions")

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Execute chat completion using Baidu ERNIE."""
        start_time = time.time()

        try:
            access_token = await self._get_access_token()
            endpoint = self._model_to_endpoint(request.model)

            # Convert messages to Baidu format
            messages = []
            for msg in request.messages:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                messages.append({"role": msg.role.value, "content": content})

            body = {
                "messages": messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
            }

            if request.max_tokens:
                body["max_output_tokens"] = request.max_tokens
            if request.stop:
                body["stop"] = request.stop

            response = await self._client.post(
                f"{self.base_url}/chat/{endpoint}?access_token={access_token}",
                json=body,
            )

            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 429:
                raise AdapterRateLimitError(provider=self.provider)

            result = response.json()

            if "error_code" in result:
                raise AdapterError(
                    f"Baidu API error: {result.get('error_msg', 'Unknown error')}",
                    provider=self.provider,
                )

            return self._parse_response(result, request.model, latency_ms)

        except httpx.TimeoutException as e:
            logger.error("baidu_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except Exception as e:
            logger.error("baidu_error", model=request.model, error=str(e))
            raise AdapterError(f"Baidu API error: {str(e)}", provider=self.provider) from e

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Execute streaming chat completion."""
        request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        try:
            access_token = await self._get_access_token()
            endpoint = self._model_to_endpoint(request.model)

            messages = []
            for msg in request.messages:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                messages.append({"role": msg.role.value, "content": content})

            body = {
                "messages": messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "stream": True,
            }

            async with self._client.stream(
                "POST",
                f"{self.base_url}/chat/{endpoint}?access_token={access_token}",
                json=body,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or line == "":
                        continue

                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data:
                            try:
                                chunk = json.loads(data)
                                yield self._parse_stream_chunk(chunk, request_id, request.model)
                            except json.JSONDecodeError:
                                continue

            yield StreamChunk(
                id=request_id,
                model=request.model,
                delta={},
                finish_reason="stop",
                provider=self.provider,
            )

        except Exception as e:
            logger.error("baidu_stream_error", model=request.model, error=str(e))
            raise AdapterError(f"Baidu streaming error: {str(e)}", provider=self.provider) from e

    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Execute embedding request."""
        try:
            access_token = await self._get_access_token()
            texts = request.input if isinstance(request.input, list) else [request.input]

            embeddings = []
            total_tokens = 0

            for idx, text in enumerate(texts):
                response = await self._client.post(
                    f"{self.base_url}/embeddings/embedding-v1?access_token={access_token}",
                    json={"input": [text]},
                )

                result = response.json()

                if "error_code" in result:
                    raise AdapterError(
                        f"Baidu embedding error: {result.get('error_msg')}",
                        provider=self.provider,
                    )

                data = result.get("data", [])
                if data:
                    embeddings.append(Embedding(
                        index=idx,
                        embedding=data[0].get("embedding", []),
                    ))

                usage = result.get("usage", {})
                total_tokens += usage.get("total_tokens", 0)

            return EmbeddingResponse(
                id=f"emb-{int(time.time())}",
                model=request.model,
                data=embeddings,
                usage=Usage(
                    prompt_tokens=total_tokens,
                    completion_tokens=0,
                    total_tokens=total_tokens,
                ),
                provider=self.provider,
            )

        except Exception as e:
            logger.error("baidu_embedding_error", model=request.model, error=str(e))
            raise AdapterError(f"Baidu embedding error: {str(e)}", provider=self.provider) from e

    async def list_models(self) -> list[str]:
        """List available models."""
        return BAIDU_MODELS

    def supports_model(self, model: str) -> bool:
        """Check if model is supported."""
        return model.startswith("ernie-") or model.startswith("embedding-")

    def _parse_response(
        self, result: dict[str, Any], model: str, latency_ms: float
    ) -> ChatCompletionResponse:
        """Parse Baidu response."""
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=result.get("result", ""),
        )

        usage = Usage(
            prompt_tokens=result.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=result.get("usage", {}).get("completion_tokens", 0),
            total_tokens=result.get("usage", {}).get("total_tokens", 0),
        )

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            model=model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=message,
                    finish_reason="stop" if result.get("is_end") else None,
                )
            ],
            usage=usage,
            created=int(time.time()),
            provider=self.provider,
            latency_ms=latency_ms,
        )

    def _parse_stream_chunk(
        self, chunk: dict[str, Any], request_id: str, model: str
    ) -> StreamChunk:
        """Parse streaming chunk."""
        return StreamChunk(
            id=request_id,
            model=model,
            delta={"content": chunk.get("result", "")},
            finish_reason="stop" if chunk.get("is_end") else None,
            provider=self.provider,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


# Register model prefixes
AdapterRegistry.register_model_prefix("ernie-", Provider.BAIDU)

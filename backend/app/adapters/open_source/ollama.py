"""Ollama adapter for local models."""

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
from app.core.exceptions import AdapterError, AdapterTimeoutError
from app.models.channel import Provider

logger = structlog.get_logger()


@register_adapter(Provider.OLLAMA)
class OllamaAdapter(BaseAdapter):
    """Ollama adapter for local model inference."""

    provider = "ollama"

    def __init__(
        self,
        api_key: str = "",  # Ollama doesn't require API key
        api_base: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, api_base, **kwargs)

        self.base_url = api_base or "http://localhost:11434"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=settings.request_timeout_seconds,
                write=30.0,
                pool=10.0,
            ),
        )

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Execute chat completion using Ollama."""
        start_time = time.time()

        try:
            # Convert messages to Ollama format
            messages = []
            for msg in request.messages:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                messages.append({"role": msg.role.value, "content": content})

            body = {
                "model": request.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                },
            }

            if request.max_tokens:
                body["options"]["num_predict"] = request.max_tokens
            if request.stop:
                body["options"]["stop"] = request.stop

            response = await self._client.post(
                f"{self.base_url}/api/chat",
                json=body,
            )

            latency_ms = (time.time() - start_time) * 1000
            response.raise_for_status()
            result = response.json()

            return self._parse_response(result, request.model, latency_ms)

        except httpx.TimeoutException as e:
            logger.error("ollama_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except Exception as e:
            logger.error("ollama_error", model=request.model, error=str(e))
            raise AdapterError(f"Ollama API error: {str(e)}", provider=self.provider) from e

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Execute streaming chat completion."""
        request_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        try:
            messages = []
            for msg in request.messages:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                messages.append({"role": msg.role.value, "content": content})

            body = {
                "model": request.model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                },
            }

            async with self._client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=body,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    try:
                        chunk = json.loads(line)
                        yield self._parse_stream_chunk(chunk, request_id, request.model)
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error("ollama_stream_error", model=request.model, error=str(e))
            raise AdapterError(f"Ollama streaming error: {str(e)}", provider=self.provider) from e

    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Execute embedding request."""
        try:
            texts = request.input if isinstance(request.input, list) else [request.input]

            embeddings = []
            total_tokens = 0

            for idx, text in enumerate(texts):
                response = await self._client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": request.model,
                        "prompt": text,
                    },
                )

                response.raise_for_status()
                result = response.json()

                embeddings.append(Embedding(
                    index=idx,
                    embedding=result.get("embedding", []),
                ))

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
            logger.error("ollama_embedding_error", model=request.model, error=str(e))
            raise AdapterError(f"Ollama embedding error: {str(e)}", provider=self.provider) from e

    async def list_models(self) -> list[str]:
        """List available Ollama models."""
        try:
            response = await self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            result = response.json()

            return [model["name"] for model in result.get("models", [])]
        except Exception:
            return ["llama3", "llama3.1", "mistral", "codellama", "phi3"]

    def supports_model(self, model: str) -> bool:
        """Ollama supports any model name."""
        return True

    def _parse_response(
        self, result: dict[str, Any], model: str, latency_ms: float
    ) -> ChatCompletionResponse:
        """Parse Ollama response."""
        message_data = result.get("message", {})
        message = ChatMessage(
            role=MessageRole(message_data.get("role", "assistant")),
            content=message_data.get("content", ""),
        )

        eval_count = result.get("eval_count", 0)
        prompt_eval_count = result.get("prompt_eval_count", 0)

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            model=model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=message,
                    finish_reason="stop" if result.get("done") else None,
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_eval_count,
                completion_tokens=eval_count,
                total_tokens=prompt_eval_count + eval_count,
            ),
            created=int(time.time()),
            provider=self.provider,
            latency_ms=latency_ms,
        )

    def _parse_stream_chunk(
        self, chunk: dict[str, Any], request_id: str, model: str
    ) -> StreamChunk:
        """Parse streaming chunk."""
        message = chunk.get("message", {})
        content = message.get("content", "")

        return StreamChunk(
            id=request_id,
            model=model,
            delta={"content": content} if content else {},
            finish_reason="stop" if chunk.get("done") else None,
            provider=self.provider,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


# Register Ollama
AdapterRegistry.register_model_prefix("llama", Provider.OLLAMA)
AdapterRegistry.register_model_prefix("mistral", Provider.OLLAMA)
AdapterRegistry.register_model_prefix("codellama", Provider.OLLAMA)
AdapterRegistry.register_model_prefix("phi", Provider.OLLAMA)

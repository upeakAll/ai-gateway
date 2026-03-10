"""AWS Bedrock adapter implementation."""

import json
import time
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
    ToolDefinition,
    Usage,
)
from app.adapters.registry import AdapterRegistry, register_adapter
from app.config import settings
from app.core.exceptions import AdapterError, AdapterRateLimitError, AdapterTimeoutError
from app.models.channel import Provider

logger = structlog.get_logger()

# Bedrock model patterns
BEDROCK_MODELS = {
    # Claude models
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "anthropic.claude-3-5-sonnet-20240620-v1:0",
    "anthropic.claude-3-5-haiku-20241022-v1:0",
    "anthropic.claude-3-opus-20240229-v1:0",
    "anthropic.claude-3-sonnet-20240229-v1:0",
    "anthropic.claude-3-haiku-20240307-v1:0",
    "anthropic.claude-v2:1",
    "anthropic.claude-v2",
    # Amazon models
    "amazon.titan-text-lite-v1",
    "amazon.titan-text-express-v1",
    "amazon.titan-embed-text-v1",
    "amazon.titan-embed-text-v2:0",
    # Cohere models
    "cohere.command-text-v14",
    "cohere.command-light-text-v14",
    "cohere.embed-english-v3",
    "cohere.embed-multilingual-v3",
    # AI21 models
    "ai21.j2-mid-v1",
    "ai21.j2-ultra-v1",
    # Meta models
    "meta.llama3-8b-instruct-v1:0",
    "meta.llama3-70b-instruct-v1:0",
    "meta.llama3-1-8b-instruct-v1:0",
    "meta.llama3-1-70b-instruct-v1:0",
    "meta.llama3-1-405b-instruct-v1:0",
    # Mistral models
    "mistral.mistral-7b-instruct-v0:2",
    "mistral.mixtral-8x7b-instruct-v0:1",
    "mistral.mistral-large-2402-v1:0",
}


@register_adapter(Provider.AWS_BEDROCK)
class BedrockAdapter(BaseAdapter):
    """AWS Bedrock adapter for foundation models.

    Supports Claude, Titan, Cohere, Llama, and Mistral models through Bedrock.
    """

    provider = "aws_bedrock"

    def __init__(
        self,
        api_key: str,  # Not used for Bedrock, kept for interface consistency
        api_base: str | None = None,
        api_version: str | None = None,
        aws_region: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, api_base, api_version, **kwargs)

        self.aws_region = aws_region or "us-east-1"
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key

        if not aws_access_key_id or not aws_secret_access_key:
            raise AdapterError(
                "Bedrock requires aws_access_key_id and aws_secret_access_key",
                provider=self.provider,
            )

        self.base_url = api_base or f"https://bedrock-runtime.{self.aws_region}.amazonaws.com"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=settings.request_timeout_seconds,
                write=30.0,
                pool=10.0,
            ),
        )

    def _sign_request(self, method: str, path: str, body: bytes = b"") -> dict[str, str]:
        """Create AWS Signature V4 headers."""
        import hashlib
        import hmac
        from datetime import UTC, datetime

        # Create timestamps
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        # Create canonical request
        service = "bedrock"
        algorithm = "AWS4-HMAC-SHA256"

        # Hash the body
        body_hash = hashlib.sha256(body).hexdigest()

        # Create canonical headers
        canonical_headers = f"host:bedrock-runtime.{self.aws_region}.amazonaws.com\nx-amz-date:{amz_date}\n"
        signed_headers = "host;x-amz-date"

        # Create canonical request
        canonical_request = f"{method}\n{path}\n\n{canonical_headers}\n{signed_headers}\n{body_hash}"

        # Create string to sign
        credential_scope = f"{date_stamp}/{self.aws_region}/{service}/aws4_request"
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"

        # Calculate signature
        def sign(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()

        k_date = sign(("AWS4" + self.aws_secret_access_key).encode(), date_stamp)
        k_region = sign(k_date, self.aws_region)
        k_service = sign(k_region, service)
        k_signing = sign(k_service, "aws4_request")
        signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

        # Create authorization header
        authorization = f"{algorithm} Credential={self.aws_access_key_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

        return {
            "X-Amz-Date": amz_date,
            "Authorization": authorization,
            "Content-Type": "application/json",
        }

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Execute a chat completion request using Bedrock."""
        start_time = time.time()

        try:
            model_id = request.model
            provider_family = model_id.split(".")[0] if "." in model_id else "anthropic"

            # Build request body based on provider
            if provider_family == "anthropic":
                body = self._build_claude_request(request)
                path = f"/model/{model_id}/invoke"
            elif provider_family in ("amazon", "ai21"):
                body = self._build_titan_request(request)
                path = f"/model/{model_id}/invoke"
            elif provider_family == "cohere":
                body = self._build_cohere_request(request)
                path = f"/model/{model_id}/invoke"
            elif provider_family == "meta":
                body = self._build_llama_request(request)
                path = f"/model/{model_id}/invoke"
            elif provider_family == "mistral":
                body = self._build_mistral_request(request)
                path = f"/model/{model_id}/invoke"
            else:
                # Default to Claude-style request
                body = self._build_claude_request(request)
                path = f"/model/{model_id}/invoke"

            body_bytes = json.dumps(body).encode()

            # Sign and send request
            headers = self._sign_request("POST", path, body_bytes)
            response = await self._client.post(
                f"{self.base_url}{path}",
                content=body_bytes,
                headers=headers,
            )

            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 429:
                raise AdapterRateLimitError(provider=self.provider)

            response.raise_for_status()
            response_body = response.json()

            # Parse response based on provider
            if provider_family == "anthropic":
                return self._parse_claude_response(response_body, model_id, latency_ms)
            else:
                return self._parse_generic_response(response_body, model_id, latency_ms)

        except httpx.TimeoutException as e:
            logger.error("bedrock_timeout", model=request.model, error=str(e))
            raise AdapterTimeoutError(provider=self.provider) from e

        except httpx.HTTPStatusError as e:
            logger.error("bedrock_http_error", status=e.response.status_code)
            raise AdapterError(
                f"Bedrock API error: {e.response.status_code}",
                provider=self.provider,
            ) from e

        except Exception as e:
            logger.error("bedrock_error", model=request.model, error=str(e))
            raise AdapterError(f"Bedrock API error: {str(e)}", provider=self.provider) from e

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Execute streaming chat completion."""
        request_id = f"msg-{int(time.time())}"

        try:
            model_id = request.model
            provider_family = model_id.split(".")[0] if "." in model_id else "anthropic"

            # Build request body
            if provider_family == "anthropic":
                body = self._build_claude_request(request, stream=True)
            else:
                body = self._build_titan_request(request)
                body["stream"] = True

            path = f"/model/{model_id}/invoke-with-response-stream"
            body_bytes = json.dumps(body).encode()

            headers = self._sign_request("POST", path, body_bytes)

            async with self._client.stream(
                "POST",
                f"{self.base_url}{path}",
                content=body_bytes,
                headers=headers,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or line == "":
                        continue

                    # Parse SSE event
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data:
                            try:
                                event = json.loads(data)
                                chunk = self._parse_stream_event(event, request_id, model_id)
                                if chunk:
                                    yield chunk
                            except json.JSONDecodeError:
                                continue

            # Final chunk
            yield StreamChunk(
                id=request_id,
                model=model_id,
                delta={},
                finish_reason="stop",
                provider=self.provider,
            )

        except Exception as e:
            logger.error("bedrock_stream_error", model=request.model, error=str(e))
            raise AdapterError(f"Bedrock streaming error: {str(e)}", provider=self.provider) from e

    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Execute embedding request."""
        try:
            model_id = request.model
            texts = request.input if isinstance(request.input, list) else [request.input]

            embeddings = []
            total_tokens = 0

            for idx, text in enumerate(texts):
                body = {"inputText": text}

                # Add dimensions for Titan v2
                if "titan-embed-text-v2" in model_id and request.dimensions:
                    body["dimensions"] = request.dimensions

                path = f"/model/{model_id}/invoke"
                body_bytes = json.dumps(body).encode()

                headers = self._sign_request("POST", path, body_bytes)
                response = await self._client.post(
                    f"{self.base_url}{path}",
                    content=body_bytes,
                    headers=headers,
                )

                response.raise_for_status()
                result = response.json()

                embeddings.append(Embedding(
                    index=idx,
                    embedding=result.get("embedding", []),
                ))
                total_tokens += result.get("inputTextTokenCount", 0)

            return EmbeddingResponse(
                id=f"emb-{int(time.time())}",
                model=model_id,
                data=embeddings,
                usage=Usage(
                    prompt_tokens=total_tokens,
                    completion_tokens=0,
                    total_tokens=total_tokens,
                ),
                provider=self.provider,
            )

        except Exception as e:
            logger.error("bedrock_embedding_error", model=request.model, error=str(e))
            raise AdapterError(f"Bedrock embedding error: {str(e)}", provider=self.provider) from e

    async def list_models(self) -> list[str]:
        """List Bedrock models."""
        return list(BEDROCK_MODELS)

    def supports_model(self, model: str) -> bool:
        """Check if model is a Bedrock model."""
        # Bedrock models have format: provider.model-name
        if "." in model:
            provider = model.split(".")[0]
            return provider in ["anthropic", "amazon", "cohere", "ai21", "meta", "mistral"]
        return False

    def _build_claude_request(self, request: ChatCompletionRequest, stream: bool = False) -> dict[str, Any]:
        """Build Claude-style request for Bedrock."""
        # Extract system prompt and messages
        system_prompt = None
        messages = []

        for msg in request.messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content if isinstance(msg.content, str) else ""
            else:
                content = msg.content if isinstance(msg.content, str) else msg.content
                if isinstance(content, str):
                    content = [{"type": "text", "text": content}]
                messages.append({
                    "role": msg.role.value,
                    "content": content,
                })

        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": request.max_tokens or 4096,
            "messages": messages,
        }

        if system_prompt:
            body["system"] = system_prompt
        if request.temperature != 1.0:
            body["temperature"] = request.temperature
        if request.top_p != 1.0:
            body["top_p"] = request.top_p
        if request.stop:
            body["stop_sequences"] = request.stop if isinstance(request.stop, list) else [request.stop]

        return body

    def _build_titan_request(self, request: ChatCompletionRequest) -> dict[str, Any]:
        """Build Amazon Titan request."""
        # Convert messages to single prompt
        prompt = "\n".join(
            f"{msg.role.value}: {msg.content if isinstance(msg.content, str) else str(msg.content)}"
            for msg in request.messages
        )

        return {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": request.max_tokens or 1024,
                "temperature": request.temperature,
                "topP": request.top_p,
                "stopSequences": request.stop if isinstance(request.stop, list) else [request.stop] if request.stop else [],
            },
        }

    def _build_cohere_request(self, request: ChatCompletionRequest) -> dict[str, Any]:
        """Build Cohere Command request."""
        prompt = "\n".join(
            f"{msg.role.value}: {msg.content if isinstance(msg.content, str) else str(msg.content)}"
            for msg in request.messages
        )

        return {
            "prompt": prompt,
            "max_tokens": request.max_tokens or 1024,
            "temperature": request.temperature,
            "p": request.top_p,
        }

    def _build_llama_request(self, request: ChatCompletionRequest) -> dict[str, Any]:
        """Build Llama request."""
        prompt = "<|begin_of_text|>"
        for msg in request.messages:
            role = "user" if msg.role == MessageRole.USER else "assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            prompt += f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>"

        return {"prompt": prompt, "max_gen_len": request.max_tokens or 2048}

    def _build_mistral_request(self, request: ChatCompletionRequest) -> dict[str, Any]:
        """Build Mistral request."""
        prompt = ""
        for msg in request.messages:
            role = "User" if msg.role == MessageRole.USER else "Assistant"
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            prompt += f"[{role}] {content}\n"
        prompt += "[Assistant]"

        return {
            "prompt": prompt,
            "max_tokens": request.max_tokens or 1024,
            "temperature": request.temperature,
            "top_p": request.top_p,
        }

    def _parse_claude_response(
        self, body: dict[str, Any], model_id: str, latency_ms: float
    ) -> ChatCompletionResponse:
        """Parse Claude response from Bedrock."""
        content = body.get("content", [])
        text = ""
        for block in content:
            if block.get("type") == "text":
                text += block.get("text", "")

        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=text,
        )

        usage = body.get("usage", {})

        return ChatCompletionResponse(
            id=f"msg_{int(time.time())}",
            model=model_id,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=message,
                    finish_reason=body.get("stop_reason", "end_turn"),
                )
            ],
            usage=Usage(
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            ),
            created=int(time.time()),
            provider=self.provider,
            latency_ms=latency_ms,
        )

    def _parse_generic_response(
        self, body: dict[str, Any], model_id: str, latency_ms: float
    ) -> ChatCompletionResponse:
        """Parse generic response from Bedrock."""
        # Handle different response formats
        if "results" in body:
            # Titan/Amazon format
            results = body["results"][0]
            text = results.get("outputText", "")
            prompt_tokens = body.get("inputTextTokenCount", 0)
            completion_tokens = results.get("tokenCount", 0)
        elif "generations" in body:
            # Cohere format
            text = body["generations"][0].get("text", "")
            prompt_tokens = 0
            completion_tokens = 0
        elif "generation" in body:
            # Llama/Mistral format
            text = body.get("generation", "")
            prompt_tokens = body.get("prompt_token_count", 0)
            completion_tokens = body.get("generation_token_count", 0)
        else:
            text = str(body)
            prompt_tokens = 0
            completion_tokens = 0

        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=text,
        )

        return ChatCompletionResponse(
            id=f"msg_{int(time.time())}",
            model=model_id,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=message,
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            created=int(time.time()),
            provider=self.provider,
            latency_ms=latency_ms,
        )

    def _parse_stream_event(
        self, event: dict[str, Any], request_id: str, model_id: str
    ) -> StreamChunk | None:
        """Parse streaming event from Bedrock."""
        # Bedrock streaming format varies by provider
        if "bytes" in event:
            # Decode bytes
            import base64
            try:
                data = json.loads(base64.b64decode(event["bytes"]))
                if "delta" in data:
                    return StreamChunk(
                        id=request_id,
                        model=model_id,
                        delta={"content": data["delta"].get("text", "")},
                        provider=self.provider,
                    )
            except Exception:
                pass

        return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


# Register Bedrock model patterns
AdapterRegistry.register_model_prefix("anthropic.claude", Provider.AWS_BEDROCK)
AdapterRegistry.register_model_prefix("amazon.titan", Provider.AWS_BEDROCK)
AdapterRegistry.register_model_prefix("cohere.", Provider.AWS_BEDROCK)
AdapterRegistry.register_model_prefix("ai21.", Provider.AWS_BEDROCK)
AdapterRegistry.register_model_prefix("meta.llama", Provider.AWS_BEDROCK)
AdapterRegistry.register_model_prefix("mistral.", Provider.AWS_BEDROCK)

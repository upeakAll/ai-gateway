"""Open source / local model adapters."""

from app.adapters.open_source.ollama import OllamaAdapter
from app.adapters.open_source.vllm import VLLMAdapter

__all__ = [
    "OllamaAdapter",
    "VLLMAdapter",
]

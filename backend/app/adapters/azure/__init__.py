"""Azure OpenAI adapter package."""

from app.adapters.azure.adapter import AZURE_MODEL_PATTERNS, AzureOpenAIAdapter

__all__ = ["AzureOpenAIAdapter", "AZURE_MODEL_PATTERNS"]

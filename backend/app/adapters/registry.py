"""Adapter registry for managing LLM provider adapters."""

import structlog
from typing import TYPE_CHECKING, Any

from app.adapters.base import BaseAdapter
from app.core.exceptions import AdapterError, ModelNotSupportedError
from app.models.channel import Provider

if TYPE_CHECKING:
    from app.models.channel import Channel

logger = structlog.get_logger()


class AdapterRegistry:
    """Registry for managing LLM provider adapters.

    Provides a centralized way to:
    - Register adapter classes for different providers
    - Create adapter instances with configuration
    - Find appropriate adapters for models
    """

    _adapters: dict[Provider, type[BaseAdapter]] = {}
    _model_prefixes: dict[str, Provider] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, provider: Provider, adapter_class: type[BaseAdapter]) -> None:
        """Register an adapter class for a provider.

        Args:
            provider: Provider identifier
            adapter_class: Adapter class to register
        """
        cls._adapters[provider] = adapter_class
        logger.debug(
            "adapter_registered",
            provider=provider.value,
            adapter=adapter_class.__name__,
        )

    @classmethod
    def register_model_prefix(cls, prefix: str, provider: Provider) -> None:
        """Register a model name prefix for provider detection.

        Args:
            prefix: Model name prefix (e.g., "gpt-", "claude-")
            provider: Provider to use for models with this prefix
        """
        cls._model_prefixes[prefix] = provider

    @classmethod
    def get_adapter_class(cls, provider: Provider) -> type[BaseAdapter] | None:
        """Get the adapter class for a provider.

        Args:
            provider: Provider identifier

        Returns:
            Adapter class or None if not registered
        """
        return cls._adapters.get(provider)

    @classmethod
    def create_adapter(
        cls,
        channel: "Channel",
        **extra_config: Any,
    ) -> BaseAdapter:
        """Create an adapter instance for a channel.

        Args:
            channel: Channel configuration
            **extra_config: Additional configuration for the adapter

        Returns:
            Configured adapter instance

        Raises:
            AdapterError: If provider is not supported
        """
        adapter_class = cls._adapters.get(channel.provider)
        if adapter_class is None:
            raise AdapterError(
                f"Provider '{channel.provider.value}' is not supported",
                provider=channel.provider.value,
            )

        # Prepare adapter configuration
        config: dict[str, Any] = {
            "api_key": channel.api_key,
            "api_base": channel.api_base,
            "api_version": channel.api_version,
            **extra_config,
        }

        # Add AWS-specific configuration
        if channel.provider == Provider.AWS_BEDROCK:
            config.update(
                {
                    "aws_region": channel.aws_region,
                    "aws_access_key_id": channel.aws_access_key_id,
                    "aws_secret_access_key": channel.aws_secret_access_key,
                }
            )

        # Add channel-specific config
        if channel.config:
            config.update(channel.config)

        return adapter_class(**config)

    @classmethod
    def get_provider_for_model(cls, model: str) -> Provider | None:
        """Determine the provider for a model name.

        Uses registered model prefixes to detect provider.

        Args:
            model: Model name

        Returns:
            Provider or None if unknown
        """
        # Check exact matches first
        for prefix, provider in cls._model_prefixes.items():
            if model.startswith(prefix):
                return provider

        # Check if model contains known patterns
        model_lower = model.lower()
        if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
            return Provider.OPENAI
        if "claude" in model_lower:
            return Provider.ANTHROPIC
        if "gemini" in model_lower:
            return Provider.GOOGLE_VERTEX
        if "llama" in model_lower or "mistral" in model_lower:
            # Could be multiple providers
            return Provider.OPENAI  # Default to OpenAI-compatible

        return None

    @classmethod
    def list_providers(cls) -> list[Provider]:
        """List all registered providers.

        Returns:
            List of registered provider identifiers
        """
        return list(cls._adapters.keys())

    @classmethod
    def is_provider_registered(cls, provider: Provider) -> bool:
        """Check if a provider is registered.

        Args:
            provider: Provider identifier

        Returns:
            True if provider has a registered adapter
        """
        return provider in cls._adapters

    @classmethod
    async def health_check(cls, channel: "Channel") -> bool:
        """Perform a health check on a channel using its adapter.

        Args:
            channel: Channel to check

        Returns:
            True if healthy, False otherwise
        """
        try:
            adapter = cls.create_adapter(channel)
            models = await adapter.list_models()
            await adapter.close()
            return len(models) > 0
        except Exception as e:
            logger.warning(
                "health_check_failed",
                channel_id=str(channel.id),
                provider=channel.provider.value,
                error=str(e),
            )
            return False


def register_adapter(provider: Provider) -> Any:
    """Decorator to register an adapter class.

    Usage:
        @register_adapter(Provider.OPENAI)
        class OpenAIAdapter(BaseAdapter):
            ...

    Args:
        provider: Provider identifier

    Returns:
        Decorator function
    """

    def decorator(cls: type[BaseAdapter]) -> type[BaseAdapter]:
        AdapterRegistry.register(provider, cls)
        cls.provider = provider.value
        return cls

    return decorator

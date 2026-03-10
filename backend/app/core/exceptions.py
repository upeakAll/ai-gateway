"""Custom exceptions for the AI Gateway."""


class AIGatewayError(Exception):
    """Base exception for all AI Gateway errors."""

    def __init__(self, message: str, code: str | None = None) -> None:
        self.message = message
        self.code = code or "INTERNAL_ERROR"
        super().__init__(self.message)


class AuthenticationError(AIGatewayError):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, code="AUTHENTICATION_ERROR")


class AuthorizationError(AIGatewayError):
    """Authorization failed - user lacks required permissions."""

    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message, code="AUTHORIZATION_ERROR")


class APIKeyNotFoundError(AuthenticationError):
    """API key not found."""

    def __init__(self, message: str = "API key not found") -> None:
        super().__init__(message)


class APIKeyExpiredError(AuthenticationError):
    """API key has expired."""

    def __init__(self, message: str = "API key has expired") -> None:
        super().__init__(message)


class TenantNotFoundError(AIGatewayError):
    """Tenant not found."""

    def __init__(self, message: str = "Tenant not found") -> None:
        super().__init__(message, code="TENANT_NOT_FOUND")


class TenantQuotaExceededError(AIGatewayError):
    """Tenant quota exceeded."""

    def __init__(self, message: str = "Tenant quota exceeded") -> None:
        super().__init__(message, code="QUOTA_EXCEEDED")


class ChannelNotFoundError(AIGatewayError):
    """Channel not found."""

    def __init__(self, message: str = "Channel not found") -> None:
        super().__init__(message, code="CHANNEL_NOT_FOUND")


class ChannelUnavailableError(AIGatewayError):
    """Channel is unavailable (unhealthy or disabled)."""

    def __init__(self, message: str = "Channel is unavailable") -> None:
        super().__init__(message, code="CHANNEL_UNAVAILABLE")


class NoAvailableChannelError(AIGatewayError):
    """No available channels for the requested model."""

    def __init__(self, message: str = "No available channels for this model") -> None:
        super().__init__(message, code="NO_AVAILABLE_CHANNEL")


class RateLimitExceededError(AIGatewayError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, code="RATE_LIMIT_EXCEEDED")


class ModelNotSupportedError(AIGatewayError):
    """Requested model is not supported."""

    def __init__(self, model: str) -> None:
        super().__init__(
            f"Model '{model}' is not supported or not available",
            code="MODEL_NOT_SUPPORTED",
        )


class AdapterError(AIGatewayError):
    """Error in LLM adapter."""

    def __init__(self, message: str, provider: str | None = None) -> None:
        self.provider = provider
        super().__init__(message, code="ADAPTER_ERROR")


class AdapterTimeoutError(AdapterError):
    """Adapter request timed out."""

    def __init__(self, provider: str | None = None) -> None:
        super().__init__(
            f"Request to {provider or 'provider'} timed out",
            provider=provider,
        )


class AdapterRateLimitError(AdapterError):
    """Adapter hit provider rate limit."""

    def __init__(self, provider: str | None = None, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(
            f"Provider {provider or 'unknown'} rate limit exceeded",
            provider=provider,
        )


class StreamingError(AIGatewayError):
    """Error during streaming response."""

    def __init__(self, message: str = "Streaming error") -> None:
        super().__init__(message, code="STREAMING_ERROR")


class BillingError(AIGatewayError):
    """Error in billing calculation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="BILLING_ERROR")


class MCPError(AIGatewayError):
    """Error in MCP protocol handling."""

    def __init__(self, message: str, code: str = "MCP_ERROR") -> None:
        super().__init__(message, code=code)


class MCPToolNotFoundError(MCPError):
    """MCP tool not found."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"MCP tool '{tool_name}' not found", code="TOOL_NOT_FOUND")


class MCPToolExecutionError(MCPError):
    """Error executing MCP tool."""

    def __init__(self, tool_name: str, reason: str) -> None:
        super().__init__(
            f"Error executing tool '{tool_name}': {reason}",
            code="TOOL_EXECUTION_ERROR",
        )


class MCPServerNotFoundError(MCPError):
    """MCP server not found."""

    def __init__(self, server_name: str) -> None:
        super().__init__(f"MCP server '{server_name}' not found", code="SERVER_NOT_FOUND")


class ValidationError(AIGatewayError):
    """Validation error."""

    def __init__(self, message: str, field: str | None = None) -> None:
        self.field = field
        super().__init__(message, code="VALIDATION_ERROR")


class ConfigurationError(AIGatewayError):
    """Configuration error."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONFIGURATION_ERROR")

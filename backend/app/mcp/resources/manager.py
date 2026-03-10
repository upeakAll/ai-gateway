"""MCP Resources implementation."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()


@dataclass
class Resource:
    """MCP Resource definition."""

    uri: str
    name: str
    description: str | None = None
    mime_type: str | None = None
    size: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_mcp_format(self) -> dict[str, Any]:
        """Convert to MCP protocol format."""
        result: dict[str, Any] = {
            "uri": self.uri,
            "name": self.name,
        }
        if self.description:
            result["description"] = self.description
        if self.mime_type:
            result["mimeType"] = self.mime_type
        if self.size is not None:
            result["size"] = self.size
        return result


@dataclass
class ResourceContent:
    """Content of a resource."""

    uri: str
    mime_type: str | None = None
    text: str | None = None
    blob: bytes | None = None

    def to_mcp_format(self) -> dict[str, Any]:
        """Convert to MCP protocol format."""
        result: dict[str, Any] = {"uri": self.uri}
        if self.mime_type:
            result["mimeType"] = self.mime_type
        if self.text is not None:
            result["text"] = self.text
        if self.blob is not None:
            import base64
            result["blob"] = base64.b64encode(self.blob).decode()
        return result


class ResourceProvider(ABC):
    """Abstract base class for resource providers."""

    @abstractmethod
    async def list_resources(self) -> list[Resource]:
        """List available resources."""
        pass

    @abstractmethod
    async def read_resource(self, uri: str) -> ResourceContent:
        """Read a resource by URI."""
        pass

    async def subscribe(self, uri: str) -> bool:
        """Subscribe to resource updates.

        Returns True if subscription is supported.
        """
        return False

    async def unsubscribe(self, uri: str) -> None:
        """Unsubscribe from resource updates."""
        pass


class StaticResourceProvider(ResourceProvider):
    """Provider for static resources."""

    def __init__(self) -> None:
        self._resources: dict[str, Resource] = {}
        self._contents: dict[str, ResourceContent] = {}

    def add_resource(self, resource: Resource, content: ResourceContent) -> None:
        """Add a static resource."""
        self._resources[resource.uri] = resource
        self._contents[resource.uri] = content

    def remove_resource(self, uri: str) -> None:
        """Remove a static resource."""
        self._resources.pop(uri, None)
        self._contents.pop(uri, None)

    async def list_resources(self) -> list[Resource]:
        """List all static resources."""
        return list(self._resources.values())

    async def read_resource(self, uri: str) -> ResourceContent:
        """Read a static resource."""
        content = self._contents.get(uri)
        if not content:
            raise ValueError(f"Resource not found: {uri}")
        return content


class FileResourceProvider(ResourceProvider):
    """Provider for file-based resources."""

    def __init__(self, base_path: str, allowed_extensions: set[str] | None = None) -> None:
        self.base_path = base_path
        self.allowed_extensions = allowed_extensions

    async def list_resources(self) -> list[Resource]:
        """List files in the base path."""
        import os

        resources = []

        try:
            for root, _, files in os.walk(self.base_path):
                for filename in files:
                    filepath = os.path.join(root, filename)

                    # Check extension
                    if self.allowed_extensions:
                        ext = os.path.splitext(filename)[1].lower()
                        if ext not in self.allowed_extensions:
                            continue

                    rel_path = os.path.relpath(filepath, self.base_path)
                    uri = f"file://{rel_path}"

                    # Determine mime type
                    mime_type = self._get_mime_type(filename)

                    # Get file size
                    size = os.path.getsize(filepath)

                    resources.append(Resource(
                        uri=uri,
                        name=filename,
                        description=f"File: {rel_path}",
                        mime_type=mime_type,
                        size=size,
                    ))
        except Exception as e:
            logger.error("file_resource_list_error", error=str(e))

        return resources

    async def read_resource(self, uri: str) -> ResourceContent:
        """Read a file resource."""
        import os

        parsed = urlparse(uri)
        if parsed.scheme != "file":
            raise ValueError(f"Invalid URI scheme: {uri}")

        rel_path = parsed.path
        filepath = os.path.join(self.base_path, rel_path)

        # Security check - ensure path is within base_path
        real_path = os.path.realpath(filepath)
        if not real_path.startswith(os.path.realpath(self.base_path)):
            raise ValueError(f"Access denied: {uri}")

        if not os.path.exists(filepath):
            raise ValueError(f"File not found: {uri}")

        mime_type = self._get_mime_type(filepath)

        # Read as text or binary
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
            return ResourceContent(uri=uri, mime_type=mime_type, text=text)
        except UnicodeDecodeError:
            with open(filepath, "rb") as f:
                blob = f.read()
            return ResourceContent(uri=uri, mime_type=mime_type, blob=blob)

    def _get_mime_type(self, filename: str) -> str:
        """Guess MIME type from filename."""
        import mimetypes

        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"


class ResourceManager:
    """Manager for MCP resources.

    Coordinates multiple resource providers.
    """

    def __init__(self) -> None:
        self._providers: dict[str, ResourceProvider] = {}
        self._subscriptions: dict[str, set[str]] = {}  # uri -> session_ids

    def register_provider(self, scheme: str, provider: ResourceProvider) -> None:
        """Register a provider for a URI scheme."""
        self._providers[scheme] = provider
        logger.info("resource_provider_registered", scheme=scheme)

    def unregister_provider(self, scheme: str) -> None:
        """Unregister a provider."""
        self._providers.pop(scheme, None)

    async def list_resources(self) -> list[Resource]:
        """List all resources from all providers."""
        all_resources = []

        for provider in self._providers.values():
            try:
                resources = await provider.list_resources()
                all_resources.extend(resources)
            except Exception as e:
                logger.warning(
                    "resource_list_error",
                    error=str(e),
                )

        return all_resources

    async def read_resource(self, uri: str) -> ResourceContent:
        """Read a resource by URI."""
        from urllib.parse import urlparse

        parsed = urlparse(uri)
        scheme = parsed.scheme

        provider = self._providers.get(scheme)
        if not provider:
            raise ValueError(f"No provider for scheme: {scheme}")

        return await provider.read_resource(uri)

    async def subscribe(self, session_id: str, uri: str) -> bool:
        """Subscribe a session to resource updates."""
        from urllib.parse import urlparse

        parsed = urlparse(uri)
        scheme = parsed.scheme

        provider = self._providers.get(scheme)
        if not provider:
            return False

        # Try to subscribe with provider
        subscribed = await provider.subscribe(uri)
        if not subscribed:
            return False

        # Track subscription
        if uri not in self._subscriptions:
            self._subscriptions[uri] = set()
        self._subscriptions[uri].add(session_id)

        return True

    async def unsubscribe(self, session_id: str, uri: str) -> None:
        """Unsubscribe a session from resource updates."""
        if uri in self._subscriptions:
            self._subscriptions[uri].discard(session_id)
            if not self._subscriptions[uri]:
                del self._subscriptions[uri]

                # Notify provider
                from urllib.parse import urlparse
                parsed = urlparse(uri)
                provider = self._providers.get(parsed.scheme)
                if provider:
                    await provider.unsubscribe(uri)

    async def notify_update(self, uri: str) -> list[str]:
        """Notify subscribers of resource update.

        Returns list of session IDs that should be notified.
        """
        return list(self._subscriptions.get(uri, set()))


# Global resource manager
resource_manager = ResourceManager()

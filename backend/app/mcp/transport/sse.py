"""SSE transport for MCP protocol."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Callable

import structlog
from sse_starlette.sse import EventSourceResponse

logger = structlog.get_logger()


@dataclass
class SSEClient:
    """SSE client connection."""

    session_id: str
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    connected_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())


class SSETransport:
    """Server-Sent Events transport for MCP.

    Implements bidirectional communication:
    - Client sends requests via POST
    - Server sends responses and notifications via SSE
    """

    def __init__(self, heartbeat_interval: int = 30) -> None:
        self._clients: dict[str, SSEClient] = {}
        self._heartbeat_interval = heartbeat_interval
        self._request_handlers: dict[str, Callable[..., Any]] = {}

    def register_client(self, session_id: str) -> SSEClient:
        """Register a new SSE client."""
        client = SSEClient(session_id=session_id)
        self._clients[session_id] = client

        logger.info(
            "sse_client_registered",
            session_id=session_id,
        )

        return client

    def unregister_client(self, session_id: str) -> None:
        """Unregister an SSE client."""
        client = self._clients.pop(session_id, None)
        if client:
            logger.info(
                "sse_client_unregistered",
                session_id=session_id,
            )

    async def send(self, session_id: str, data: dict[str, Any]) -> bool:
        """Send data to a specific client."""
        client = self._clients.get(session_id)
        if client:
            await client.queue.put(data)
            return True
        return False

    async def broadcast(self, method: str, params: dict[str, Any]) -> int:
        """Broadcast notification to all connected clients.

        Returns:
            Number of clients that received the message
        """
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        count = 0
        for client in self._clients.values():
            try:
                await client.queue.put(message)
                count += 1
            except Exception as e:
                logger.warning(
                    "sse_broadcast_failed",
                    session_id=client.session_id,
                    error=str(e),
                )

        return count

    async def event_stream(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        """Generate SSE event stream for a client.

        Yields:
            SSE event dictionaries
        """
        client = self.register_client(session_id)

        try:
            while True:
                try:
                    # Wait for message with timeout for heartbeat
                    message = await asyncio.wait_for(
                        client.queue.get(),
                        timeout=self._heartbeat_interval,
                    )

                    yield {
                        "event": "message",
                        "data": json.dumps(message),
                    }

                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield {
                        "event": "ping",
                        "data": "",
                    }

        except asyncio.CancelledError:
            pass
        finally:
            self.unregister_client(session_id)

    def create_response(self, session_id: str) -> EventSourceResponse:
        """Create SSE response for a client."""
        return EventSourceResponse(
            self.event_stream(session_id),
            media_type="text/event-stream",
        )


class StreamableHTTPTransport:
    """Streamable HTTP transport for MCP.

    Supports both synchronous and streaming responses.
    """

    def __init__(self) -> None:
        self._pending_requests: dict[str, asyncio.Future[Any]] = {}

    async def send_request(
        self,
        request_id: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send a request and wait for response."""
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            # Wait for response with timeout
            return await asyncio.wait_for(future, timeout=300.0)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise
        finally:
            self._pending_requests.pop(request_id, None)

    async def handle_response(self, request_id: str, result: Any) -> bool:
        """Handle a response for a pending request."""
        future = self._pending_requests.get(request_id)
        if future and not future.done():
            future.set_result(result)
            return True
        return False

    async def handle_error(self, request_id: str, error: Exception) -> bool:
        """Handle an error for a pending request."""
        future = self._pending_requests.get(request_id)
        if future and not future.done():
            future.set_exception(error)
            return True
        return False

"""MCP session management."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class MCPSession:
    """MCP client session."""

    id: str
    client_info: dict[str, Any]
    capabilities: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    subscriptions: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def is_expired(self, timeout_seconds: int = 3600) -> bool:
        """Check if session is expired."""
        return time.time() - self.last_activity > timeout_seconds

    def add_subscription(self, uri: str) -> None:
        """Add a resource subscription."""
        self.subscriptions.add(uri)

    def remove_subscription(self, uri: str) -> None:
        """Remove a resource subscription."""
        self.subscriptions.discard(uri)

    def has_subscription(self, uri: str) -> bool:
        """Check if subscribed to a resource."""
        return uri in self.subscriptions


class MCPSessionManager:
    """Manager for MCP client sessions."""

    def __init__(self, session_timeout: int = 3600) -> None:
        self._sessions: dict[str, MCPSession] = {}
        self._session_timeout = session_timeout
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_id: str,
        client_info: dict[str, Any],
        capabilities: dict[str, Any],
    ) -> MCPSession:
        """Create a new session."""
        async with self._lock:
            session = MCPSession(
                id=session_id,
                client_info=client_info,
                capabilities=capabilities,
            )
            self._sessions[session_id] = session

            logger.info(
                "mcp_session_created",
                session_id=session_id,
                client_info=client_info,
            )

            return session

    async def get_session(self, session_id: str) -> MCPSession | None:
        """Get a session by ID."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.touch()
            return session

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                logger.info(
                    "mcp_session_deleted",
                    session_id=session_id,
                )

    async def list_sessions(self) -> list[MCPSession]:
        """List all active sessions."""
        async with self._lock:
            return list(self._sessions.values())

    async def cleanup_expired(self) -> int:
        """Remove expired sessions.

        Returns:
            Number of sessions removed
        """
        async with self._lock:
            expired_ids = [
                sid
                for sid, session in self._sessions.items()
                if session.is_expired(self._session_timeout)
            ]

            for sid in expired_ids:
                del self._sessions[sid]

            if expired_ids:
                logger.info(
                    "mcp_sessions_cleaned",
                    count=len(expired_ids),
                )

            return len(expired_ids)

    async def get_sessions_with_subscription(self, uri: str) -> list[MCPSession]:
        """Get all sessions subscribed to a resource."""
        async with self._lock:
            return [
                session
                for session in self._sessions.values()
                if session.has_subscription(uri)
            ]

    async def subscribe(self, session_id: str, uri: str) -> bool:
        """Subscribe a session to a resource."""
        session = await self.get_session(session_id)
        if session:
            session.add_subscription(uri)
            return True
        return False

    async def unsubscribe(self, session_id: str, uri: str) -> bool:
        """Unsubscribe a session from a resource."""
        session = await self.get_session(session_id)
        if session:
            session.remove_subscription(uri)
            return True
        return False

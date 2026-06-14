"""MCP integration exceptions."""

from __future__ import annotations


class MCPIntegrationError(RuntimeError):
    """Base class for MCP client/registry failures."""


class MCPToolExecutionError(MCPIntegrationError):
    """Raised when a tool returns ``isError`` or malformed output."""

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class MCPConnectionError(MCPIntegrationError):
    """Raised when the MCP transport or handshake fails."""

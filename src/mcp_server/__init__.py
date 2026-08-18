"""Authenticated MCP interface for SignalDesk's read-only CDP tools."""

from .auth import StaticBearerTokenVerifier
from .server import (
    READ_SCOPE,
    SERVER_NAME,
    SERVER_VERSION,
    MCPServerConfig,
    SignalDeskMCPServer,
    create_server,
)

__all__ = [
    "MCPServerConfig",
    "READ_SCOPE",
    "SERVER_NAME",
    "SERVER_VERSION",
    "SignalDeskMCPServer",
    "StaticBearerTokenVerifier",
    "create_server",
]

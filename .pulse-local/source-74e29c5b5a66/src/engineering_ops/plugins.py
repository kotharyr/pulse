from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from mcp.server.fastmcp import FastMCP

from engineering_ops.auth import protect_http_route
from engineering_ops.config import settings


ToolFunction = Callable[..., Any]
RouteFunction = Callable[..., Any]


class MCPPlugin(Protocol):
    """A self-contained capability that can extend an MCP server."""

    name: str

    def register(self, server: FastMCP) -> None: ...


@dataclass(frozen=True)
class CapabilityPlugin:
    """Declarative plugin for MCP tools and custom HTTP routes."""

    name: str
    tools: tuple[ToolFunction, ...] = ()
    routes: tuple[tuple[str, tuple[str, ...], RouteFunction], ...] = ()

    def register(self, server: FastMCP) -> None:
        for tool in self.tools:
            server.add_tool(tool)
        for path, methods, handler in self.routes:
            # The console shell and lightweight liveness probes contain no workspace data.
            public = path in {"/console", "/console/", "/console/{asset}", "/health", "/health/live"}
            if settings.mcp_bearer_token and not public:
                handler = protect_http_route(handler, settings.mcp_bearer_token)
            server.custom_route(path, methods=list(methods))(handler)


@dataclass
class PluginRegistry:
    """Ordered plugin registry used to compose the application."""

    _plugins: dict[str, MCPPlugin] = field(default_factory=dict)

    def add(self, plugin: MCPPlugin) -> None:
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin already registered: {plugin.name}")
        self._plugins[plugin.name] = plugin

    def install(self, server: FastMCP) -> None:
        for plugin in self._plugins.values():
            plugin.register(server)

    @property
    def names(self) -> list[str]:
        return list(self._plugins)


from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings
from mcp.server.fastmcp.tools import Tool
from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl, BaseModel, create_model
from starlette.applications import Starlette

from src.tools import CDPTools, ToolRegistry
from src.tools.schemas import (
    GetCampaignEligibilityInput,
    GetCustomerEventsInput,
    GetCustomerProfileInput,
    SearchKnowledgeBaseInput,
    ToolCallResult,
)

from .auth import StaticBearerTokenVerifier


SERVER_NAME = "signaldesk-cdp"
SERVER_VERSION = "commit14_v1"
READ_SCOPE = "signaldesk:read"

# MCP SDK 1.29 leaves the generic lifespan annotation unresolved at import time.
Settings.model_rebuild()


@dataclass(frozen=True)
class MCPServerConfig:
    database: Path = Path("data/warehouse/signaldesk.duckdb")
    corpus_dir: Path = Path("data/generated/knowledge")
    host: str = "127.0.0.1"
    port: int = 8000
    bearer_token: str = field(default="", repr=False)
    issuer_url: str = "https://auth.signaldesk.local"
    resource_server_url: str = "http://127.0.0.1:8000/mcp"

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        AnyHttpUrl(self.issuer_url)
        AnyHttpUrl(self.resource_server_url)


def _strict_tool(
    fn: Callable[..., ToolCallResult],
    *,
    name: str,
    description: str,
    input_model: type[BaseModel],
) -> Tool:
    """Build a FastMCP tool with the existing strict flat input schema."""

    tool = Tool.from_function(
        fn,
        name=name,
        description=description,
        annotations=ToolAnnotations(
            title=name.replace("_", " ").title(),
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        meta={
            "signaldesk/serverVersion": SERVER_VERSION,
            "signaldesk/sideEffects": "none",
        },
        structured_output=True,
    )
    argument_model = create_model(
        f"{name.title().replace('_', '')}Arguments",
        __base__=(input_model, ArgModelBase),
    )
    metadata = tool.fn_metadata.model_copy(update={"arg_model": argument_model})
    return tool.model_copy(update={
        "parameters": argument_model.model_json_schema(),
        "fn_metadata": metadata,
    })


class SignalDeskMCPServer:
    """Authenticated MCP adapter over SignalDesk's read-only CDP registry."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        token_verifier = StaticBearerTokenVerifier(
            config.bearer_token,
            scope=READ_SCOPE,
        )
        self._cdp_tools = CDPTools(config.database, corpus_dir=config.corpus_dir)
        try:
            self._registry = ToolRegistry(self._cdp_tools)
            self.mcp = FastMCP(
                SERVER_NAME,
                instructions=(
                    "Read-only access to PII-safe SignalDesk customer context, "
                    "bounded events, approved knowledge, and campaign review "
                    "constraints."
                ),
                tools=self._build_tools(),
                host=config.host,
                port=config.port,
                streamable_http_path="/mcp",
                stateless_http=True,
                json_response=True,
                token_verifier=token_verifier,
                auth=AuthSettings(
                    issuer_url=AnyHttpUrl(config.issuer_url),
                    resource_server_url=AnyHttpUrl(config.resource_server_url),
                    required_scopes=[READ_SCOPE],
                ),
            )
        except Exception:
            self._cdp_tools.close()
            raise

    def _execute(
        self,
        public_name: str,
        registry_name: str,
        arguments: dict[str, Any],
    ) -> ToolCallResult:
        result = self._registry.execute(registry_name, arguments)
        return result.model_copy(update={"tool_name": public_name})

    def _build_tools(self) -> list[Tool]:
        def customer_profile(customer_id: str) -> ToolCallResult:
            return self._execute(
                "customer_profile",
                "get_customer_profile",
                {"customer_id": customer_id},
            )

        def customer_events(
            customer_id: str,
            days: int = 30,
            limit: int = 50,
            event_types: list[str] | None = None,
        ) -> ToolCallResult:
            return self._execute(
                "customer_events",
                "get_customer_events",
                {
                    "customer_id": customer_id,
                    "days": days,
                    "limit": limit,
                    "event_types": event_types or [],
                },
            )

        def knowledge_search(
            query: str,
            top_k: int = 5,
            families: list[str] | None = None,
        ) -> ToolCallResult:
            return self._execute(
                "knowledge_search",
                "search_knowledge_base",
                {
                    "query": query,
                    "top_k": top_k,
                    "families": families or [],
                },
            )

        def campaign_eligibility(
            customer_id: str,
            channel: str | None = None,
        ) -> ToolCallResult:
            return self._execute(
                "campaign_eligibility",
                "get_campaign_eligibility",
                {"customer_id": customer_id, "channel": channel},
            )

        return [
            _strict_tool(
                customer_profile,
                name="customer_profile",
                description=(
                    "Return a PII-safe customer profile and semantic-layer as-of time."
                ),
                input_model=GetCustomerProfileInput,
            ),
            _strict_tool(
                customer_events,
                name="customer_events",
                description=(
                    "Return bounded identity-resolved events for one customer and "
                    "lookback window."
                ),
                input_model=GetCustomerEventsInput,
            ),
            _strict_tool(
                knowledge_search,
                name="knowledge_search",
                description=(
                    "Search only current approved policy documents using the bounded "
                    "deterministic lexical index."
                ),
                input_model=SearchKnowledgeBaseInput,
            ),
            _strict_tool(
                campaign_eligibility,
                name="campaign_eligibility",
                description=(
                    "Return hard channel blocks and review requirements without "
                    "claiming final campaign eligibility."
                ),
                input_model=GetCampaignEligibilityInput,
            ),
        ]

    def streamable_http_app(self) -> Starlette:
        return self.mcp.streamable_http_app()

    def run(self) -> None:
        self.mcp.run(transport="streamable-http")

    def close(self) -> None:
        self._cdp_tools.close()

    def __enter__(self) -> "SignalDeskMCPServer":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


def create_server(config: MCPServerConfig) -> SignalDeskMCPServer:
    return SignalDeskMCPServer(config)

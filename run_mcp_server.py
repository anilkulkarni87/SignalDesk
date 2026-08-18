#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
from pathlib import Path

from src.mcp_server import MCPServerConfig, create_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the authenticated read-only SignalDesk MCP server.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/warehouse/signaldesk.duckdb"),
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("data/generated/knowledge"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--issuer-url",
        default=os.environ.get(
            "SIGNALDESK_MCP_ISSUER_URL",
            "https://auth.signaldesk.local",
        ),
    )
    parser.add_argument(
        "--resource-server-url",
        default=os.environ.get("SIGNALDESK_MCP_RESOURCE_URL"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = os.environ.get("SIGNALDESK_MCP_TOKEN", "")
    if not token:
        raise SystemExit(
            "Set SIGNALDESK_MCP_TOKEN to a pre-issued bearer token of at least "
            "16 characters."
        )
    resource_server_url = (
        args.resource_server_url or f"http://{args.host}:{args.port}/mcp"
    )
    config = MCPServerConfig(
        database=args.database,
        corpus_dir=args.corpus_dir,
        host=args.host,
        port=args.port,
        bearer_token=token,
        issuer_url=args.issuer_url,
        resource_server_url=resource_server_url,
    )
    with create_server(config) as server:
        print(f"SignalDesk MCP server: {resource_server_url}")
        print("Authentication: Bearer token required")
        print("Scope: signaldesk:read")
        try:
            server.run()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

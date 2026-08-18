#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import json
import os

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover and call the local SignalDesk MCP server.",
    )
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--customer-id", default="C0000001")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    token = os.environ.get("SIGNALDESK_MCP_TOKEN", "")
    if not token:
        raise SystemExit("Set SIGNALDESK_MCP_TOKEN before running the client.")

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(
            args.url,
            http_client=http_client,
        ) as (read_stream, write_stream, _session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                print("Discovered tools:")
                for tool in tools.tools:
                    print(f"- {tool.name}: {tool.description}")

                result = await session.call_tool(
                    "customer_profile",
                    {"customer_id": args.customer_id},
                )
                print("\ncustomer_profile result:")
                print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    asyncio.run(main())

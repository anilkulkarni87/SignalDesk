#!/usr/bin/env python3

from __future__ import annotations

import argparse

import uvicorn

from src.api import APIConfig, create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SignalDesk FastAPI API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        config = APIConfig.from_env()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    uvicorn.run(
        create_app(config),
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Minimal streaming demo.

This intentionally uses plain text rather than the production assessment schema.
The goal is to observe the streaming event lifecycle directly.
"""

from __future__ import annotations

import argparse
import os


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"))
    p.add_argument(
        "--reasoning-effort",
        default="none",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
    )
    return p.parse_args()


def main():
    args = parse_args()

    from openai import OpenAI

    client = OpenAI()

    stream = client.responses.create(
        model=args.model,
        reasoning={"effort": args.reasoning_effort},
        instructions=(
            "You are demonstrating API streaming. Be concise and do not use tools."
        ),
        input=(
            "In four short bullets, explain why deterministic customer metrics "
            "should be calculated before an LLM reasons about them."
        ),
        stream=True,
        store=False,
    )

    for event in stream:
        if event.type == "response.output_text.delta":
            print(event.delta, end="", flush=True)

    print()


if __name__ == "__main__":
    main()

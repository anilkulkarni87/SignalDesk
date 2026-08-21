#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def summarize(samples: list[dict], elapsed_seconds: float) -> dict:
    latencies = [float(sample["latency_ms"]) for sample in samples]
    successful = sum(200 <= int(sample["status_code"]) < 300 for sample in samples)
    return {
        "requests": len(samples),
        "successful_requests": successful,
        "success_rate_pct": round(100 * successful / len(samples), 2) if samples else 0,
        "unhandled_exceptions": sum(
            bool(sample.get("exception")) for sample in samples
        ),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
        },
        "throughput_requests_per_second": round(
            len(samples) / max(elapsed_seconds, 0.0001),
            2,
        ),
        "status_counts": {
            str(code): sum(int(item["status_code"]) == code for item in samples)
            for code in sorted({int(item["status_code"]) for item in samples})
        },
    }


def request_once(url: str, timeout_seconds: float) -> dict:
    started = time.perf_counter()
    status_code = 0
    exception = None
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            status_code = response.status
            response.read()
    except urllib.error.HTTPError as exc:
        status_code = exc.code
    except Exception as exc:
        exception = exc.__class__.__name__
    return {
        "status_code": status_code,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "exception": exception,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded SignalDesk load smoke.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=5)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit17/reports/load_smoke.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.requests < 1 or args.concurrency < 1:
        raise SystemExit("requests and concurrency must be positive")
    url = f"{args.base_url.rstrip('/')}/api/v1/health"
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        samples = list(
            executor.map(
                lambda _: request_once(url, args.timeout_seconds),
                range(args.requests),
            )
        )
    report = summarize(samples, time.perf_counter() - started)
    report["config"] = {
        "url": url,
        "concurrency": args.concurrency,
        "timeout_seconds": args.timeout_seconds,
        "quality_gate": {
            "success_rate_pct": 99,
            "p95_latency_ms": 8000,
        },
    }
    report["passed"] = (
        report["success_rate_pct"] >= 99
        and report["latency_ms"]["p95"] < 8000
        and report["unhandled_exceptions"] == 0
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

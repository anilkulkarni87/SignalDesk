#!/usr/bin/env python3
"""
Benchmark NovaCart synthetic CDP generation at increasing scale.

For each configured customer count, this script:
1. Runs the generator.
2. Runs structural validation.
3. Runs semantic validation.
4. Measures elapsed time, dataset size, row counts, rows/sec.
5. Extracts duplicate/null/late-event rates.
6. Writes a consolidated JSON and CSV benchmark report.

Example:
    python data/generator/benchmark_scale.py \
        --generator data/generator/generate_synthetic_cdp_v4.py \
        --structural-validator data/generator/validate_synthetic_cdp_scale.py \
        --semantic-validator data/generator/validate_semantic_behavior_scale.py \
        --sizes 1000 10000 100000 \
        --output-format parquet \
        --products 1000 \
        --avg-orders 5 \
        --avg-browsing-sessions 6 \
        --output-root data/generated/scale
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List


DATA_FILES = [
    "customers.csv",
    "identities.csv",
    "products.csv",
    "orders.csv",
    "order_items.csv",
    "support_tickets.csv",
    "sessions.csv",
    "events.csv",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark NovaCart synthetic CDP generation.")
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--structural-validator", type=Path, required=True)
    parser.add_argument("--semantic-validator", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1000, 10000, 100000])
    parser.add_argument("--products", type=int, default=1000)
    parser.add_argument("--avg-orders", type=float, default=5.0)
    parser.add_argument("--avg-browsing-sessions", type=float, default=6.0)
    parser.add_argument("--duplicate-event-rate", type=float, default=0.01)
    parser.add_argument("--late-event-rate", type=float, default=0.04)
    parser.add_argument("--null-profile-rate", type=float, default=0.03)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--output-format",
        choices=["csv", "parquet"],
        default="csv",
        help="Storage format passed to the generator.",
    )
    parser.add_argument(
        "--keep-generated-data",
        action="store_true",
        help="Keep generated CSVs after benchmarking. By default, runs are preserved.",
    )
    return parser.parse_args()


def run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def dir_size_bytes(path: Path) -> int:
    total = 0
    for file in path.rglob("*"):
        if file.is_file():
            total += file.stat().st_size
    return total


def data_file_size_bytes(path: Path) -> int:
    total = 0
    for name in DATA_FILES:
        csv_path = path / name
        parquet_path = csv_path.with_suffix(".parquet")
        if csv_path.exists():
            total += csv_path.stat().st_size
        elif parquet_path.exists():
            total += parquet_path.stat().st_size

    truth_csv = path / "_truth" / "customer_generation_truth.csv"
    truth_parquet = truth_csv.with_suffix(".parquet")
    if truth_csv.exists():
        total += truth_csv.stat().st_size
    elif truth_parquet.exists():
        total += truth_parquet.stat().st_size

    return total


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def benchmark_one(args, customer_count: int) -> Dict:
    run_dir = args.output_root / f"{customer_count:09d}_customers"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    generator_cmd = [
        sys.executable, str(args.generator),
        "--customers", str(customer_count),
        "--products", str(args.products),
        "--avg-orders", str(args.avg_orders),
        "--avg-browsing-sessions", str(args.avg_browsing_sessions),
        "--duplicate-event-rate", str(args.duplicate_event_rate),
        "--late-event-rate", str(args.late_event_rate),
        "--null-profile-rate", str(args.null_profile_rate),
        "--seed", str(args.seed),
        "--output-dir", str(run_dir),
        "--output-format", args.output_format,
    ]

    start = time.perf_counter()
    generator_result = run(generator_cmd)
    wall_seconds = time.perf_counter() - start

    result = {
        "customers_requested": customer_count,
        "generator_exit_code": generator_result.returncode,
        "generator_wall_seconds": round(wall_seconds, 3),
        "structural_validation_passed": False,
        "semantic_validation_passed": False,
    }

    if generator_result.returncode != 0:
        result["error"] = generator_result.stderr[-4000:]
        return result

    manifest_path = run_dir / "manifest.json"
    manifest = load_json(manifest_path)
    row_counts = manifest["row_counts"]
    total_rows = sum(v for k, v in row_counts.items() if k != "customer_generation_truth")

    result.update({
        "generator_internal_seconds": manifest["elapsed_seconds"],
        "total_data_rows": total_rows,
        "rows_per_second": round(total_rows / max(wall_seconds, 0.001), 2),
        "dataset_size_bytes": data_file_size_bytes(run_dir),
        "dataset_size_mb": round(data_file_size_bytes(run_dir) / (1024 * 1024), 3),
        "full_run_dir_size_mb": round(dir_size_bytes(run_dir) / (1024 * 1024), 3),
        "row_counts": row_counts,
    })

    structural_report = run_dir / "validation_report.json"
    structural_result = run([
        sys.executable, str(args.structural_validator),
        "--input-dir", str(run_dir),
        "--report", str(structural_report),
    ])
    result["structural_validator_exit_code"] = structural_result.returncode

    if structural_report.exists():
        structural = load_json(structural_report)
        result["structural_validation_passed"] = bool(structural.get("passed"))
        result["duplicate_event_rate_pct"] = structural["event_quality"]["duplicate_event_rate_pct"]
        result["late_event_rate_pct"] = structural["event_quality"]["late_over_1h_rate_pct"]
        result["profile_null_rate_pct"] = structural["profile_nulls"]["overall_profile_null_rate_pct"]
        result["anonymous_session_rate_pct"] = structural["foreign_keys"]["sessions.customer_id"]["anonymous_rate_pct"]
        result["order_total_mismatches"] = structural["order_reconciliation"]["total_mismatches"]

    semantic_report = run_dir / "semantic_validation_report.json"
    semantic_result = run([
        sys.executable, str(args.semantic_validator),
        "--input-dir", str(run_dir),
        "--report", str(semantic_report),
    ])
    result["semantic_validator_exit_code"] = semantic_result.returncode

    if semantic_report.exists():
        semantic = load_json(semantic_report)
        result["semantic_validation_passed"] = bool(semantic.get("passed"))
        tests = semantic["tests"]
        result["declining_pass_rate_pct"] = tests["declining_engagement"].get("decline_pass_rate_pct")
        result["support_ticket_lift_ratio"] = tests["support_issue"].get("ticket_rate_lift_ratio")
        result["discount_lift_percentage_points"] = tests["price_sensitive"].get("lift_percentage_points")
        result["dormant_mean_recent_sessions"] = tests["dormant"].get("dormant_mean_recent_sessions")

    result["passed"] = (
        result["generator_exit_code"] == 0
        and result["structural_validation_passed"]
        and result["semantic_validation_passed"]
    )

    return result


def write_csv(path: Path, results: List[Dict]):
    scalar_keys = [
        "customers_requested",
        "passed",
        "generator_wall_seconds",
        "generator_internal_seconds",
        "total_data_rows",
        "rows_per_second",
        "dataset_size_mb",
        "structural_validation_passed",
        "semantic_validation_passed",
        "duplicate_event_rate_pct",
        "late_event_rate_pct",
        "profile_null_rate_pct",
        "anonymous_session_rate_pct",
        "declining_pass_rate_pct",
        "support_ticket_lift_ratio",
        "discount_lift_percentage_points",
        "dormant_mean_recent_sessions",
        "order_total_mismatches",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=scalar_keys)
        writer.writeheader()
        for result in results:
            writer.writerow({k: result.get(k, "") for k in scalar_keys})


def main():
    args = parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)

    results = []
    for size in args.sizes:
        print(f"\n=== Benchmarking {size:,} customers ===", flush=True)
        result = benchmark_one(args, size)
        results.append(result)
        print(json.dumps(result, indent=2), flush=True)

        # Stop scaling if a lower gate fails.
        if not result.get("passed", False):
            print(f"\nStopping: {size:,}-customer gate failed.", flush=True)
            break

    report = {
        "configuration": {
            "sizes": args.sizes,
            "products": args.products,
            "avg_orders": args.avg_orders,
            "avg_browsing_sessions": args.avg_browsing_sessions,
            "duplicate_event_rate": args.duplicate_event_rate,
            "late_event_rate": args.late_event_rate,
            "null_profile_rate": args.null_profile_rate,
            "seed": args.seed,
            "output_format": args.output_format,
        },
        "results": results,
        "all_executed_gates_passed": all(r.get("passed", False) for r in results),
    }

    json_path = args.output_root / "scale_benchmark_report.json"
    csv_path = args.output_root / "scale_benchmark_report.csv"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_csv(csv_path, results)

    print(f"\nJSON report: {json_path}")
    print(f"CSV report:  {csv_path}")


if __name__ == "__main__":
    main()



# python data/generator/benchmark_scale_v2.py \
#   --generator data/generator/generate_synthetic_cdp_v4.py \
#   --structural-validator data/generator/validate_synthetic_cdp_scale.py \
#   --semantic-validator data/generator/validate_semantic_behavior_scale.py \
#   --sizes 1000 10000 100000 \
#   --products 1000 \
#   --avg-orders 5 \
#   --avg-browsing-sessions 6 \
#   --output-format parquet \
#   --output-root data/generated/scale
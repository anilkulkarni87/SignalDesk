from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CourseCheckError(RuntimeError):
    """Raised when a frozen lesson artifact no longer satisfies its contract."""


def _json(root: Path, relative_path: str) -> dict[str, Any]:
    path = root / relative_path
    if not path.is_file():
        raise CourseCheckError(f"missing evidence: {relative_path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _files(root: Path, *relative_paths: str) -> list[str]:
    checked = []
    for relative_path in relative_paths:
        path = root / relative_path
        if not path.is_file() or path.stat().st_size == 0:
            raise CourseCheckError(f"missing or empty artifact: {relative_path}")
        checked.append(relative_path)
    return checked


def check_lesson(root: Path, lesson_id: str) -> list[str]:
    checks = {
        "01": _check_01,
        "02": _check_02,
        "04": _check_04,
        "06": _check_06,
        "10": _check_10,
        "18": _check_18,
    }
    try:
        check = checks[lesson_id]
    except KeyError as exc:
        raise CourseCheckError(
            f"lesson {lesson_id} does not have a frozen check yet"
        ) from exc
    return check(root)


def _check_01(root: Path) -> list[str]:
    return _files(
        root,
        "docs/customer_problem.md",
        "docs/discovery_notes.md",
        "docs/requirements.md",
        "docs/success_metrics.md",
    )


def _check_02(root: Path) -> list[str]:
    artifacts = _files(
        root,
        "data/generator/generate_synthetic_cdp_v5.py",
        "docs/data_model_v1.md",
        "docs/benchmarks/commit02-scale-benchmark_parquet.json",
    )
    report = _json(root, artifacts[-1])
    scale = next(
        (
            result
            for result in report.get("results", [])
            if result.get("customers_requested") == 100_000
        ),
        None,
    )
    if not scale or not scale.get("passed"):
        raise CourseCheckError("100,000-customer synthetic benchmark did not pass")
    if scale.get("total_data_rows") != 7_005_497:
        raise CourseCheckError("synthetic benchmark row count changed unexpectedly")
    return artifacts


def _check_04(root: Path) -> list[str]:
    artifacts = _files(
        root,
        "run_one.py",
        "evals/commit04/cases_v2.jsonl",
        "evals/commit04/report_luna_none_v2.json",
    )
    report = _json(root, artifacts[-1])
    if report.get("cases") != 30 or report.get("successful_api_calls") != 30:
        raise CourseCheckError("Commit 04 frozen 30-case experiment is incomplete")
    if report.get("schema_valid_rate_pct") != 100.0:
        raise CourseCheckError("Commit 04 schema-validity contract regressed")
    return artifacts


def _check_06(root: Path) -> list[str]:
    artifacts = _files(
        root,
        "evals/commit06/retrieval_cases.jsonl",
        "evals/commit06/reports/retrieval_benchmark.json",
    )
    report = _json(root, artifacts[-1])
    lexical = report.get("retrievers", {}).get("lexical", {})
    vector = report.get("retrievers", {}).get("vector", {})
    if report.get("cases") != 50:
        raise CourseCheckError("Commit 06 benchmark must contain 50 cases")
    if lexical.get("recall_at_5_pct") != 68.0:
        raise CourseCheckError("Commit 06 lexical baseline changed")
    if vector.get("recall_at_5_pct") != 98.0:
        raise CourseCheckError("Commit 06 vector result changed")
    return artifacts


def _check_10(root: Path) -> list[str]:
    artifacts = _files(
        root,
        "evals/commit10/cases.jsonl",
        "evals/commit10/reports/v4_full_report.json",
    )
    report = _json(root, artifacts[-1])
    run_config = report.get("run_config", {})
    if report.get("cases") != 50 or report.get("task_completed_rate_pct") != 100.0:
        raise CourseCheckError("Commit 10 frozen task contract regressed")
    if run_config.get("model") != "gpt-5.6-luna":
        raise CourseCheckError("Commit 10 frozen model changed")
    if run_config.get("reasoning_effort") != "none":
        raise CourseCheckError("Commit 10 reasoning effort changed")
    return artifacts


def _check_18(root: Path) -> list[str]:
    required = [
        "docs/fde/discovery.md",
        "docs/fde/requirements.md",
        "docs/fde/architecture.md",
        "docs/fde/security.md",
        "docs/fde/evaluation.md",
        "docs/fde/deployment.md",
        "docs/fde/runbook.md",
        "docs/fde/roi.md",
        "docs/fde/known_limitations.md",
        "docs/fde/roadmap.md",
        "docs/fde/demo.md",
    ]
    return _files(root, *required)

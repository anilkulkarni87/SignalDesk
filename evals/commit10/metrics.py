from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from typing import Any


EVALUATION_VERSION = "commit10_v4_policy_evidence_and_policy_aggregate"


def pct(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 4)


def mean(values: list[float | int]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def scalar_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) == float(right)
    return type(left) is type(right) and left == right


def scalar_fields(value: Any, path: str = "") -> list[tuple[str, Any]]:
    fields = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if isinstance(child, (dict, list)):
                fields.extend(scalar_fields(child, child_path))
            else:
                fields.append((child_path, child))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            if isinstance(child, (dict, list)):
                fields.extend(scalar_fields(child, child_path))
            else:
                fields.append((child_path, child))
    return fields


def argument_matches(
    arguments: dict[str, Any] | None,
    rules: dict[str, Any],
    output: dict[str, Any] | None,
) -> bool:
    if arguments is None:
        return False
    if "customer_id" in rules and arguments.get("customer_id") != rules["customer_id"]:
        return False
    effective_days = (
        output.get("window_days")
        if output is not None and "window_days" in output
        else arguments.get("days")
    )
    if "days_equals" in rules and effective_days != rules["days_equals"]:
        return False
    if "limit_max" in rules and arguments.get("limit", 1000) > rules["limit_max"]:
        return False
    if rules.get("channel_must_be_null") and arguments.get("channel") is not None:
        return False
    if "top_k_min" in rules and arguments.get("top_k", 5) < rules["top_k_min"]:
        return False
    if (
        "families_per_call_max" in rules
        and len(arguments.get("families", [])) > rules["families_per_call_max"]
    ):
        return False
    return True


def tool_arguments_correct(
    case: dict[str, Any],
    traces: list[dict[str, Any]],
) -> bool:
    for tool_name in case["expected_tools"]:
        tool_traces = [trace for trace in traces if trace["tool_name"] == tool_name]
        if not tool_traces:
            return False
        rules = case["argument_rules"][tool_name]
        if any(
            not trace["success"]
            or not argument_matches(trace["arguments"], rules, trace["output"])
            for trace in tool_traces
        ):
            return False
        if len(tool_traces) < rules.get("minimum_calls", 1):
            return False
        required_families = set(rules.get("required_families_across_calls", []))
        observed_families = {
            family
            for trace in tool_traces
            for family in (trace["arguments"] or {}).get("families", [])
        }
        if not required_families.issubset(observed_families):
            return False
    return True


def evaluate_case(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    traces = run["tool_trace"]
    answer = run["answer"]
    called_names = [trace["tool_name"] for trace in traces]
    expected_tools = set(case["expected_tools"])
    allowed_tools = set(case["allowed_tools"])

    correct_tools_selected = expected_tools.issubset(set(called_names))
    correct_tool_arguments = tool_arguments_correct(case, traces)

    unnecessary_calls = []
    successful_names: set[str] = set()
    covered_policy_families: set[str] = set()
    required_policy_families = set(case["required_policy_families"])
    for trace in traces:
        if trace["tool_name"] not in allowed_tools:
            unnecessary_calls.append(trace["tool_name"])
        elif trace["tool_name"] == "search_knowledge_base" and trace["success"]:
            call_families = set((trace["arguments"] or {}).get("families", []))
            new_required_family = (
                call_families & required_policy_families
            ) - covered_policy_families
            if trace["tool_name"] in successful_names and not new_required_family:
                unnecessary_calls.append(trace["tool_name"])
            covered_policy_families.update(call_families & required_policy_families)
        elif trace["tool_name"] in successful_names:
            unnecessary_calls.append(trace["tool_name"])
        if trace["success"]:
            successful_names.add(trace["tool_name"])

    returned_scalars: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    retrieved_documents: dict[str, dict[str, str]] = {}
    for trace in traces:
        if not trace["success"] or trace["output"] is None:
            continue
        returned_scalars[trace["tool_name"]].extend(scalar_fields(trace["output"]))
        if trace["tool_name"] == "search_knowledge_base":
            for result in trace["output"].get("results", []):
                retrieved_documents[result["document_id"]] = {
                    "family": result["family"],
                    "excerpt": result["excerpt"],
                }

    answer_evidence = answer["evidence"]
    all_evidence_grounded = all(
        any(
            field == item["field"] and scalar_equal(value, item["value"])
            for field, value in returned_scalars.get(item["source_tool"], [])
        )
        for item in answer_evidence
    )
    required_evidence_present = all(
        any(
            item["source_tool"] == required["source_tool"]
            and item["field"] == required["field"]
            and scalar_equal(item["value"], required["value"])
            for item in answer_evidence
        )
        for required in case["required_evidence"]
    )

    cited_ids = answer["policy_document_ids"]
    all_policy_citations_retrieved = all(
        document_id in retrieved_documents for document_id in cited_ids
    )
    evidenced_policy_ids = {
        item["value"]
        for item in answer_evidence
        if item["source_tool"] == "search_knowledge_base"
        and item["field"].endswith(".document_id")
    }
    evidenced_policy_excerpts = Counter(
        item["value"]
        for item in answer_evidence
        if item["source_tool"] == "search_knowledge_base"
        and item["field"].endswith(".excerpt")
    )
    unique_cited_ids = list(dict.fromkeys(cited_ids))
    expected_policy_excerpts = Counter(
        retrieved_documents[document_id]["excerpt"]
        for document_id in unique_cited_ids
        if document_id in retrieved_documents
    )
    all_policy_citations_evidenced = (
        all(document_id in evidenced_policy_ids for document_id in unique_cited_ids)
        and all_policy_citations_retrieved
        and all(
            evidenced_policy_excerpts[excerpt] >= count
            for excerpt, count in expected_policy_excerpts.items()
        )
    )
    required_policy_families_cited = set(case["required_policy_families"]).issubset({
        retrieved_documents[document_id]["family"]
        for document_id in cited_ids
        if document_id in retrieved_documents
    })
    conclusion_correct = (
        answer["conclusion_code"] == case["expected_conclusion_code"]
        and answer["risk_level"] == case["expected_risk_level"]
    )
    summary_complete = (
        len(answer["summary"]) <= 300
        and answer["summary"].rstrip().endswith((".", "!", "?"))
    )
    task_completed = all((
        answer["task_status"] == "COMPLETED",
        correct_tools_selected,
        correct_tool_arguments,
        conclusion_correct,
        all_evidence_grounded,
        required_evidence_present,
        all_policy_citations_retrieved,
        all_policy_citations_evidenced,
        required_policy_families_cited,
        summary_complete,
    ))
    return {
        "correct_tools_selected": correct_tools_selected,
        "correct_tool_arguments": correct_tool_arguments,
        "unnecessary_tools_empty": not unnecessary_calls,
        "unnecessary_tool_calls": unnecessary_calls,
        "conclusion_correct": conclusion_correct,
        "summary_complete": summary_complete,
        "all_evidence_grounded": all_evidence_grounded,
        "required_evidence_present": required_evidence_present,
        "all_policy_citations_retrieved": all_policy_citations_retrieved,
        "all_policy_citations_evidenced": all_policy_citations_evidenced,
        "required_policy_families_cited": required_policy_families_cited,
        "task_completed": task_completed,
    }


def build_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [row for row in rows if row.get("api_success")]
    metric_names = (
        "correct_tools_selected",
        "correct_tool_arguments",
        "unnecessary_tools_empty",
        "conclusion_correct",
        "summary_complete",
        "all_evidence_grounded",
        "required_evidence_present",
        "all_policy_citations_retrieved",
        "all_policy_citations_evidenced",
        "required_policy_families_cited",
        "task_completed",
    )

    def metric_rates(group: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            f"{name}_rate_pct": pct(
                sum(bool(row.get("evaluation", {}).get(name)) for row in group),
                len(group),
            )
            for name in metric_names
        }

    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_type[row["case"]["task_type"]].append(row)
    policy_rows = [row for row in rows if row["case"]["required_policy_families"]]
    latency = [row["run"]["metrics"]["latency_seconds"] for row in successes]
    tool_calls = [row["run"]["metrics"]["tool_calls"] for row in successes]
    input_tokens = [row["run"]["metrics"]["input_tokens"] for row in successes]
    output_tokens = [row["run"]["metrics"]["output_tokens"] for row in successes]
    api_requests = [row["run"]["metrics"]["api_requests"] for row in successes]
    api_retry_attempts = [
        row["run"]["metrics"]["api_retry_attempts"] for row in successes
    ]
    costs = [
        row["run"]["metrics"]["estimated_cost_usd"]
        for row in successes
        if row["run"]["metrics"]["estimated_cost_usd"] is not None
    ]
    return {
        "cases": len(rows),
        "successful_agent_runs": len(successes),
        "api_success_rate_pct": pct(len(successes), len(rows)),
        **metric_rates(rows),
        "model": sorted({
            row["run"]["metrics"]["model"] for row in successes
        }),
        "prompt_version": sorted({
            row["run"]["metrics"]["prompt_version"] for row in successes
        }),
        "reasoning_effort": sorted({
            row["run"]["metrics"]["reasoning_effort"] for row in successes
        }),
        "latency_seconds": {
            "mean": mean(latency),
            "p50": percentile(latency, 0.50),
            "p95": percentile(latency, 0.95),
        },
        "tool_calls_per_task": {
            "mean": mean(tool_calls),
            "p95": percentile([float(value) for value in tool_calls], 0.95),
            "total": sum(tool_calls),
        },
        "api_execution": {
            "requests_total": sum(api_requests),
            "retry_attempts_total": sum(api_retry_attempts),
            "runs_without_retry_rate_pct": pct(
                sum(value == 0 for value in api_retry_attempts),
                len(api_retry_attempts),
            ),
        },
        "tokens": {
            "input_total": sum(input_tokens),
            "output_total": sum(output_tokens),
        },
        "estimated_cost_usd": {
            "total": round(sum(costs), 6) if costs else None,
            "mean_per_task": round(statistics.mean(costs), 8) if costs else None,
        },
        "by_task_type": {
            task_type: {"cases": len(group), **metric_rates(group)}
            for task_type, group in sorted(by_type.items())
        },
        "policy_tasks": {
            "cases": len(policy_rows),
            **{
                f"{name}_rate_pct": pct(
                    sum(
                        bool(row.get("evaluation", {}).get(name))
                        for row in policy_rows
                    ),
                    len(policy_rows),
                )
                for name in (
                    "all_policy_citations_retrieved",
                    "all_policy_citations_evidenced",
                    "required_policy_families_cited",
                    "task_completed",
                )
            },
        },
        "failures": [{
            "case_id": row["case"]["case_id"],
            "task_type": row["case"]["task_type"],
            "error_type": row.get("error_type"),
            "error": row.get("error"),
            "failed_metrics": [
                name for name in metric_names
                if not row.get("evaluation", {}).get(name)
            ],
            "called_tools": [
                trace["tool_name"]
                for trace in row.get("run", {}).get("tool_trace", [])
            ],
        } for row in rows if not row.get("evaluation", {}).get("task_completed")],
    }

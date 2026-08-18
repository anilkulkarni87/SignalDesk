#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from pydantic import ValidationError

from src.llm.customer_store import CustomerStore
from src.llm.policy_context import build_policy_context
from src.llm.policy_schemas import (
    ModelPolicyGroundedAssessment,
    model_assessment_schema,
    resolve_policy_assessment,
)
from src.llm.pricing import estimate_text_cost_usd
from src.llm.prompt_versions import v6
from src.llm.retry import with_exponential_backoff
from src.retrieval.embeddings import DEFAULT_EMBEDDING_MODEL, OpenAIEmbedder
from src.retrieval.query_planner import (
    VectorPolicyRetriever,
    plan_policy_queries,
)
from src.retrieval.vector_store import PgVectorStore


class IncompleteResponseError(RuntimeError):
    def __init__(self, response):
        self.response = response
        details = getattr(response, "incomplete_details", None)
        if hasattr(details, "model_dump"):
            details = details.model_dump()
        self.response_status = getattr(response, "status", None)
        self.incomplete_details = details
        super().__init__(
            f"OpenAI response status was {self.response_status}: {details}"
        )


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("evals/commit07/cases.jsonl"),
    )
    parser.add_argument("--dsn")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--embedding-dimensions", type=int)
    parser.add_argument("--per-query-top-k", type=int, default=3)
    parser.add_argument("--max-results", type=int, default=12)
    parser.add_argument("--max-context-characters", type=int, default=16_000)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument(
        "--reasoning-effort",
        default="none",
        choices=["none"],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/commit07/reports/results.jsonl"),
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--max-output-tokens", type=int, default=3_000)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--case-ids-file", type=Path)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def citation_is_grounded(citation, retrieved_by_id: dict) -> bool:
    result = retrieved_by_id.get(citation.document_id)
    if result is None:
        return False
    return normalize_text(citation.supporting_excerpt) in normalize_text(
        result.content
    )


def select_cases(
    frozen_cases: list[dict],
    *,
    case_ids: list[str],
    case_ids_file: Path | None,
    limit: int | None,
) -> list[dict]:
    selected_ids = list(case_ids)
    if case_ids_file:
        selected_ids.extend(
            line.strip()
            for line in case_ids_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )

    if selected_ids:
        selected = set(selected_ids)
        known = {case["case_id"] for case in frozen_cases}
        unknown = sorted(selected - known)
        if unknown:
            raise ValueError(f"Unknown case IDs: {', '.join(unknown)}")
        return [
            case for case in frozen_cases if case["case_id"] in selected
        ]

    return frozen_cases[:limit] if limit else frozen_cases


def main():
    args = parse_args()
    frozen_cases = read_jsonl(args.cases)
    if len(frozen_cases) != 100:
        raise ValueError(
            f"Expected 100 frozen RAG questions, found {len(frozen_cases)}"
        )
    cases = select_cases(
        frozen_cases,
        case_ids=args.case_id,
        case_ids_file=args.case_ids_file,
        limit=args.limit,
    )

    customer_store = CustomerStore(args.database)
    client = OpenAI(timeout=45.0, max_retries=0)
    retriever = VectorPolicyRetriever(
        embedder=OpenAIEmbedder(
            model=args.embedding_model,
            dimensions=args.embedding_dimensions,
        ),
        vector_store=PgVectorStore(args.dsn),
        per_query_top_k=args.per_query_top_k,
        max_results=args.max_results,
    )
    retryable_generation_errors = (
        RateLimitError,
        APITimeoutError,
        APIConnectionError,
        InternalServerError,
        IncompleteResponseError,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8") as output:
        for index, case in enumerate(cases, start=1):
            record = {
                "case": case,
                "prompt_version": v6.PROMPT_VERSION,
                "prompt_change_hypothesis": v6.PROMPT_CHANGE_HYPOTHESIS,
                "schema_valid": False,
                "citation_resolution_valid": False,
                "api_success": False,
                "api_attempts": 0,
            }
            case_started = time.perf_counter()

            try:
                snapshot = customer_store.get_snapshot(case["customer_id"])
                planned_queries = plan_policy_queries(snapshot)
                retrieval_started = time.perf_counter()
                retrieved = retriever.retrieve(snapshot)
                retrieval_latency = time.perf_counter() - retrieval_started
                context = build_policy_context(
                    retrieved,
                    planned_queries=planned_queries,
                    max_characters=args.max_context_characters,
                )
                schema = model_assessment_schema(context.intent_quote_ids)
                included = context.included_results
                retrieved_by_id = {
                    result.document_id: result for result in included
                }
                retrieved_doc_ids = set(retrieved_by_id)
                retrieved_families = {
                    result.family for result in included
                }
                record.update({
                    "snapshot": snapshot,
                    "planned_policy_queries": [
                        query.to_dict() for query in planned_queries
                    ],
                    "retrieved_policy_doc_ids": sorted(retrieved_doc_ids),
                    "retrieved_policy_results": [
                        result.to_dict() for result in included
                    ],
                    "context_character_count": context.character_count,
                    "context_quote_count": len(context.quotes_by_id),
                })

                snapshot_json = json.dumps(
                    snapshot,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
                generation_started = time.perf_counter()

                def generate():
                    response = client.responses.create(
                        model=args.model,
                        instructions=v6.SYSTEM_INSTRUCTIONS,
                        input=v6.build_user_input(
                            case["question"],
                            snapshot_json,
                            context.json_text,
                        ),
                        reasoning={"effort": args.reasoning_effort},
                        max_output_tokens=args.max_output_tokens,
                        text={
                            "format": {
                                "type": "json_schema",
                                "name": "policy_grounded_customer_assessment",
                                "description": (
                                    "Customer assessment grounded in Customer "
                                    "360 facts and deterministic policy quote "
                                    "identifiers."
                                ),
                                "schema": schema,
                                "strict": True,
                            }
                        },
                        store=False,
                        metadata={
                            "app": "signaldesk",
                            "prompt_version": v6.PROMPT_VERSION,
                            "commit": "07",
                        },
                    )
                    if getattr(response, "status", None) != "completed":
                        raise IncompleteResponseError(response)
                    return response

                response, api_attempts = with_exponential_backoff(
                    generate,
                    retryable_exceptions=retryable_generation_errors,
                    max_attempts=args.max_attempts,
                    base_delay_seconds=1.0,
                )
                generation_latency = time.perf_counter() - generation_started
                record.update({
                    "api_success": True,
                    "api_attempts": api_attempts,
                    "first_attempt_api_success": api_attempts == 1,
                    "response_status": response.status,
                })

                usage = response.usage
                input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
                output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
                total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
                input_details = getattr(usage, "input_tokens_details", None)
                output_details = getattr(usage, "output_tokens_details", None)
                cached_input_tokens = int(
                    getattr(input_details, "cached_tokens", 0) or 0
                )
                reasoning_tokens = int(
                    getattr(output_details, "reasoning_tokens", 0) or 0
                )
                record["metrics"] = {
                    "response_id": response.id,
                    "model": response.model,
                    "prompt_version": v6.PROMPT_VERSION,
                    "api_attempts": api_attempts,
                    "retrieval_latency_seconds": round(
                        retrieval_latency,
                        4,
                    ),
                    "generation_latency_seconds": round(
                        generation_latency,
                        4,
                    ),
                    "total_latency_seconds": round(
                        time.perf_counter() - case_started,
                        4,
                    ),
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "total_tokens": total_tokens,
                    "estimated_cost_usd": estimate_text_cost_usd(
                        args.model,
                        input_tokens,
                        cached_input_tokens,
                        output_tokens,
                    ),
                }

                record["raw_output_text"] = response.output_text
                model_assessment = (
                    ModelPolicyGroundedAssessment.model_validate_json(
                        response.output_text
                    )
                )
                record.update({
                    "schema_valid": True,
                    "assessment_draft": model_assessment.model_dump(),
                })
                assessment = resolve_policy_assessment(
                    model_assessment,
                    context.quotes_by_id,
                    context.intent_quote_ids,
                )
                record["citation_resolution_valid"] = True

                evidence_features = {
                    evidence.feature for evidence in assessment.evidence
                }
                required_all = set(case["required_evidence_all"])
                required_any = set(case["required_evidence_any"])
                required_all_present = required_all.issubset(evidence_features)
                required_any_present = (
                    True
                    if not required_any
                    else bool(required_any & evidence_features)
                )
                risk_correct = (
                    assessment.risk_level == case["expected_risk_level"]
                )

                expected_docs = set(case["expected_policy_doc_ids_all"])
                expected_families = set(
                    case["expected_policy_families_all"]
                )
                cited_doc_ids = {
                    source.document_id for source in assessment.policy_sources
                }
                cited_families = {
                    retrieved_by_id[document_id].family
                    for document_id in cited_doc_ids
                    if document_id in retrieved_by_id
                }
                citation_checks = [
                    citation_is_grounded(source, retrieved_by_id)
                    for source in assessment.policy_sources
                ]

                record.update({
                    "assessment": assessment.model_dump(),
                    "risk_correct": risk_correct,
                    "required_evidence_all_present": required_all_present,
                    "required_evidence_any_present": required_any_present,
                    "answer_correct": (
                        risk_correct
                        and required_all_present
                        and required_any_present
                    ),
                    "expected_policy_docs_retrieved": expected_docs.issubset(
                        retrieved_doc_ids
                    ),
                    "expected_policy_families_retrieved": (
                        expected_families.issubset(retrieved_families)
                    ),
                    "all_citations_retrieved": cited_doc_ids.issubset(
                        retrieved_doc_ids
                    ),
                    "all_citation_excerpts_grounded": all(citation_checks),
                    "citation_grounded_count": sum(citation_checks),
                    "citation_count": len(citation_checks),
                    "expected_policy_docs_cited": expected_docs.issubset(
                        cited_doc_ids
                    ),
                    "expected_policy_families_cited": (
                        expected_families.issubset(cited_families)
                    ),
                    "unsupported_policy_claims_empty": (
                        not assessment.unsupported_policy_claims
                    ),
                })
                record.pop("raw_output_text", None)
            except ValidationError as exc:
                record["error_type"] = type(exc).__name__
                record["error"] = str(exc)
            except Exception as exc:
                if isinstance(exc, retryable_generation_errors):
                    record["api_attempts"] = args.max_attempts
                    record["first_attempt_api_success"] = False
                if isinstance(exc, IncompleteResponseError):
                    record["response_status"] = exc.response_status
                    record["incomplete_details"] = exc.incomplete_details
                    record["raw_output_text"] = exc.response.output_text
                    usage = exc.response.usage
                    record["incomplete_output_tokens"] = int(
                        getattr(usage, "output_tokens", 0) or 0
                    )
                    output_details = getattr(
                        usage,
                        "output_tokens_details",
                        None,
                    )
                    record["incomplete_reasoning_tokens"] = int(
                        getattr(output_details, "reasoning_tokens", 0) or 0
                    )
                    record["incomplete_total_tokens"] = int(
                        getattr(usage, "total_tokens", 0) or 0
                    )
                record["error_type"] = type(exc).__name__
                record["error"] = str(exc)

            output.write(json.dumps(record, default=str) + "\n")
            output.flush()
            status = (
                "OK"
                if record.get("citation_resolution_valid")
                else "INVALID_OUTPUT"
                if record.get("api_success")
                else "API_ERROR"
            )
            print(
                f'[{index:03d}/{len(cases)}] {case["case_id"]}: '
                f'{status}'
            )
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    print(json.dumps({
        "cases": len(cases),
        "output": str(args.output),
        "prompt_version": v6.PROMPT_VERSION,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "embedding_model": args.embedding_model,
        "embedding_requests": retriever.embedding_requests,
        "embedding_input_tokens": retriever.embedding_input_tokens,
        "max_attempts": args.max_attempts,
        "max_output_tokens": args.max_output_tokens,
    }, indent=2))


if __name__ == "__main__":
    main()

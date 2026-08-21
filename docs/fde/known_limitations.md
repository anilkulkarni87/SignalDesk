# Known Limitations

## Learning scope

SignalDesk intentionally stops short of a production product. The limitations below are part of the deliverable because an FDE must make uncertainty and operational debt visible.

## Data and domain

- All customers, events, policies, labels, and actions are synthetic or generated.
- No real customer interviews, workflow observations, or policy-owner approvals were performed.
- The generated knowledge corpus does not establish legal or business correctness.
- The system has not been tested against real data quality, identity ambiguity, multilingual content, or regional policy variation.

## Evaluation

- Curated evaluation data was developed inside the same learning project as the implementation.
- Commit 05's first comparison contains ambiguous selectors and is repeatability evidence, not proof of prompt improvement.
- Most generative evaluations use one completed run per case and do not estimate variance or confidence intervals.
- Automated rubric success does not replace expert review or user testing.
- The p95 latency target below 8 seconds was not met in the main RAG and agent reports.
- Investigation time, analyst adoption, error cost, and business impact remain unmeasured.

## Retrieval and generation

- Vector retrieval performed best in the benchmark, but the accepted serving path remains lexical and current-approved.
- Retrieval benchmarks use curated relevance judgments and may not represent natural queries.
- Citation grounding confirms that excerpts came from retrieved text; it does not prove the source policy itself is correct.
- The model can still vary across repeated calls or provider updates.
- Cost and latency measurements are local snapshots, not capacity commitments.

## Agent and action behavior

- Tools are bounded to a small synthetic domain and do not represent a complete enterprise semantic layer.
- The action demo executes only a synthetic coupon event.
- A person supplies or reviews the action payload; the system does not prove autonomous action quality.
- Human approval demonstrates a control pattern, not enterprise separation of duties.
- The Agents SDK comparison is an experiment; the accepted workflow remains LangGraph.

## Security and compliance

- Local access-code authentication is not enterprise identity.
- There is no complete tenant model, row-level authorization, formal privacy review, or compliance certification.
- Local files and databases are not a managed, encrypted, backed-up production data plane.
- Prompt injection and data exfiltration have not been comprehensively red-teamed.
- Audit retention, legal hold, deletion, and regulator access processes are not implemented.

## Reliability and operations

- Deployment is local or single-host containerized; there is no high availability or disaster recovery proof.
- Observability is a local learning dashboard, not centralized tracing, paging, or SLO management.
- The liveness smoke test does not exercise retrieval, tools, or model generation.
- Failure injection covers known boundaries, not every dependency, concurrency pattern, or partial outage.
- No sustained end-to-end load test establishes model-backed capacity.

## Product and adoption

- The UI demonstrates a workflow but has not undergone accessibility, usability, or analyst productivity studies.
- No integration with a real CDP, CRM, case-management system, identity provider, or policy repository exists.
- There is no production ownership model, support process, rollout plan, or training program.
- The fictional ROI model must not be used as a business case without real measurements.

These limits do not erase the learning evidence. They define what the next experiment must establish.


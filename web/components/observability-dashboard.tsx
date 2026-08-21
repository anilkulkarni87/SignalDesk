"use client";

import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Database,
  FileCheck2,
  Gauge,
  LoaderCircle,
  RefreshCw,
  SearchCheck,
  Wrench,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { APIError, api } from "@/lib/api";
import type {
  ObservabilitySummary,
  RunObservation,
  Session,
} from "@/lib/types";

function errorMessage(error: unknown): string {
  if (error instanceof APIError || error instanceof Error) return error.message;
  return "The observability request could not be completed.";
}

function formatCost(value: number | null): string {
  if (value === null) return "Not recorded";
  return `$${value.toFixed(4)}`;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function SummaryMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Gauge;
  label: string;
  value: string;
}) {
  return (
    <div className="observation-metric">
      <span><Icon size={15} />{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RunDetail({
  run,
  session,
  onUpdated,
}: {
  run: RunObservation;
  session: Session;
  onUpdated: (run: RunObservation) => void;
}) {
  const [note, setNote] = useState(run.evaluation_note ?? "");
  const [submitting, setSubmitting] = useState<"PASS" | "FAIL" | null>(null);
  const [error, setError] = useState("");

  async function evaluate(result: "PASS" | "FAIL") {
    setSubmitting(result);
    setError("");
    try {
      onUpdated(await api.evaluateRun(run.request_id, result, note, session.csrf_token));
    } catch (evaluationError) {
      setError(errorMessage(evaluationError));
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <aside className="run-detail" aria-label="Selected run details">
      <header className="run-detail-header">
        <div>
          <span className="section-label">Run detail</span>
          <code>{run.request_id}</code>
        </div>
        <span className={`run-status ${run.status.toLowerCase()}`}>
          {run.status === "SUCCESS" ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
          {run.status}
        </span>
      </header>

      <div className="run-detail-scroll">
        <section className="run-facts">
          <div><span>Customer</span><strong>{run.customer_id}</strong></div>
          <div><span>Started</span><strong>{formatDate(run.started_at)}</strong></div>
          <div><span>Model</span><strong>{run.model}</strong></div>
          <div><span>Prompt</span><code>{run.prompt_version}</code></div>
          <div><span>Latency</span><strong>{run.latency_seconds.toFixed(2)}s</strong></div>
          <div><span>Cost</span><strong>{formatCost(run.cost_usd)}</strong></div>
        </section>

        <section className="run-section">
          <div className="run-section-title"><span>Token usage</span><strong>{run.tokens.total.toLocaleString()}</strong></div>
          <div className="token-strip">
            <span>Input <strong>{run.tokens.input.toLocaleString()}</strong></span>
            <span>Cached <strong>{run.tokens.cached_input.toLocaleString()}</strong></span>
            <span>Output <strong>{run.tokens.output.toLocaleString()}</strong></span>
            <span>Reasoning <strong>{run.tokens.reasoning.toLocaleString()}</strong></span>
          </div>
        </section>

        <section className="run-section">
          <div className="run-section-title"><span>Final answer</span><strong>{run.final_answer?.task_status ?? "Unavailable"}</strong></div>
          {run.final_answer ? (
            <div className="observed-answer">
              <div>
                <span className={`risk risk-${String(run.final_answer.risk_level ?? "not-assessed").toLowerCase()}`}>
                  {String(run.final_answer.risk_level ?? "Not assessed")}
                </span>
                <strong>{String(run.final_answer.conclusion_code ?? "No conclusion")}</strong>
              </div>
              <p>{String(run.final_answer.summary ?? "No summary recorded.")}</p>
            </div>
          ) : <p className="empty-copy compact">No final answer was produced.</p>}
        </section>

        <section className="run-section">
          <div className="run-section-title"><span>Tool calls</span><strong>{run.tool_calls.length}</strong></div>
          <div className="observed-tools">
            {run.tool_calls.map((tool, index) => (
              <div key={`${tool.tool_name}-${index}`}>
                <span className={tool.success ? "success-text" : "failure-text"}>
                  {tool.success ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                </span>
                <code>{tool.tool_name}</code>
                <span>{tool.latency_ms.toFixed(1)}ms</span>
              </div>
            ))}
            {run.tool_calls.length === 0 && <p className="empty-copy compact">No tool calls recorded.</p>}
          </div>
        </section>

        <section className="run-section">
          <div className="run-section-title"><span>Retrieval</span><strong>{run.retrieval_documents.length}</strong></div>
          <div className="retrieval-observations">
            {run.retrieval_documents.map((documentId, index) => (
              <div key={`${documentId}-${index}`}><code>{documentId}</code><span>{run.retrieval_scores[index].toFixed(3)}</span></div>
            ))}
            {run.retrieval_documents.length === 0 && <p className="empty-copy compact">No policy documents recorded.</p>}
          </div>
        </section>

        {run.errors.length > 0 && (
          <section className="run-section observed-errors">
            <div className="run-section-title"><span>Errors</span><strong>{run.errors.length}</strong></div>
            {run.errors.map((item, index) => (
              <div key={`${item.stage}-${index}`}><AlertTriangle size={14} /><p><strong>{item.error_type}</strong>{item.message}</p></div>
            ))}
          </section>
        )}

        <section className="run-section evaluation-section">
          <div className="run-section-title"><span>Human evaluation</span><strong>{run.evaluation_result.replaceAll("_", " ")}</strong></div>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Record why this answer passes or fails"
            aria-label="Evaluation note"
            minLength={3}
            maxLength={500}
          />
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="evaluation-actions">
            <button className="danger-button" disabled={note.trim().length < 3 || submitting !== null} onClick={() => evaluate("FAIL")}>
              {submitting === "FAIL" ? <LoaderCircle className="spin" size={15} /> : <XCircle size={15} />}Fail
            </button>
            <button className="primary-button" disabled={note.trim().length < 3 || submitting !== null} onClick={() => evaluate("PASS")}>
              {submitting === "PASS" ? <LoaderCircle className="spin" size={15} /> : <FileCheck2 size={15} />}Pass
            </button>
          </div>
        </section>
      </div>
    </aside>
  );
}

export function ObservabilityDashboard({ session }: { session: Session }) {
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null);
  const [runs, setRuns] = useState<RunObservation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [nextSummary, nextRuns] = await Promise.all([
        api.observabilitySummary(),
        api.observabilityRuns(),
      ]);
      setSummary(nextSummary);
      setRuns(nextRuns.runs);
      setSelectedId((current) => current ?? nextRuns.runs[0]?.request_id ?? null);
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.observabilitySummary(), api.observabilityRuns()])
      .then(([nextSummary, nextRuns]) => {
        if (cancelled) return;
        setSummary(nextSummary);
        setRuns(nextRuns.runs);
        setSelectedId(nextRuns.runs[0]?.request_id ?? null);
      })
      .catch((loadError) => {
        if (!cancelled) setError(errorMessage(loadError));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedRun = useMemo(
    () => runs.find((run) => run.request_id === selectedId) ?? null,
    [runs, selectedId],
  );

  function updateRun(updated: RunObservation) {
    setRuns((current) => current.map((run) => run.request_id === updated.request_id ? updated : run));
    void api.observabilitySummary().then(setSummary).catch((summaryError) => setError(errorMessage(summaryError)));
  }

  return (
    <section className="observability-shell">
      <header className="observability-heading">
        <div><span className="section-label">Operations</span><h1>Agent observability</h1></div>
        <button className="secondary-button" onClick={() => void load()} disabled={loading}>
          {loading ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}Refresh
        </button>
      </header>

      {summary && (
        <section className="observation-metrics" aria-label="Agent run metrics">
          <SummaryMetric icon={Gauge} label="Task success" value={`${summary.task_success_rate_pct.toFixed(1)}%`} />
          <SummaryMetric icon={Clock3} label="P50 latency" value={`${summary.latency_seconds.p50.toFixed(2)}s`} />
          <SummaryMetric icon={Clock3} label="P95 latency" value={`${summary.latency_seconds.p95.toFixed(2)}s`} />
          <SummaryMetric icon={Database} label="Tokens / task" value={summary.tokens_per_task.toLocaleString()} />
          <SummaryMetric icon={CircleDollarSign} label="Cost / task" value={formatCost(summary.cost_per_task_usd)} />
          <SummaryMetric icon={Wrench} label="Tool failures" value={`${summary.tool_failure_rate_pct.toFixed(1)}%`} />
          <SummaryMetric icon={SearchCheck} label="Retrieval failures" value={`${summary.retrieval_failure_rate_pct.toFixed(1)}%`} />
        </section>
      )}

      {error && <div className="dashboard-error" role="alert"><AlertTriangle size={16} />{error}</div>}

      <div className="observability-content">
        <section className="run-ledger" aria-label="Recent agent runs">
          <div className="ledger-heading">
            <div><span className="section-label">Recent runs</span><strong>{runs.length} recorded</strong></div>
            {summary && <span>{summary.error_runs} errors · {summary.evaluated_runs} evaluated</span>}
          </div>
          <div className="run-table-wrap">
            <table className="run-table">
              <thead><tr><th>Status</th><th>Customer</th><th>Conclusion</th><th>Latency</th><th>Tokens</th><th>Cost</th><th>Evaluation</th><th aria-label="Open" /></tr></thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.request_id} className={run.request_id === selectedId ? "selected" : ""} onClick={() => setSelectedId(run.request_id)}>
                    <td><span className={`run-dot ${run.status.toLowerCase()}`} />{run.status}</td>
                    <td><strong>{run.customer_id}</strong><small>{formatDate(run.started_at)}</small></td>
                    <td>{String(run.final_answer?.conclusion_code ?? run.errors[0]?.error_type ?? "No answer").replaceAll("_", " ")}</td>
                    <td>{run.latency_seconds.toFixed(2)}s</td>
                    <td>{run.tokens.total.toLocaleString()}</td>
                    <td>{formatCost(run.cost_usd)}</td>
                    <td><span className={`evaluation-badge ${run.evaluation_result.toLowerCase()}`}>{run.evaluation_result.replaceAll("_", " ")}</span></td>
                    <td><button className="icon-button" onClick={() => setSelectedId(run.request_id)} title="Open run" aria-label={`Open run ${run.request_id}`}><ChevronRight size={15} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && runs.length === 0 && <div className="ledger-empty"><Database size={24} /><strong>No agent runs recorded</strong></div>}
          </div>
        </section>
        {selectedRun ? <RunDetail key={selectedRun.request_id} run={selectedRun} session={session} onUpdated={updateRun} /> : <aside className="run-detail empty"><Database size={24} /><strong>Select a run</strong></aside>}
      </div>
    </section>
  );
}

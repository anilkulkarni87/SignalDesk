"use client";

import {
  AlertTriangle,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Database,
  FileCheck2,
  LoaderCircle,
  LogOut,
  Play,
  Search,
  Send,
  ShieldCheck,
  UserRound,
  Workflow,
  Wrench,
  X,
  XCircle,
} from "lucide-react";
import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { APIError, api } from "@/lib/api";
import type {
  ActionPackage,
  Customer360,
  CustomerSearchItem,
  Investigation,
  Session,
} from "@/lib/types";

const DEFAULT_QUESTION =
  "Investigate this customer's current warning signals, explain the strongest evidence, and identify the next analyst review step.";

type DetailTab = "evidence" | "sources" | "tools" | "timeline";

function errorMessage(error: unknown): string {
  if (error instanceof APIError || error instanceof Error) return error.message;
  return "The request could not be completed.";
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "Not available";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(value).replaceAll("_", " ");
}

function riskClass(risk: string | undefined): string {
  return `risk risk-${(risk ?? "not-assessed").toLowerCase().replaceAll("_", "-")}`;
}

function WarningMarks({ customer }: { customer: CustomerSearchItem }) {
  return (
    <span className="warning-marks" aria-label={`${customer.warning_count} warnings`}>
      <span className={customer.purchase_decline_flag ? "mark active" : "mark"} />
      <span className={customer.engagement_decline_flag ? "mark active" : "mark"} />
      <span className={customer.support_attention_flag ? "mark active" : "mark"} />
    </span>
  );
}

function LoginView({ onLogin }: { onLogin: (session: Session) => void }) {
  const [reviewerId, setReviewerId] = useState("local-analyst");
  const [accessCode, setAccessCode] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      onLogin(await api.login(accessCode, reviewerId));
    } catch (loginError) {
      setError(errorMessage(loginError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="brand-lockup large">
          <span className="brand-mark"><Database size={20} /></span>
          <span>SignalDesk</span>
        </div>
        <div className="login-heading">
          <p className="eyebrow">Analyst workspace</p>
          <h1 id="login-title">Access customer intelligence</h1>
        </div>
        <form onSubmit={submit} className="login-form">
          <label>
            Reviewer ID
            <input
              value={reviewerId}
              onChange={(event) => setReviewerId(event.target.value)}
              autoComplete="username"
              minLength={3}
              required
            />
          </label>
          <label>
            Workspace access code
            <input
              type="password"
              value={accessCode}
              onChange={(event) => setAccessCode(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button full" disabled={submitting}>
            {submitting ? <LoaderCircle className="spin" size={16} /> : <ShieldCheck size={16} />}
            Sign in
          </button>
        </form>
      </section>
    </main>
  );
}

function MetricCell({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="metric-cell">
      <span>{label}</span>
      <strong>{formatValue(value)}</strong>
    </div>
  );
}

function ApprovalDialog({
  action,
  csrf,
  onChange,
  onClose,
}: {
  action: ActionPackage;
  csrf: string;
  onChange: (value: ActionPackage) => void;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<"APPROVED" | "REJECTED" | null>(null);
  const [error, setError] = useState("");
  const completed = action.run.status !== "PENDING_APPROVAL";

  async function decide(decision: "APPROVED" | "REJECTED") {
    setPending(decision);
    setError("");
    try {
      onChange(await api.decideAction(action.proposal.action_id, decision, reason, csrf));
    } catch (decisionError) {
      setError(errorMessage(decisionError));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="approval-dialog" role="dialog" aria-modal="true" aria-labelledby="approval-title">
        <header className="dialog-header">
          <div>
            <p className="eyebrow">Human authorization</p>
            <h2 id="approval-title">
              {completed ? "Decision recorded" : "Review exact action payload"}
            </h2>
          </div>
          <button className="icon-button" onClick={onClose} title="Close approval dialog" aria-label="Close approval dialog">
            <X size={18} />
          </button>
        </header>
        <div className="approval-body">
          <div className="approval-meta">
            <span>Action ID</span><code>{action.proposal.action_id}</code>
            <span>Customer</span><strong>{action.proposal.customer_id}</strong>
          </div>
          <div className="review-block">
            <span>Recommendation</span>
            <p>{action.proposal.recommendation}</p>
          </div>
          <div className="review-block">
            <span>Expected impact</span>
            <p>{action.proposal.expected_impact}</p>
          </div>
          <div className="payload-block">
            <span>Exact payload</span>
            <pre>{JSON.stringify(action.proposal.action, null, 2)}</pre>
          </div>
          {completed ? (
            <div className={`decision-result ${action.run.status.toLowerCase()}`}>
              {action.run.status === "EXECUTED" ? <CheckCircle2 size={20} /> : <XCircle size={20} />}
              <div>
                <strong>{action.run.status}</strong>
                <p>{action.run.decision?.reason}</p>
              </div>
            </div>
          ) : (
            <label className="decision-reason">
              Decision reason
              <textarea
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Record the evidence behind this decision"
                minLength={3}
                maxLength={500}
              />
            </label>
          )}
          {error && <p className="form-error" role="alert">{error}</p>}
        </div>
        <footer className="dialog-footer">
          {completed ? (
            <button className="secondary-button" onClick={onClose}>Done</button>
          ) : (
            <>
              <button
                className="danger-button"
                disabled={reason.trim().length < 3 || pending !== null}
                onClick={() => decide("REJECTED")}
              >
                {pending === "REJECTED" ? <LoaderCircle className="spin" size={16} /> : <XCircle size={16} />}
                Reject
              </button>
              <button
                className="primary-button"
                disabled={reason.trim().length < 3 || pending !== null}
                onClick={() => decide("APPROVED")}
              >
                {pending === "APPROVED" ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}
                Approve exact payload
              </button>
            </>
          )}
        </footer>
      </section>
    </div>
  );
}

export function Workspace() {
  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [customers, setCustomers] = useState<CustomerSearchItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [customer, setCustomer] = useState<Customer360 | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [detailTab, setDetailTab] = useState<DetailTab>("evidence");
  const [loadingCustomers, setLoadingCustomers] = useState(false);
  const [loadingCustomer, setLoadingCustomer] = useState(false);
  const [investigating, setInvestigating] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [action, setAction] = useState<ActionPackage | null>(null);
  const [error, setError] = useState("");
  const selectedIdRef = useRef<string | null>(null);
  const customerRequestRef = useRef(0);

  const selectCustomer = useCallback(async (customerId: string) => {
    const requestId = ++customerRequestRef.current;
    selectedIdRef.current = customerId;
    setSelectedId(customerId);
    setLoadingCustomer(true);
    setError("");
    setInvestigation(null);
    setAction(null);
    try {
      const result = await api.customer360(customerId);
      if (requestId === customerRequestRef.current) setCustomer(result);
    } catch (customerError) {
      if (requestId === customerRequestRef.current) {
        setError(errorMessage(customerError));
      }
    } finally {
      if (requestId === customerRequestRef.current) setLoadingCustomer(false);
    }
  }, []);

  useEffect(() => {
    api.session().then(setSession).catch(() => setSession(null)).finally(() => setAuthLoading(false));
  }, []);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(async () => {
      setLoadingCustomers(true);
      try {
        const result = await api.searchCustomers(query);
        setCustomers(result.customers);
        const firstCustomerId = result.customers[0]?.customer_id;
        if (!selectedIdRef.current && firstCustomerId) {
          void selectCustomer(firstCustomerId);
        }
      } catch (searchError) {
        setError(errorMessage(searchError));
      } finally {
        setLoadingCustomers(false);
      }
    }, 180);
    return () => window.clearTimeout(timer);
  }, [query, selectCustomer, session]);

  const selectedListItem = useMemo(
    () => customers.find((item) => item.customer_id === selectedId),
    [customers, selectedId],
  );

  async function logout() {
    if (!session) return;
    await api.logout(session.csrf_token).catch(() => undefined);
    setSession(null);
  }

  async function runInvestigation() {
    if (!selectedId || !session || question.trim().length < 10) return;
    setInvestigating(true);
    setError("");
    try {
      const result = await api.investigate(selectedId, question, session.csrf_token);
      setInvestigation(result);
      setDetailTab("evidence");
    } catch (investigationError) {
      setError(errorMessage(investigationError));
    } finally {
      setInvestigating(false);
    }
  }

  async function draftAction() {
    if (!investigation || !session) return;
    setDrafting(true);
    setError("");
    try {
      const result = await api.draftSupportAction(
        investigation.investigation_id,
        "Create a reviewed synthetic support follow-up from this investigation.",
        session.csrf_token,
      );
      setAction(result);
    } catch (draftError) {
      setError(errorMessage(draftError));
    } finally {
      setDrafting(false);
    }
  }

  if (authLoading) {
    return <main className="loading-screen"><LoaderCircle className="spin" size={24} /></main>;
  }
  if (!session) return <LoginView onLogin={setSession} />;

  const purchase = customer?.metrics.purchase ?? {};
  const engagement = customer?.metrics.engagement ?? {};
  const support = customer?.metrics.support ?? {};

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark"><Database size={17} /></span>
          <span>SignalDesk</span>
          <span className="environment-label">Learning</span>
        </div>
        <div className="topbar-actions">
          <span className="connection"><span /> API connected</span>
          <span className="reviewer"><UserRound size={15} />{session.reviewer_id}</span>
          <button className="icon-button" onClick={logout} title="Sign out" aria-label="Sign out">
            <LogOut size={17} />
          </button>
        </div>
      </header>

      <div className="workspace-grid">
        <aside className="customer-rail">
          <div className="rail-heading">
            <div><span className="section-label">Customer queue</span><strong>{customers.length} shown</strong></div>
            {loadingCustomers && <LoaderCircle className="spin" size={15} />}
          </div>
          <label className="search-box">
            <Search size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search ID, tier, country"
              aria-label="Search customers"
            />
            {query && (
              <button onClick={() => setQuery("")} title="Clear search" aria-label="Clear search"><X size={14} /></button>
            )}
          </label>
          <div className="customer-list">
            {customers.map((item) => (
              <button
                key={item.customer_id}
                className={selectedId === item.customer_id ? "customer-row selected" : "customer-row"}
                onClick={() => void selectCustomer(item.customer_id)}
              >
                <div className="customer-row-main">
                  <strong>{item.customer_id}</strong>
                  <WarningMarks customer={item} />
                </div>
                <div className="customer-row-meta">
                  <span>{item.loyalty_tier}</span>
                  <span>{item.country}</span>
                  <span>{item.days_since_last_seen}d idle</span>
                </div>
                <ChevronRight size={15} />
              </button>
            ))}
            {!loadingCustomers && customers.length === 0 && <p className="empty-copy">No customers match this search.</p>}
          </div>
        </aside>

        <section className="primary-workspace">
          {selectedId ? (
            <>
              <header className="customer-header">
                <div>
                  <div className="customer-title-line">
                    <h1>{selectedId}</h1>
                    <span className={riskClass(investigation?.risk_level)}>
                      {investigation?.risk_level ?? `${customer?.warning_count ?? selectedListItem?.warning_count ?? 0} warnings`}
                    </span>
                  </div>
                  <p>
                    {customer?.profile.loyalty_tier ?? selectedListItem?.loyalty_tier} · {customer?.profile.country ?? selectedListItem?.country} · {customer?.profile.customer_status ?? selectedListItem?.customer_status}
                  </p>
                </div>
                <div className="as-of">
                  <Clock3 size={15} />
                  <span>As of</span>
                  <strong>{customer ? new Date(String(customer.profile.as_of_ts)).toLocaleString() : "Loading"}</strong>
                </div>
              </header>

              <section className="metrics-band" aria-label="Customer 360 metrics">
                <MetricCell label="Lifetime value" value={purchase.lifetime_value ? `$${formatValue(purchase.lifetime_value)}` : purchase.lifetime_value} />
                <MetricCell label="Orders, 60d" value={purchase.orders_60d} />
                <MetricCell label="Purchase change" value={purchase.purchase_change_pct === null ? null : `${formatValue(purchase.purchase_change_pct)}%`} />
                <MetricCell label="Sessions, 60d" value={engagement.sessions_60d} />
                <MetricCell label="Open support" value={support.open_support_cases} />
                <MetricCell label="Campaign status" value={customer?.campaign_eligibility.status} />
              </section>

              <section className="conversation" aria-label="Investigation conversation">
                <div className="conversation-heading">
                  <div><span className="section-label">Investigation</span><strong>{investigation ? investigation.investigation_id : "New analysis"}</strong></div>
                  {investigation && (
                    <div className="run-metrics">
                      <span>{investigation.metrics.tool_calls} tools</span>
                      <span>{investigation.metrics.latency_seconds.toFixed(1)}s</span>
                      <span>{investigation.metrics.total_tokens.toLocaleString()} tokens</span>
                    </div>
                  )}
                </div>
                <div className="messages">
                  {investigation ? (
                    <>
                      <article className="message user-message">
                        <span className="message-icon"><UserRound size={15} /></span>
                        <div><span>Analyst</span><p>{investigation.question}</p></div>
                      </article>
                      <article className="message assistant-message">
                        <span className="message-icon"><Database size={15} /></span>
                        <div>
                          <div className="answer-heading">
                            <span>SignalDesk</span>
                            <strong>{investigation.conclusion_code.replaceAll("_", " ")}</strong>
                          </div>
                          <p>{investigation.summary}</p>
                          {investigation.limitations.length > 0 && (
                            <div className="limitations"><AlertTriangle size={15} />{investigation.limitations.join(" ")}</div>
                          )}
                        </div>
                      </article>
                    </>
                  ) : (
                    <div className="conversation-empty">
                      {loadingCustomer ? <LoaderCircle className="spin" size={22} /> : <Workflow size={24} />}
                      <strong>{loadingCustomer ? "Loading customer context" : "Ready for investigation"}</strong>
                    </div>
                  )}
                </div>
                <div className="composer">
                  <textarea
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    aria-label="Investigation question"
                    maxLength={1000}
                  />
                  <button
                    className="primary-button composer-action"
                    onClick={runInvestigation}
                    disabled={investigating || !customer || question.trim().length < 10}
                  >
                    {investigating ? <LoaderCircle className="spin" size={16} /> : investigation ? <Send size={16} /> : <Play size={16} />}
                    {investigating ? "Investigating" : investigation ? "Run again" : "Run investigation"}
                  </button>
                </div>
              </section>

              {investigation && (
                <section className="action-band">
                  <div>
                    <FileCheck2 size={18} />
                    <div><strong>Synthetic support follow-up</strong><span>Requires exact-payload human approval</span></div>
                  </div>
                  <button className="secondary-button" onClick={draftAction} disabled={drafting}>
                    {drafting ? <LoaderCircle className="spin" size={16} /> : <ShieldCheck size={16} />}
                    Review action
                  </button>
                </section>
              )}
            </>
          ) : (
            <div className="primary-empty"><Database size={28} /><strong>Select a customer</strong></div>
          )}
          {error && <div className="global-error" role="alert"><AlertTriangle size={16} />{error}<button onClick={() => setError("")}><X size={14} /></button></div>}
        </section>

        <aside className="detail-rail">
          <nav className="detail-tabs" aria-label="Investigation details">
            {([
              ["evidence", "Evidence", Database],
              ["sources", "Sources", BookOpen],
              ["tools", "Tools", Wrench],
              ["timeline", "Timeline", Workflow],
            ] as const).map(([id, label, Icon]) => (
              <button key={id} className={detailTab === id ? "active" : ""} onClick={() => setDetailTab(id)} title={label} aria-label={label}>
                <Icon size={16} /><span>{label}</span>
              </button>
            ))}
          </nav>
          <div className="detail-content">
            {!investigation ? (
              <div className="detail-empty"><Database size={22} /><p>Investigation details will appear here.</p></div>
            ) : detailTab === "evidence" ? (
              <div className="detail-list">
                <div className="detail-title"><span>Grounded evidence</span><strong>{investigation.evidence.length}</strong></div>
                {investigation.evidence.map((item, index) => (
                  <article className="evidence-item" key={`${item.field}-${index}`}>
                    <div><code>{item.field}</code><strong>{formatValue(item.value)}</strong></div>
                    <p>{item.interpretation}</p>
                    <span>{item.source_tool.replaceAll("_", " ")}</span>
                  </article>
                ))}
              </div>
            ) : detailTab === "sources" ? (
              <div className="detail-list">
                <div className="detail-title"><span>Policy sources</span><strong>{investigation.sources.length}</strong></div>
                {investigation.sources.length === 0 ? <p className="empty-copy">No policy source was needed.</p> : investigation.sources.map((source) => (
                  <article className="source-item" key={source.document_id}>
                    <div><code>{source.document_id}</code>{source.cited && <span className="cited"><Check size={12} />Cited</span>}</div>
                    <strong>{source.title}</strong>
                    <p>{source.excerpt}</p>
                    <span>{source.family} · score {source.score.toFixed(3)}</span>
                  </article>
                ))}
              </div>
            ) : detailTab === "tools" ? (
              <div className="detail-list">
                <div className="detail-title"><span>Executed tools</span><strong>{investigation.tools.length}</strong></div>
                {investigation.tools.map((tool, index) => (
                  <article className="tool-item" key={`${tool.tool_name}-${index}`}>
                    <div><span className={tool.success ? "tool-status success" : "tool-status failure"}>{tool.success ? <CheckCircle2 size={14} /> : <XCircle size={14} />}</span><code>{tool.tool_name}</code><span>{tool.latency_ms.toFixed(1)}ms</span></div>
                    <p>{tool.result_summary}</p>
                  </article>
                ))}
              </div>
            ) : (
              <div className="timeline-list">
                <div className="detail-title"><span>Agent timeline</span><strong>{investigation.timeline.length}</strong></div>
                {investigation.timeline.map((step, index) => (
                  <div className="timeline-step" key={`${step}-${index}`}>
                    <span>{index + 1}</span><div><strong>{step.replaceAll("_", " ")}</strong><small>{step === "finish" ? "Completed" : "Checkpoint recorded"}</small></div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>
      {action && <ApprovalDialog action={action} csrf={session.csrf_token} onChange={setAction} onClose={() => setAction(null)} />}
    </main>
  );
}

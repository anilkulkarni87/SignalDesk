export type Session = {
  user_id: string;
  reviewer_id: string;
  csrf_token: string;
  expires_at: number;
};

export type CustomerSearchItem = {
  customer_id: string;
  customer_status: string;
  loyalty_tier: string;
  country: string;
  days_since_last_seen: number;
  warning_count: number;
  purchase_decline_flag: boolean;
  engagement_decline_flag: boolean;
  support_attention_flag: boolean;
};

export type CustomerSearch = {
  query: string;
  returned_count: number;
  customers: CustomerSearchItem[];
};

export type Customer360 = {
  customer_id: string;
  profile: Record<string, string | number | boolean | null>;
  metrics: {
    purchase: Record<string, unknown>;
    engagement: Record<string, unknown>;
    support: Record<string, unknown>;
    campaigns: Record<string, unknown>;
    subscriptions_and_consent: Record<string, unknown>;
    [key: string]: unknown;
  };
  campaign_eligibility: {
    status: "BLOCKED" | "REVIEW_REQUIRED";
    channel_results: Array<{
      channel: string;
      consented: boolean;
      status: string;
      reasons: string[];
    }>;
    limitations: string[];
  };
  warning_count: number;
};

export type Evidence = {
  source_tool: string;
  field: string;
  value: string | number | boolean | null;
  interpretation: string;
};

export type Investigation = {
  request_id: string;
  investigation_id: string;
  customer_id: string;
  question: string;
  task_status: string;
  conclusion_code: string;
  risk_level: string;
  summary: string;
  evidence: Evidence[];
  limitations: string[];
  policy_document_ids: string[];
  tools: Array<{
    round_number: number;
    tool_name: string;
    arguments: Record<string, unknown> | null;
    success: boolean;
    error_code: string | null;
    latency_ms: number;
    result_summary: string;
  }>;
  sources: Array<{
    document_id: string;
    title: string;
    family: string;
    excerpt: string;
    score: number;
    cited: boolean;
  }>;
  timeline: string[];
  metrics: {
    model: string;
    prompt_version: string;
    reasoning_effort: "none";
    tool_calls: number;
    model_rounds: number;
    latency_seconds: number;
    total_tokens: number;
    estimated_cost_usd: number | null;
  };
  created_at: string;
};

export type ObservedToolCall = {
  round_number: number;
  tool_name: string;
  success: boolean;
  error_code: string | null;
  latency_ms: number;
  returned_count: number | null;
};

export type RunObservation = {
  request_id: string;
  investigation_id: string | null;
  user_id: string;
  customer_id: string;
  question: string;
  status: "SUCCESS" | "ERROR";
  task_success: boolean;
  model: string;
  prompt_version: string;
  reasoning_effort: "none";
  tool_calls: ObservedToolCall[];
  retrieval_documents: string[];
  retrieval_scores: number[];
  tokens: {
    input: number;
    cached_input: number;
    output: number;
    reasoning: number;
    total: number;
  };
  cost_usd: number | null;
  latency_seconds: number;
  final_answer: {
    task_status?: string;
    conclusion_code?: string;
    risk_level?: string;
    summary?: string;
    [key: string]: unknown;
  } | null;
  evaluation_result: "NOT_EVALUATED" | "PASS" | "FAIL";
  evaluation_note: string | null;
  errors: Array<{
    stage: string;
    error_type: string;
    message: string;
  }>;
  started_at: string;
  completed_at: string;
};

export type ObservabilitySummary = {
  total_runs: number;
  successful_runs: number;
  error_runs: number;
  task_success_rate_pct: number;
  latency_seconds: { p50: number; p95: number };
  tokens_per_task: number;
  cost_per_task_usd: number;
  tool_failure_rate_pct: number;
  retrieval_failure_rate_pct: number;
  evaluated_runs: number;
  evaluation_pass_rate_pct: number | null;
};

export type ActionPackage = {
  investigation_id: string;
  proposal: {
    action_id: string;
    customer_id: string;
    action: Record<string, unknown>;
    recommendation: string;
    reason: string;
    expected_impact: string;
    source_case_id: string;
    proposed_by: string;
  };
  run: {
    status: "PENDING_APPROVAL" | "REJECTED" | "EXECUTED";
    synthetic_event_id: string | null;
    approval_request: {
      action: Record<string, unknown>;
    } | null;
    decision: {
      decision: "APPROVED" | "REJECTED";
      reviewer_id: string;
      reason: string;
    } | null;
    transitions: string[];
  };
};

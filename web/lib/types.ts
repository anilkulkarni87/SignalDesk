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

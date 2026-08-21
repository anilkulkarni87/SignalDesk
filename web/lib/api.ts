import type {
  ActionPackage,
  Customer360,
  CustomerSearch,
  Investigation,
  ObservabilitySummary,
  RunObservation,
  Session,
} from "./types";

const API_URL =
  process.env.NEXT_PUBLIC_SIGNALDESK_API_URL ?? "http://127.0.0.1:8001";

export class APIError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { csrf?: string } = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (options.csrf) headers.set("x-signaldesk-csrf", options.csrf);
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) message = payload.detail;
    } catch {
      // Keep the status-based message for non-JSON errors.
    }
    throw new APIError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  login: (accessCode: string, reviewerId: string) =>
    request<Session>("/api/v1/auth/session", {
      method: "POST",
      body: JSON.stringify({ access_code: accessCode, reviewer_id: reviewerId }),
    }),
  session: () => request<Session>("/api/v1/auth/session"),
  logout: (csrf: string) =>
    request<void>("/api/v1/auth/session", { method: "DELETE", csrf }),
  searchCustomers: (query: string) =>
    request<CustomerSearch>(
      `/api/v1/customers?query=${encodeURIComponent(query)}&limit=20`,
    ),
  customer360: (customerId: string) =>
    request<Customer360>(`/api/v1/customers/${customerId}`),
  investigate: (customerId: string, question: string, csrf: string) =>
    request<Investigation>("/api/v1/investigations", {
      method: "POST",
      csrf,
      body: JSON.stringify({ customer_id: customerId, question }),
    }),
  draftSupportAction: (
    investigationId: string,
    reason: string,
    csrf: string,
  ) =>
    request<ActionPackage>(
      `/api/v1/investigations/${investigationId}/support-action`,
      {
        method: "POST",
        csrf,
        body: JSON.stringify({ priority: "MEDIUM", reason }),
      },
    ),
  decideAction: (
    actionId: string,
    decision: "APPROVED" | "REJECTED",
    reason: string,
    csrf: string,
  ) =>
    request<ActionPackage>(`/api/v1/actions/${actionId}/decision`, {
      method: "POST",
      csrf,
      body: JSON.stringify({ decision, reason }),
    }),
  observabilitySummary: () =>
    request<ObservabilitySummary>("/api/v1/observability/summary"),
  observabilityRuns: (limit = 100) =>
    request<{ runs: RunObservation[] }>(
      `/api/v1/observability/runs?limit=${limit}`,
    ),
  evaluateRun: (
    requestId: string,
    result: "PASS" | "FAIL",
    note: string,
    csrf: string,
  ) =>
    request<RunObservation>(
      `/api/v1/observability/runs/${requestId}/evaluation`,
      {
        method: "POST",
        csrf,
        body: JSON.stringify({ result, note }),
      },
    ),
};

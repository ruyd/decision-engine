// Thin fetch wrapper around the decision engine API (proxied by Vite to :8000).
export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
  }
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new ApiError(r.status, (data as { detail?: unknown })?.detail ?? data);
  return data as T;
}

export const api = {
  get: <T>(p: string) => req<T>("GET", p),
  post: <T>(p: string, b?: unknown) => req<T>("POST", p, b ?? {}),
};

// ---- shared types ---------------------------------------------------------------------
export type Flow = "claim" | "prior_auth";
export interface Reason { rule: string; name: string; outcome: string; reason: string }
export interface Contribution { feature: string; label: string; value: number; contribution: number }
export interface Explanation {
  model: string; version: string; unit: string; contributions: Contribution[];
  base_value?: number; prediction?: number; score?: number;
}
export interface TraceEntry {
  id: string; name: string; condition: string; enabled: boolean; matched: boolean; error?: string;
  values: Record<string, unknown>; action: { outcome: string; queue?: string; reason?: string };
}
export interface DecisionRow {
  id: number; flow: Flow; subject_id: string; member_id: string; created_at: string; outcome: string;
  queue: string; amount: number; reasons: Reason[]; fraud_score: number | null; risk_tier: string | null;
  procedure: string | null; injected: string | null; review_status: string; review_outcome: string | null;
  latency_ms: number;
}
export interface Decision extends Omit<DecisionRow, "fraud_score" | "risk_tier" | "procedure"> {
  request: any; facts: any; explanations: { fraud?: Explanation; cost?: Explanation };
  rule_trace: TraceEntry[]; ruleset_version: number; model_versions: Record<string, string>;
  review_note: string | null; reviewed_at: string | null;
}
export interface Rule {
  id: string; name: string; description?: string; condition: string; enabled?: boolean;
  action: { outcome: string; queue?: string; reason?: string };
}
export interface RuleSet { version?: number; default?: { outcome: string; queue?: string; reason?: string }; rules: Rule[] }

export const money = (v: number | string | null | undefined, digits = 0) =>
  v == null || v === "" ? "—" : Number(v).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits });
export const num = (v: number | null | undefined, digits = 0) =>
  v == null ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: digits });
export const pct = (v: number | null | undefined, digits = 1) => (v == null ? "—" : `${(v * 100).toFixed(digits)}%`);
export const time = (s: string) => new Date(s).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
export const datetime = (s: string) => new Date(s).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

export const OUTCOME_STYLE: Record<string, { label: string; cls: string; dot: string }> = {
  APPROVE: { label: "Approved", cls: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", dot: "bg-emerald-500" },
  DENY: { label: "Denied", cls: "bg-rose-50 text-rose-700 ring-rose-600/20", dot: "bg-rose-500" },
  PEND_SIU: { label: "SIU referral", cls: "bg-violet-50 text-violet-700 ring-violet-600/20", dot: "bg-violet-500" },
  PEND_REVIEW: { label: "Pended review", cls: "bg-amber-50 text-amber-800 ring-amber-600/20", dot: "bg-amber-500" },
  PEND_CLINICAL: { label: "Clinical review", cls: "bg-amber-50 text-amber-800 ring-amber-600/20", dot: "bg-amber-500" },
  PEND_INFO: { label: "Info requested", cls: "bg-sky-50 text-sky-700 ring-sky-600/20", dot: "bg-sky-500" },
};
export const OUTCOME_COLOR: Record<string, string> = {
  APPROVE: "#10b981", DENY: "#f43f5e", PEND_SIU: "#8b5cf6", PEND_REVIEW: "#f59e0b", PEND_CLINICAL: "#f59e0b", PEND_INFO: "#0ea5e9",
};
export const QUEUE_LABEL: Record<string, string> = {
  auto: "Auto", siu: "Special Investigations", payment_integrity: "Payment Integrity", claims_review: "Claims Review",
  eligibility: "Eligibility", clinical_review: "Clinical Review", care_management: "Care Management",
};
export const SCENARIO_LABEL: Record<string, string> = {
  upcoding: "Upcoding", price_inflation: "Price inflation", unbundling: "Unbundling", duplicate: "Duplicate",
  deceased_member: "Deceased member", genuine: "Genuine",
};
export const SCENARIO_DESC: Record<string, string> = {
  upcoding: "Visits billed at the highest complexity level with inflated prices.",
  price_inflation: "Every line billed at 4–8× the normal price for the code.",
  unbundling: "Many extra lab tests added to an ordinary visit at top-of-range prices.",
  duplicate: "Exact resubmission of a claim that was already billed.",
  deceased_member: "Services billed for a member after their date of death.",
};
export const TIER_STYLE: Record<string, string> = {
  Low: "bg-emerald-50 text-emerald-700", Moderate: "bg-sky-50 text-sky-700",
  High: "bg-amber-50 text-amber-800", "Very high": "bg-rose-50 text-rose-700",
};

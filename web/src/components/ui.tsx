import { Link } from "react-router";
import type { ReactNode } from "react";
import { FlaskConical, Loader2 } from "lucide-react";
import { OUTCOME_STYLE, QUEUE_LABEL, SCENARIO_LABEL, TIER_STYLE } from "../lib/format";

export function OutcomeBadge({ outcome, size = "sm" }: { outcome: string; size?: "sm" | "lg" }) {
  const s = OUTCOME_STYLE[outcome] ?? { label: outcome, cls: "bg-slate-100 text-slate-700 ring-slate-500/20", dot: "bg-slate-400" };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full ring-1 ring-inset font-medium whitespace-nowrap ${s.cls} ${
      size === "lg" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs"}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />{s.label}
    </span>
  );
}

export function TierBadge({ tier }: { tier?: string | null }) {
  if (!tier) return <span className="text-slate-400">—</span>;
  return <span className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${TIER_STYLE[tier] ?? "bg-slate-100"}`}>{tier}</span>;
}

export function ScenarioBadge({ scenario }: { scenario?: string | null }) {
  if (!scenario) return null;
  return (
    <span title="Injected by the simulator (ground truth for the demo)"
      className="inline-flex items-center gap-1 rounded-md bg-fuchsia-50 px-1.5 py-0.5 text-[11px] font-medium text-fuchsia-700 ring-1 ring-inset ring-fuchsia-600/20 whitespace-nowrap">
      <FlaskConical size={11} />{SCENARIO_LABEL[scenario] ?? scenario}
    </span>
  );
}

export const queueLabel = (q?: string | null) => (q ? QUEUE_LABEL[q] ?? q : "—");

export function ScoreBar({ score }: { score: number | null }) {
  if (score == null) return <span className="text-slate-400">—</span>;
  const color = score >= 0.995 ? "bg-violet-500" : score >= 0.98 ? "bg-amber-500" : score >= 0.9 ? "bg-amber-300" : "bg-slate-300";
  return (
    <div className="flex items-center gap-2 min-w-[90px]">
      <div className="h-1.5 w-14 rounded-full bg-slate-100 overflow-hidden"><div className={`h-full ${color}`} style={{ width: `${score * 100}%` }} /></div>
      <span className="tabular-nums text-xs text-slate-600">{(score * 100).toFixed(1)}</span>
    </div>
  );
}

export function Kpi({ label, value, sub, icon, accent = "text-slate-900" }: {
  label: string; value: ReactNode; sub?: ReactNode; icon?: ReactNode; accent?: string;
}) {
  return (
    <div className="card px-4 py-3.5">
      <div className="flex items-center justify-between"><span className="label">{label}</span><span className="text-slate-400">{icon}</span></div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${accent}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="text-sm text-slate-500 mt-0.5 max-w-3xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="flex items-center gap-2 text-sm text-slate-500 p-6"><Loader2 className="animate-spin" size={16} />{label}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="p-8 text-center text-sm text-slate-500">{children}</div>;
}

export function MemberLink({ id }: { id: string }) {
  return <Link to={`/members/${id}`} className="mono text-brand-700 hover:underline" onClick={(e) => e.stopPropagation()}>{id}</Link>;
}

export function Card({ title, icon, actions, children, className = "" }: {
  title?: ReactNode; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && <div className="card-h justify-between"><span className="flex items-center gap-2">{icon}{title}</span>{actions}</div>}
      {children}
    </section>
  );
}

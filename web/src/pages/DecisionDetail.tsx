import { useState } from "react";
import { Link, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BrainCircuit, Check, ClipboardList, FileText, FlaskConical, ListChecks, Scale, User, X } from "lucide-react";
import { api, type Decision } from "../api";
import { CostWaterfallSummary, RuleTrace, ScoreGauge, ShapBars } from "../components/explain";
import { Card, Loading, MemberLink, OutcomeBadge, TierBadge, queueLabel } from "../components/ui";
import { SCENARIO_DESC, SCENARIO_LABEL, datetime, money } from "../lib/format";

function ReviewPanel({ d }: { d: Decision }) {
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const m = useMutation({
    mutationFn: (action: "approve" | "deny") => api.post(`/decisions/${d.id}/review`, { action, note }),
    onSuccess: () => qc.invalidateQueries(),
  });
  if (d.review_status === "resolved")
    return (
      <div className="rounded-lg bg-slate-50 px-4 py-3 text-sm">
        <span className="label">Human review</span>
        <div className="mt-1 flex items-center gap-2"><OutcomeBadge outcome={d.review_outcome!} /> <span className="text-slate-500 text-xs">{d.reviewed_at && datetime(d.reviewed_at)}</span></div>
        {d.review_note && <div className="mt-1 text-slate-600">“{d.review_note}”</div>}
      </div>
    );
  if (d.review_status !== "open") return null;
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3">
      <div className="text-sm font-medium text-amber-900">Waiting in {queueLabel(d.queue)}</div>
      <div className="mt-2 flex flex-wrap gap-2">
        <input className="input flex-1 min-w-[200px]" placeholder="Reviewer note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        <button className="btn bg-emerald-600 text-white hover:bg-emerald-700" disabled={m.isPending} onClick={() => m.mutate("approve")}><Check size={15} />Approve</button>
        <button className="btn bg-rose-600 text-white hover:bg-rose-700" disabled={m.isPending} onClick={() => m.mutate("deny")}><X size={15} />Deny</button>
      </div>
    </div>
  );
}

function ClaimBody({ d }: { d: Decision }) {
  const c = d.request; const f = d.facts;
  return (
    <>
      <Card title="Claim" icon={<FileText size={16} className="text-slate-500" />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 px-5 pb-4 text-sm">
          <div><div className="label">Member</div><MemberLink id={c.member_id} /></div>
          <div><div className="label">Service date</div>{c.service_date}</div>
          <div><div className="label">Rendering provider</div><span className="mono">{c.provider_npi ?? "—"}</span>
            <div className="text-xs text-slate-500">{f.provider.known ? `${f.provider.claims.toLocaleString()} claims on file · ${(f.provider.high_em_share * 100).toFixed(0)}% top-level visits` : "No billing history"}</div></div>
          <div><div className="label">History checks</div>
            <div className="text-xs">{f.claim.member_claims_30d} member claims in prior 30 days</div>
            <div className={`text-xs ${f.claim.dup_count ? "text-rose-600 font-medium" : ""}`}>{f.claim.dup_count} identical claims on file</div></div>
        </div>
        {c.dx_codes?.length > 0 && (
          <div className="px-5 pb-3 flex flex-wrap gap-1.5">
            {c.dx_codes.map((dx: string, i: number) => (
              <span key={dx + i} className="rounded-md bg-slate-100 px-2 py-0.5 text-xs"><span className="mono">{dx}</span>{c.dx_labels?.[dx] && <span className="text-slate-500"> · {c.dx_labels[dx]}</span>}</span>
            ))}
          </div>
        )}
        <table className="tbl">
          <thead><tr><th>#</th><th>Procedure</th><th className="text-right">Billed</th><th className="text-right">Typical (median)</th><th className="text-right">95th pct</th><th className="text-right">vs. median</th></tr></thead>
          <tbody>
            {c.lines.map((l: any) => {
              const hot = l.price_ratio != null && (l.price_ratio >= 6 || (l.p95 != null && l.amount > l.p95));
              return (
                <tr key={l.line_num}>
                  <td className="text-slate-400">{l.line_num}</td>
                  <td><span className="mono">{l.hcpcs ?? "—"}</span> <span className="text-slate-500 text-xs">{l.label}</span></td>
                  <td className={`text-right tabular-nums ${hot ? "text-rose-600 font-semibold" : ""}`}>{money(l.amount)}</td>
                  <td className="text-right tabular-nums text-slate-500">{money(l.p50)}</td>
                  <td className="text-right tabular-nums text-slate-500">{money(l.p95)}</td>
                  <td className={`text-right tabular-nums ${hot ? "text-rose-600 font-semibold" : "text-slate-500"}`}>{l.price_ratio != null ? `${l.price_ratio.toFixed(1)}×` : "—"}</td>
                </tr>
              );
            })}
            <tr><td /><td className="font-medium">Total</td><td className="text-right font-semibold tabular-nums">{money(f.claim.total_paid)}</td><td colSpan={3} /></tr>
          </tbody>
        </table>
      </Card>
      {d.explanations.fraud && (
        <Card title={`Fraud anomaly model · claim_fraud v${d.explanations.fraud.version}`} icon={<BrainCircuit size={16} className="text-violet-600" />}>
          <ScoreGauge score={d.explanations.fraud.score!} />
          <div className="px-5 pb-1 text-xs text-slate-500">SHAP: what made this claim look unusual (red) or ordinary (blue) to the Isolation Forest.</div>
          <ShapBars expl={d.explanations.fraud} />
        </Card>
      )}
    </>
  );
}

function PriorAuthBody({ d }: { d: Decision }) {
  const r = d.facts.request; const m = d.facts.member;
  return (
    <>
      <Card title="Request" icon={<ClipboardList size={16} className="text-slate-500" />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 px-5 pb-4 text-sm">
          <div className="col-span-2"><div className="label">Procedure</div><span className="mono">{r.kind === "drg" ? `DRG ${r.code}` : r.code}</span>
            {r.label && r.label !== r.code && r.label !== `DRG ${r.code}` && <> · {r.label}</>}
            <div className="text-xs text-slate-500 capitalize">{r.category} · {r.units} unit{r.units > 1 ? "s" : ""}</div></div>
          <div><div className="label">Expected cost</div><span className="text-lg font-semibold tabular-nums">{money(r.est_cost)}</span>
            <div className="text-xs text-slate-500">high-end {money(r.high_cost)}</div></div>
          <div><div className="label">Requested for</div>{d.request.service_date}</div>
        </div>
      </Card>
      <Card title="Member" icon={<User size={16} className="text-slate-500" />}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 px-5 pb-4 text-sm">
          <div><div className="label">Member</div><MemberLink id={m.id} /><div className="text-xs text-slate-500">{m.age} y · {m.sex} · state {m.state}</div></div>
          <div><div className="label">Risk tier</div><TierBadge tier={m.risk_tier} /><div className="text-xs text-slate-500">{m.risk_pct?.toFixed(0)}th percentile</div></div>
          <div><div className="label">Coverage (months)</div><div className="text-xs">Part A {m.parta_months ?? "—"} · Part B {m.partb_months ?? "—"} · Part D {m.partd_months ?? "—"}</div>
            {m.deceased && <div className="text-xs text-rose-600 font-medium">Deceased {m.death_date}</div>}</div>
          <div><div className="label">Chronic conditions</div><div className="text-xs">{m.chronic?.length ? m.chronic.join(", ") : "None on file"}</div></div>
        </div>
      </Card>
      {d.explanations.cost && (
        <Card title={`Cost model · next_year_cost v${d.explanations.cost.version}`} icon={<BrainCircuit size={16} className="text-brand-600" />}>
          <CostWaterfallSummary expl={d.explanations.cost} />
          <div className="px-5 pb-1 text-xs text-slate-500">SHAP (dollars): what raises (red) or lowers (blue) this member's expected cost vs. the average member.</div>
          <ShapBars expl={d.explanations.cost} dollars />
        </Card>
      )}
    </>
  );
}

export default function DecisionDetail() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["decision", id], queryFn: () => api.get<Decision>(`/decisions/${id}`) });
  if (!q.data) return <Loading />;
  const d = q.data;
  return (
    <>
      <Link to={d.flow === "claim" ? "/claims" : "/prior-auth"} className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800 mb-3">
        <ArrowLeft size={14} /> {d.flow === "claim" ? "Claims" : "Prior authorization"}
      </Link>
      <div className="card px-5 py-4 mb-4">
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex-1 min-w-[260px]">
            <div className="label">{d.flow === "claim" ? "Claim decision" : "Prior-auth decision"} #{d.id}</div>
            <div className="mt-0.5 flex items-center gap-3"><h1 className="text-xl font-semibold mono">{d.subject_id}</h1><OutcomeBadge outcome={d.outcome} size="lg" /></div>
            <div className="mt-1 text-xs text-slate-500">
              {datetime(d.created_at)} · routed to <b className="text-slate-700">{queueLabel(d.queue)}</b> · {d.latency_ms} ms ·
              rules v{d.ruleset_version} · models {Object.entries(d.model_versions ?? {}).map(([k, v]) => `${k} v${v}`).join(", ")}
            </div>
          </div>
          <div className="w-full lg:w-[460px]"><ReviewPanel d={d} /></div>
        </div>
        {d.injected && (
          <div className="mt-3 flex items-start gap-2 rounded-lg bg-fuchsia-50 px-3 py-2 text-sm text-fuchsia-800">
            <FlaskConical size={16} className="mt-0.5 shrink-0" />
            <div><b>Simulator ground truth: {SCENARIO_LABEL[d.injected]}.</b> {SCENARIO_DESC[d.injected]} The engine did not see this label.</div>
          </div>
        )}
        <div className="mt-4">
          <div className="label mb-1.5 flex items-center gap-1"><Scale size={12} /> Why this decision</div>
          <ul className="space-y-1">
            {d.reasons.map((r, i) => (
              <li key={r.rule} className={`flex items-center gap-2 text-sm ${i === 0 ? "" : "text-slate-500"}`}>
                <OutcomeBadge outcome={r.outcome} /><span className={i === 0 ? "font-medium" : ""}>{r.reason}</span>
                <span className="mono text-slate-400 text-xs">{r.rule}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[1.25fr_1fr] gap-4 items-start">
        <div className="space-y-4">{d.flow === "claim" ? <ClaimBody d={d} /> : <PriorAuthBody d={d} />}</div>
        <div className="space-y-4">
          <Card title={`Rule trace · ${d.rule_trace.filter((t) => t.matched).length} of ${d.rule_trace.length} rules fired`} icon={<ListChecks size={16} className="text-amber-600" />}>
            <RuleTrace trace={d.rule_trace} />
          </Card>
          <Card title="Facts the rules saw">
            <pre className="mono text-[11.5px] px-5 pb-4 max-h-96 overflow-auto text-slate-700">{JSON.stringify(d.facts, null, 2)}</pre>
          </Card>
        </div>
      </div>
    </>
  );
}

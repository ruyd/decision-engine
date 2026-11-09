import { useNavigate, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, type DecisionRow } from "../api";
import { Card, Empty, Loading, MemberLink, OutcomeBadge, PageHeader, ScenarioBadge, ScoreBar, queueLabel } from "../components/ui";
import { OUTCOME_STYLE, QUEUE_LABEL, SCENARIO_LABEL, money, num, time } from "../lib/format";

const PAGE = 50;

export default function Claims() {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const f = { outcome: sp.get("outcome") ?? "", queue: sp.get("queue") ?? "", injected: sp.get("injected") ?? "", q: sp.get("q") ?? "" };
  const page = Number(sp.get("page") ?? 0);
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); v ? n.set(k, v) : n.delete(k); n.delete("page"); setSp(n); };
  const qs = new URLSearchParams({ flow: "claim", limit: String(PAGE), offset: String(page * PAGE), ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) });
  const data = useQuery({ queryKey: ["decisions", qs.toString()], queryFn: () => api.get<{ total: number; items: DecisionRow[] }>(`/decisions?${qs}`) });

  return (
    <>
      <PageHeader title="Claims" subtitle="Every professional claim the engine decided, with its anomaly score, outcome and the rule that drove it." />
      <Card>
        <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-slate-100">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
            <input className="input pl-8 w-64" placeholder="Claim or member id" defaultValue={f.q}
              onKeyDown={(e) => e.key === "Enter" && set("q", (e.target as HTMLInputElement).value)} />
          </div>
          <select className="input" value={f.outcome} onChange={(e) => set("outcome", e.target.value)}>
            <option value="">All outcomes</option>
            {["APPROVE", "PEND_REVIEW", "PEND_SIU", "DENY"].map((o) => <option key={o} value={o}>{OUTCOME_STYLE[o].label}</option>)}
          </select>
          <select className="input" value={f.queue} onChange={(e) => set("queue", e.target.value)}>
            <option value="">All queues</option>
            {["auto", "payment_integrity", "siu", "claims_review", "eligibility"].map((q) => <option key={q} value={q}>{QUEUE_LABEL[q]}</option>)}
          </select>
          <select className="input" value={f.injected} onChange={(e) => set("injected", e.target.value)}>
            <option value="">Genuine + injected</option>
            <option value="none">Genuine only</option>
            <option value="any">Injected fraud only</option>
            {Object.keys(SCENARIO_LABEL).filter((s) => s !== "genuine").map((s) => <option key={s} value={s}>Injected: {SCENARIO_LABEL[s]}</option>)}
          </select>
          <span className="ml-auto text-xs text-slate-500">{data.data ? `${num(data.data.total)} claims` : ""}</span>
        </div>
        {!data.data ? <Loading /> : data.data.items.length === 0 ? <Empty>No claims match. Run the simulator from the Overview page.</Empty> : (
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Decided</th><th>Claim</th><th>Member</th><th>Service date</th><th className="text-right">Billed</th><th>Fraud score</th><th>Outcome</th><th>Queue</th><th>Top reason</th></tr></thead>
              <tbody>
                {data.data.items.map((r) => (
                  <tr key={r.id} className="row-link" onClick={() => nav(`/decisions/${r.id}`)}>
                    <td className="text-xs text-slate-500 tabular-nums">{time(r.created_at)}</td>
                    <td className="mono whitespace-nowrap">{r.subject_id} <ScenarioBadge scenario={r.injected} /></td>
                    <td><MemberLink id={r.member_id} /></td>
                    <td className="text-xs tabular-nums">{(r as any).service_date ?? ""}</td>
                    <td className="text-right tabular-nums">{money(r.amount)}</td>
                    <td><ScoreBar score={r.fraud_score} /></td>
                    <td><OutcomeBadge outcome={r.outcome} /></td>
                    <td className="text-xs text-slate-600 whitespace-nowrap">{queueLabel(r.queue)}</td>
                    <td className="text-xs text-slate-500 max-w-[280px] truncate" title={r.reasons[0]?.reason}>{r.reasons[0]?.name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data.data && data.data.total > PAGE && (
          <div className="flex items-center justify-end gap-2 px-4 py-2.5 text-sm">
            <button className="btn-outline" disabled={page === 0} onClick={() => { const n = new URLSearchParams(sp); n.set("page", String(page - 1)); setSp(n); }}>Previous</button>
            <span className="text-slate-500 text-xs">Page {page + 1} of {Math.ceil(data.data.total / PAGE)}</span>
            <button className="btn-outline" disabled={(page + 1) * PAGE >= data.data.total} onClick={() => { const n = new URLSearchParams(sp); n.set("page", String(page + 1)); setSp(n); }}>Next</button>
          </div>
        )}
      </Card>
    </>
  );
}

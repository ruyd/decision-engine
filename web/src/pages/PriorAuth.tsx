import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, Loader2, Shuffle } from "lucide-react";
import { api, type DecisionRow } from "../api";
import { CostWaterfallSummary, ShapBars } from "../components/explain";
import { Card, Empty, Loading, MemberLink, OutcomeBadge, PageHeader, TierBadge, queueLabel } from "../components/ui";
import { money, time } from "../lib/format";

interface CatalogItem { code: string; kind: "hcpcs" | "drg"; category: string; label: string; volume: number; typical_cost: number; high_cost: number }
const CATS = ["inpatient", "surgery", "imaging", "dme", "drug"];

export default function PriorAuth() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [sp] = useSearchParams();
  const [member, setMember] = useState(sp.get("member") ?? "");
  const [cat, setCat] = useState("inpatient");
  const [code, setCode] = useState("");
  const [units, setUnits] = useState(1);
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: () => api.get<CatalogItem[]>("/prior-auth/catalog") });
  const list = useQuery({ queryKey: ["decisions", "pa"], queryFn: () => api.get<{ total: number; items: DecisionRow[] }>("/decisions?flow=prior_auth&limit=30") });
  const items = useMemo(() => (catalog.data ?? []).filter((c) => c.category === cat), [catalog.data, cat]);
  const selected = items.find((c) => `${c.kind}:${c.code}` === code) ?? items[0];
  const submit = useMutation({
    mutationFn: () => api.post<any>("/prior-auth", { member_id: member.trim(), code: selected!.code, kind: selected!.kind, units }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["decisions"] }),
  });
  const random = async (tier?: string) => {
    const r = await api.get<{ items: { member_id: string }[] }>(`/members?limit=200${tier ? `&tier=${encodeURIComponent(tier)}` : ""}`);
    setMember(r.items[Math.floor(Math.random() * r.items.length)].member_id);
  };
  const res = submit.data;

  return (
    <>
      <PageHeader title="Prior authorization"
        subtitle="Requests are decided instantly: eligibility and cost rules, plus the member's predicted next-year cost from the risk model — explained with SHAP." />
      <div className="grid grid-cols-1 xl:grid-cols-[420px_1fr] gap-4 items-start">
        <Card title="New request" icon={<ClipboardCheck size={16} className="text-brand-600" />}>
          <div className="px-5 pb-5 space-y-3">
            <label className="block space-y-1"><div className="label">Member id</div>
              <div className="flex gap-2">
                <input className="input flex-1 mono" placeholder="e.g. 00013D2EFD8E45D1" value={member} onChange={(e) => setMember(e.target.value)} />
                <button className="btn-outline" title="Random member" onClick={() => random()}><Shuffle size={14} /></button>
              </div>
              <div className="flex gap-2 text-xs"><span className="text-slate-500">Random:</span>
                {["Low", "High", "Very high"].map((t) => <button key={t} className="text-brand-700 hover:underline" onClick={() => random(t)}>{t} risk</button>)}</div>
            </label>
            <div className="space-y-1"><div className="label">Service category</div>
              <div className="flex flex-wrap gap-1.5">
                {CATS.map((c) => (
                  <button key={c} onClick={() => { setCat(c); setCode(""); }}
                    className={`rounded-full px-2.5 py-1 text-xs capitalize ring-1 ${cat === c ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-slate-600 ring-slate-300 hover:bg-slate-50"}`}>{c}</button>
                ))}
              </div>
            </div>
            <label className="block space-y-1"><div className="label">Procedure</div>
              <select className="input w-full" value={selected ? `${selected.kind}:${selected.code}` : ""} onChange={(e) => setCode(e.target.value)}>
                {items.map((c) => <option key={c.kind + c.code} value={`${c.kind}:${c.code}`}>{c.kind === "drg" ? "DRG " : ""}{c.code} — {c.label} ({money(c.typical_cost)})</option>)}
              </select>
              {selected && <div className="text-xs text-slate-500">Typical {money(selected.typical_cost)} · high-end {money(selected.high_cost)} · {selected.volume.toLocaleString()} in history</div>}
            </label>
            <label className="block space-y-1 w-28"><div className="label">Units</div>
              <input type="number" min={1} max={20} className="input w-full" value={units} onChange={(e) => setUnits(+e.target.value)} /></label>
            <button className="btn-primary w-full justify-center" disabled={!member || !selected || submit.isPending} onClick={() => submit.mutate()}>
              {submit.isPending && <Loader2 size={15} className="animate-spin" />} Submit request
            </button>
            {submit.error && <div className="text-sm text-rose-600">{String((submit.error as any).detail ?? submit.error)}</div>}
          </div>
        </Card>

        <div className="space-y-4">
          {res && (
            <Card title={<span className="flex items-center gap-2">Decision <OutcomeBadge outcome={res.outcome} size="lg" /></span>}
              actions={<Link to={`/decisions/${res.id}`} className="text-xs font-normal text-brand-700 hover:underline">Full audit trail →</Link>}>
              <div className="px-5 pb-3 space-y-1">
                {res.reasons.map((r: any) => <div key={r.rule} className="text-sm flex items-center gap-2"><OutcomeBadge outcome={r.outcome} /> {r.reason}</div>)}
                <div className="text-xs text-slate-500 pt-1">
                  {res.facts.request.label} · expected {money(res.facts.request.est_cost)} · member risk <TierBadge tier={res.facts.member.risk_tier} /> ·
                  routed to {queueLabel(res.queue)} · decided in {res.latency_ms} ms
                </div>
              </div>
              {res.explanations.cost && (<><CostWaterfallSummary expl={res.explanations.cost} /><ShapBars expl={res.explanations.cost} top={6} dollars /></>)}
            </Card>
          )}
          <Card title="Recent requests">
            {!list.data ? <Loading /> : list.data.items.length === 0 ? <Empty>No requests yet.</Empty> : (
              <table className="tbl">
                <thead><tr><th>Time</th><th>Request</th><th>Member</th><th>Procedure</th><th className="text-right">Expected</th><th>Risk</th><th>Outcome</th><th>Queue</th></tr></thead>
                <tbody>
                  {list.data.items.map((r) => (
                    <tr key={r.id} className="row-link" onClick={() => nav(`/decisions/${r.id}`)}>
                      <td className="text-xs text-slate-500 tabular-nums">{time(r.created_at)}</td>
                      <td className="mono">{r.subject_id}</td>
                      <td><MemberLink id={r.member_id} /></td>
                      <td className="text-xs max-w-[220px] truncate">{r.procedure}</td>
                      <td className="text-right tabular-nums">{money(r.amount)}</td>
                      <td><TierBadge tier={r.risk_tier} /></td>
                      <td><OutcomeBadge outcome={r.outcome} /></td>
                      <td className="text-xs text-slate-600">{queueLabel(r.queue)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

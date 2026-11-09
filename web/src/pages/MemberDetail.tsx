import { Link, useNavigate, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowLeft, BrainCircuit, ClipboardCheck, HeartPulse, Hospital } from "lucide-react";
import { api } from "../api";
import { CostWaterfallSummary, ShapBars } from "../components/explain";
import { Card, Empty, Loading, OutcomeBadge, ScenarioBadge, TierBadge, queueLabel } from "../components/ui";
import { money, time } from "../lib/format";

export default function MemberDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["member", id], queryFn: () => api.get<any>(`/members/${id}`) });
  if (q.error) return <Empty>Member not found.</Empty>;
  if (!q.data) return <Loading label="Scoring member and computing SHAP…" />;
  const { facts: f, explanation, years, inpatient_stays, decisions } = q.data;
  const chart = years.map((y: any) => ({ year: y.year, Inpatient: +y.inpatient, Outpatient: +y.outpatient, Physician: +y.physician, Drugs: +y.drugs }));
  chart.push({ year: "2010 (pred.)", Predicted: Math.round(explanation.prediction) });
  return (
    <>
      <Link to="/members" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800 mb-3"><ArrowLeft size={14} /> Members</Link>
      <div className="card px-5 py-4 mb-4 flex flex-wrap items-center gap-6">
        <div>
          <div className="label">Member</div>
          <h1 className="text-xl font-semibold mono">{f.id}</h1>
          <div className="text-sm text-slate-500">{f.age} years · {f.sex === "M" ? "Male" : "Female"} · state {f.state}{f.esrd ? " · ESRD" : ""}
            {f.deceased && <span className="ml-2 text-rose-600 font-medium">Deceased {f.death_date}</span>}</div>
        </div>
        <div><div className="label">Predicted 2010 cost</div><div className="text-2xl font-semibold tabular-nums">{money(explanation.prediction)}</div></div>
        <div><div className="label">Risk tier</div><div className="mt-1"><TierBadge tier={f.risk_tier} /> <span className="text-xs text-slate-500">{f.risk_pct?.toFixed(0)}th pct</span></div></div>
        <div><div className="label">Coverage months (2010)</div><div className="text-sm">A {f.parta_months ?? "—"} · B {f.partb_months ?? "—"} · D {f.partd_months ?? "—"}</div></div>
        <div className="ml-auto"><button className="btn-primary" onClick={() => nav(`/prior-auth?member=${f.id}`)}><ClipboardCheck size={15} />New prior auth</button></div>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
        <Card title={`Why this prediction · next_year_cost v${explanation.version}`} icon={<BrainCircuit size={16} className="text-brand-600" />}>
          <CostWaterfallSummary expl={explanation} />
          <ShapBars expl={explanation} top={12} dollars />
        </Card>
        <div className="space-y-4">
          <Card title="Chronic conditions" icon={<HeartPulse size={16} className="text-rose-500" />}>
            <div className="px-5 pb-4 flex flex-wrap gap-1.5">
              {f.chronic.length === 0 ? <span className="text-sm text-slate-500">None on file</span> :
                f.chronic.map((c: string) => <span key={c} className="rounded-full bg-rose-50 px-2.5 py-0.5 text-xs text-rose-700 ring-1 ring-rose-200">{c}</span>)}
            </div>
          </Card>
          <Card title="Annual cost of care">
            <div className="h-60 px-2 pb-3">
              <ResponsiveContainer>
                <BarChart data={chart} margin={{ left: 10, right: 10 }}>
                  <CartesianGrid vertical={false} stroke="#f1f5f9" />
                  <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                  <Tooltip formatter={(v) => money(Number(v))} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="Inpatient" stackId="a" fill="#0f766e" />
                  <Bar dataKey="Outpatient" stackId="a" fill="#14b8a6" />
                  <Bar dataKey="Physician" stackId="a" fill="#5eead4" />
                  <Bar dataKey="Drugs" stackId="a" fill="#a5b4fc" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="Predicted" stackId="a" fill="#cbd5e1" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="px-5 pb-3 text-xs text-slate-500">2010 actuals in SynPUF are incomplete (fewer claims), so the prediction is shown on its own.</p>
          </Card>
          <Card title="Hospital stays" icon={<Hospital size={16} className="text-slate-500" />}>
            {inpatient_stays.length === 0 ? <Empty>No inpatient stays 2008–2010.</Empty> : (
              <table className="tbl"><thead><tr><th>Admitted</th><th>DRG</th><th>Principal dx</th><th className="text-right">Paid</th></tr></thead>
                <tbody>{inpatient_stays.map((s: any) => (
                  <tr key={s.clm_id}><td className="tabular-nums text-xs">{s.clm_from_dt}</td>
                    <td className="text-xs"><span className="mono">{s.clm_drg_cd}</span> {s.drg_label}</td>
                    <td className="text-xs"><span className="mono">{s.dx}</span> {s.dx_label}</td>
                    <td className="text-right tabular-nums">{money(s.clm_pmt_amt)}</td></tr>))}</tbody></table>
            )}
          </Card>
          <Card title="Engine decisions for this member">
            {decisions.length === 0 ? <Empty>None yet.</Empty> : (
              <table className="tbl"><tbody>{decisions.map((d: any) => (
                <tr key={d.id} className="row-link" onClick={() => nav(`/decisions/${d.id}`)}>
                  <td className="text-xs text-slate-500">{time(d.created_at)}</td><td className="text-xs">{d.flow === "claim" ? "Claim" : "Prior auth"}</td>
                  <td className="mono">{d.subject_id} <ScenarioBadge scenario={d.injected} /></td><td className="text-right tabular-nums">{money(d.amount)}</td>
                  <td><OutcomeBadge outcome={d.outcome} /></td><td className="text-xs text-slate-500">{queueLabel(d.queue)}</td></tr>))}</tbody></table>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

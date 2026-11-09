import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Gauge, Inbox, Loader2, Play, RotateCcw, ShieldAlert, Sparkles, Timer, Wallet } from "lucide-react";
import { api, type DecisionRow } from "../api";
import { Card, Kpi, Loading, OutcomeBadge, PageHeader, ScenarioBadge, ScoreBar, queueLabel } from "../components/ui";
import { OUTCOME_COLOR, OUTCOME_STYLE, SCENARIO_LABEL, money, num, pct, time } from "../lib/format";

const SCENARIOS = ["genuine", "upcoding", "price_inflation", "unbundling", "duplicate", "deceased_member"];

function Simulator() {
  const qc = useQueryClient();
  const [claims, setClaims] = useState(200);
  const [fraud, setFraud] = useState(10);
  const [pas, setPas] = useState(30);
  const sim = useMutation({
    mutationFn: () => api.post<any>("/simulate", { claims, fraud_rate: fraud / 100, prior_auths: pas }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const reset = useMutation({ mutationFn: () => api.post("/admin/reset"), onSuccess: () => qc.invalidateQueries() });
  return (
    <Card title="Simulate incoming traffic" icon={<Sparkles size={16} className="text-brand-600" />}>
      <div className="px-5 pb-4">
        <p className="text-xs text-slate-500 mb-3">
          Replays real 2010 professional claims from the warehouse and injects known fraud patterns at the chosen rate.
          Prior-auth requests are generated for random members.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1"><div className="label">Claims</div>
            <input type="number" className="input w-24" min={0} max={1000} value={claims} onChange={(e) => setClaims(+e.target.value)} /></label>
          <label className="space-y-1"><div className="label">Fraud rate %</div>
            <input type="number" className="input w-24" min={0} max={100} value={fraud} onChange={(e) => setFraud(+e.target.value)} /></label>
          <label className="space-y-1"><div className="label">Prior auths</div>
            <input type="number" className="input w-24" min={0} max={500} value={pas} onChange={(e) => setPas(+e.target.value)} /></label>
          <button className="btn-primary" disabled={sim.isPending} onClick={() => sim.mutate()}>
            {sim.isPending ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            {sim.isPending ? "Deciding…" : "Run"}
          </button>
          <button className="btn-ghost" disabled={reset.isPending}
            onClick={() => confirm("Clear all simulated decisions? Rules and models are kept.") && reset.mutate()}>
            <RotateCcw size={14} /> Reset
          </button>
        </div>
        {sim.data && (
          <div className="mt-3 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-800">
            Decided <b>{sim.data.processed}</b> in {sim.data.seconds}s (avg {sim.data.avg_latency_ms} ms each) ·{" "}
            {Object.entries(sim.data.outcomes as Record<string, Record<string, number>>).map(([flow, o]) => (
              <span key={flow} className="mr-2">{flow === "claim" ? "Claims" : "PA"}: {Object.entries(o).map(([k, v]) => `${v} ${OUTCOME_STYLE[k]?.label ?? k}`).join(", ")}</span>
            ))}
          </div>
        )}
        {sim.error && <div className="mt-3 text-sm text-rose-600">{String(sim.error)}</div>}
      </div>
    </Card>
  );
}

export default function Overview() {
  const nav = useNavigate();
  const d = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<any>("/dashboard"), refetchInterval: 15000 });
  const recent = useQuery({ queryKey: ["decisions", "recent"], queryFn: () => api.get<{ items: DecisionRow[] }>("/decisions?limit=12") });
  if (!d.data) return <Loading />;
  const { totals, outcomes, queues, fraud_matrix, caught_by } = d.data;
  const claimOut = outcomes.filter((o: any) => o.flow === "claim");
  const paOut = outcomes.filter((o: any) => o.flow === "prior_auth");
  const nClaims = totals.claims || 0;
  const autoClaims = claimOut.find((o: any) => o.outcome === "APPROVE")?.n ?? 0;
  const held = claimOut.filter((o: any) => o.outcome !== "APPROVE").reduce((a: number, o: any) => a + Number(o.amount), 0);
  const autoPa = paOut.find((o: any) => o.outcome === "APPROVE")?.n ?? 0;

  const m: Record<string, Record<string, number>> = {};
  for (const r of fraud_matrix) (m[r.scenario] ??= {})[r.outcome] = r.n;
  const caughtRule: Record<string, Record<string, number>> = {};
  for (const r of caught_by) (caughtRule[r.scenario] ??= {})[r.rule] = r.n;
  const outcomesCols = ["APPROVE", "PEND_REVIEW", "PEND_SIU", "DENY"];
  const injectedTotal = SCENARIOS.slice(1).reduce((a, s) => a + Object.values(m[s] ?? {}).reduce((x, y) => x + y, 0), 0);
  const injectedCaught = SCENARIOS.slice(1).reduce((a, s) => a + Object.entries(m[s] ?? {}).filter(([k]) => k !== "APPROVE").reduce((x, [, y]) => x + y, 0), 0);
  const genuine = Object.values(m.genuine ?? {}).reduce((x, y) => x + y, 0);
  const genuineFlagged = Object.entries(m.genuine ?? {}).filter(([k]) => k !== "APPROVE").reduce((x, [, y]) => x + y, 0);

  return (
    <>
      <PageHeader title="Overview"
        subtitle="Automated claim routing and prior authorization, combining business rules with a fraud anomaly model and a cost-prediction model. Every decision is explained and auditable." />
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-4 mb-4">
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          <Kpi label="Claims decided" value={num(nClaims)} icon={<Gauge size={16} />} sub={`${num(totals.prior_auths)} prior auths`} />
          <Kpi label="Auto-adjudicated" value={pct(nClaims ? autoClaims / nClaims : null)} accent="text-emerald-600"
            sub="claims paid with no human touch" icon={<Sparkles size={16} />} />
          <Kpi label="Held from payment" value={money(held)} icon={<Wallet size={16} />} sub="pended or denied claim dollars" />
          <Kpi label="Fraud caught" value={injectedTotal ? pct(injectedCaught / injectedTotal, 0) : "—"} accent="text-violet-600"
            icon={<ShieldAlert size={16} />} sub={`${injectedCaught}/${injectedTotal} injected · ${pct(genuine ? genuineFlagged / genuine : null)} of genuine flagged`} />
          <Kpi label="PA auto-approved" value={pct(totals.prior_auths ? autoPa / totals.prior_auths : null)}
            icon={<Sparkles size={16} />} sub="decided instantly at request time" />
          <Kpi label="Decision latency" value={`${num(totals.claim_latency, 0)} ms`} icon={<Timer size={16} />}
            sub={`claims · PA ${num(totals.pa_latency, 0)} ms (incl. SHAP)`} />
        </div>
        <Simulator />
      </div>

      {nClaims === 0 ? (
        <Card><div className="p-10 text-center text-slate-500">No decisions yet — run the simulator to send traffic through the engine.</div></Card>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <Card title="Fraud detection vs. simulator ground truth" icon={<ShieldAlert size={16} className="text-violet-600" />} className="xl:col-span-2 min-w-0">
            <div className="overflow-x-auto">
              <table className="tbl">
                <thead><tr><th>Scenario</th>{outcomesCols.map((o) => <th key={o} className="text-right">{OUTCOME_STYLE[o].label}</th>)}<th className="text-right">Caught</th><th>Caught mainly by</th></tr></thead>
                <tbody>
                  {SCENARIOS.filter((s) => m[s]).map((s) => {
                    const row = m[s]; const tot = Object.values(row).reduce((a, b) => a + b, 0);
                    const flagged = tot - (row.APPROVE ?? 0);
                    const top = Object.entries(caughtRule[s] ?? {}).filter(([r]) => r !== "default").sort((a, b) => b[1] - a[1])[0];
                    return (
                      <tr key={s} className="row-link" onClick={() => nav(`/claims?injected=${s === "genuine" ? "none" : s}`)}>
                        <td>{s === "genuine" ? <span className="font-medium">Genuine claims</span> : <ScenarioBadge scenario={s} />}</td>
                        {outcomesCols.map((o) => <td key={o} className="text-right tabular-nums">{row[o] ?? <span className="text-slate-300">0</span>}</td>)}
                        <td className={`text-right tabular-nums font-medium ${s === "genuine" ? "text-slate-500" : flagged / tot > 0.8 ? "text-emerald-600" : "text-amber-600"}`}>
                          {s === "genuine" ? `${pct(flagged / tot)} flagged` : pct(flagged / tot, 0)}
                        </td>
                        <td className="text-xs text-slate-500 mono">{s === "genuine" ? "" : top?.[0] ?? "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="px-5 py-3 text-xs text-slate-500">
              {SCENARIO_LABEL.genuine} = real replayed claims. Rules and the anomaly model are complementary: duplicates and deceased members are caught
              deterministically by rules; unbundling by the anomaly score; upcoding by a rule comparing the claim to the provider's own billing history.
            </p>
          </Card>

          <Card title="Claim outcomes">
            <div className="h-56 px-2 pb-3">
              <ResponsiveContainer>
                <BarChart data={claimOut.map((o: any) => ({ ...o, label: OUTCOME_STYLE[o.outcome]?.label ?? o.outcome }))} layout="vertical" margin={{ left: 20, right: 20 }}>
                  <CartesianGrid horizontal={false} stroke="#f1f5f9" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="label" tick={{ fontSize: 12 }} width={100} />
                  <Tooltip formatter={(v) => num(Number(v))} />
                  <Bar dataKey="n" radius={[0, 4, 4, 0]}>{claimOut.map((o: any) => <Cell key={o.outcome} fill={OUTCOME_COLOR[o.outcome] ?? "#94a3b8"} />)}</Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Open review queues" icon={<Inbox size={16} className="text-amber-600" />}>
            <div className="divide-y divide-slate-100">
              {queues.length === 0 && <div className="px-5 py-6 text-sm text-slate-500">Nothing waiting for review.</div>}
              {queues.map((q: any) => (
                <Link key={q.flow + q.queue} to={`/queues?queue=${q.queue}`} className="flex items-center px-5 py-2.5 hover:bg-slate-50">
                  <div className="flex-1"><div className="text-sm font-medium">{queueLabel(q.queue)}</div>
                    <div className="text-xs text-slate-500">{q.flow === "claim" ? "Claims" : "Prior auth"} · {money(q.amount)}</div></div>
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800 tabular-nums">{q.n}</span>
                </Link>
              ))}
            </div>
          </Card>

          <Card title="Latest decisions" className="xl:col-span-2 min-w-0" actions={<Link to="/claims" className="text-xs font-normal text-brand-700 hover:underline">All claims →</Link>}>
            <div className="overflow-x-auto"><table className="tbl">
              <thead><tr><th>Time</th><th>Type</th><th>Subject</th><th className="text-right">Amount</th><th>Fraud score</th><th>Outcome</th><th>Why</th></tr></thead>
              <tbody>
                {recent.data?.items.map((r) => (
                  <tr key={r.id} className="row-link" onClick={() => nav(`/decisions/${r.id}`)}>
                    <td className="text-xs text-slate-500 tabular-nums">{time(r.created_at)}</td>
                    <td className="text-xs">{r.flow === "claim" ? "Claim" : "Prior auth"}</td>
                    <td className="mono">{r.subject_id} <ScenarioBadge scenario={r.injected} /></td>
                    <td className="text-right tabular-nums">{money(r.amount)}</td>
                    <td>{r.flow === "claim" ? <ScoreBar score={r.fraud_score} /> : <span className="block max-w-[150px] truncate text-xs text-slate-400" title={r.procedure ?? ""}>{r.procedure}</span>}</td>
                    <td><OutcomeBadge outcome={r.outcome} /></td>
                    <td className="text-xs text-slate-500 max-w-[260px] truncate">{r.reasons[0]?.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          </Card>
        </div>
      )}
    </>
  );
}

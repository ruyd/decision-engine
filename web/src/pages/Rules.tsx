import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, FlaskConical, History, Loader2, Plus, Rocket, Trash2, Undo2 } from "lucide-react";
import { api, ApiError, type Flow, type Rule, type RuleSet } from "../api";
import { Card, OutcomeBadge, PageHeader, ScenarioBadge } from "../components/ui";
import { OUTCOME_STYLE, QUEUE_LABEL, datetime, money, num, pct } from "../lib/format";

interface RulesResp {
  active: RuleSet & { version: number }; versions: { version: number; note: string; created_at: string; is_active: boolean }[];
  fire_stats: Record<string, { fired: number; evaluated: number }>; outcomes: string[]; fact_roots: string[]; sample_facts: any;
}

function FactTree({ facts }: { facts: any }) {
  if (!facts) return <div className="text-xs text-slate-500 px-5 pb-4">Run some traffic to see example facts.</div>;
  return (
    <div className="px-5 pb-4 space-y-2 max-h-[520px] overflow-auto">
      {Object.entries(facts).map(([root, v]) => (
        <div key={root}>
          <div className="mono font-semibold text-slate-800">{root}</div>
          <div className="ml-3 grid grid-cols-[auto_1fr] gap-x-3 text-[12px]">
            {Object.entries(v as object).filter(([, x]) => typeof x !== "object" || x === null || Array.isArray(x)).map(([k, x]) => (
              <div key={k} className="contents"><span className="mono text-brand-700">{root}.{k}</span>
                <span className="mono text-slate-500 truncate">{JSON.stringify(x)}</span></div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function RuleEditor({ rule, outcomes, stat, problems, onChange, onDelete }: {
  rule: Rule; outcomes: string[]; stat?: { fired: number; evaluated: number }; problems: string[];
  onChange: (r: Rule) => void; onDelete: () => void;
}) {
  const enabled = rule.enabled !== false;
  const set = (patch: Partial<Rule>) => onChange({ ...rule, ...patch });
  const setA = (patch: Partial<Rule["action"]>) => onChange({ ...rule, action: { ...rule.action, ...patch } });
  return (
    <div className={`px-5 py-3.5 ${enabled ? "" : "opacity-60"}`}>
      <div className="flex items-center gap-2">
        <label className="relative inline-flex cursor-pointer items-center" title={enabled ? "Enabled" : "Disabled"}>
          <input type="checkbox" className="peer sr-only" checked={enabled} onChange={(e) => set({ enabled: e.target.checked })} />
          <div className="h-4 w-7 rounded-full bg-slate-300 peer-checked:bg-brand-600 transition after:absolute after:left-0.5 after:top-0.5 after:h-3 after:w-3 after:rounded-full after:bg-white after:transition peer-checked:after:translate-x-3" />
        </label>
        <input className="flex-1 bg-transparent text-sm font-medium outline-none border-b border-transparent focus:border-slate-300" value={rule.name} onChange={(e) => set({ name: e.target.value })} />
        <span className="mono text-xs text-slate-400">{rule.id}</span>
        {stat && <span className="text-xs text-slate-500 tabular-nums" title="Fire rate over the last 2,000 decisions">fires {pct(stat.evaluated ? stat.fired / stat.evaluated : 0)}</span>}
        <button className="btn-ghost p-1 text-slate-400 hover:text-rose-600" onClick={onDelete} title="Delete rule"><Trash2 size={14} /></button>
      </div>
      {rule.description && <div className="ml-9 text-xs text-slate-500 mt-0.5">{rule.description}</div>}
      <div className="ml-9 mt-2 grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-2">
        <textarea rows={1} spellCheck={false} value={rule.condition} onChange={(e) => set({ condition: e.target.value })}
          className={`mono w-full rounded-lg bg-slate-900 text-slate-100 px-3 py-2 outline-none resize-y focus:ring-2 ${problems.length ? "ring-2 ring-rose-400" : "focus:ring-brand-400"}`} />
        <div className="flex gap-2 items-start">
          <select className="input" value={rule.action.outcome} onChange={(e) => setA({ outcome: e.target.value })}>
            {outcomes.map((o) => <option key={o} value={o}>{OUTCOME_STYLE[o]?.label ?? o}</option>)}
          </select>
          <select className="input" value={rule.action.queue ?? ""} onChange={(e) => setA({ queue: e.target.value })}>
            {Object.entries(QUEUE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
      </div>
      <input className="ml-9 mt-1.5 w-[calc(100%-2.25rem)] bg-transparent text-xs text-slate-600 outline-none border-b border-dashed border-slate-200 focus:border-slate-400 py-0.5"
        placeholder="Reason shown to reviewers and in the audit trail" value={rule.action.reason ?? ""} onChange={(e) => setA({ reason: e.target.value })} />
      {problems.map((p) => <div key={p} className="ml-9 mt-1 text-xs text-rose-600 flex items-center gap-1"><AlertTriangle size={12} />{p}</div>)}
    </div>
  );
}

function BacktestResult({ bt, flow }: { bt: any; flow: Flow }) {
  const s = bt.stats; const n = bt.evaluated;
  const rows = [
    { k: "Auto-approved", c: s.current.auto / n, d: s.candidate.auto / n, fmt: pct, good: "up" },
    ...(flow === "claim" ? [
      { k: "Injected fraud caught", c: s.current.flagged_fraud / Math.max(1, bt.injected_total), d: s.candidate.flagged_fraud / Math.max(1, bt.injected_total), fmt: pct, good: "up" },
      { k: "Genuine claims flagged", c: s.current.flagged_genuine / Math.max(1, n - bt.injected_total), d: s.candidate.flagged_genuine / Math.max(1, n - bt.injected_total), fmt: pct, good: "down" },
    ] : [{ k: "Sent to review / denied", c: s.current.flagged_genuine / n, d: s.candidate.flagged_genuine / n, fmt: pct, good: "neutral" }]),
    { k: "Dollars held", c: s.current.held_amount, d: s.candidate.held_amount, fmt: (v: number) => money(v), good: "neutral" },
  ];
  return (
    <Card title={`Backtest on the last ${num(n)} ${flow === "claim" ? "claims" : "requests"}`} icon={<FlaskConical size={16} className="text-brand-600" />}>
      <div className="px-5 pb-2 text-xs text-slate-500">Both rulesets re-evaluated on the stored facts (model scores included). {num(bt.changed_total)} outcomes would change.</div>
      <table className="tbl">
        <thead><tr><th>Metric</th><th className="text-right">Current</th><th className="text-right">Candidate</th><th className="text-right">Change</th></tr></thead>
        <tbody>{rows.map((r) => {
          const delta = r.d - r.c; const better = r.good === "neutral" ? null : (r.good === "up" ? delta > 0 : delta < 0);
          return (<tr key={r.k}><td>{r.k}</td><td className="text-right tabular-nums">{r.fmt(r.c)}</td><td className="text-right tabular-nums font-medium">{r.fmt(r.d)}</td>
            <td className={`text-right tabular-nums text-xs ${Math.abs(delta) < 1e-9 ? "text-slate-400" : better == null ? "text-slate-600" : better ? "text-emerald-600" : "text-rose-600"}`}>
              {Math.abs(delta) < 1e-9 ? "—" : `${delta > 0 ? "+" : "−"}${r.fmt(Math.abs(delta))}`}</td></tr>);
        })}</tbody>
      </table>
      {bt.changed.length > 0 && (
        <>
          <div className="px-5 pt-3 pb-1 label">Changed decisions (sample)</div>
          <div className="max-h-64 overflow-auto">
            <table className="tbl"><tbody>{bt.changed.slice(0, 40).map((c: any) => (
              <tr key={c.id} className="row-link" onClick={() => window.open(`/decisions/${c.id}`, "_blank")}>
                <td className="mono text-xs">{c.subject_id} <ScenarioBadge scenario={c.injected} /></td>
                <td className="text-right tabular-nums text-xs">{money(c.amount)}</td>
                <td><span className="flex items-center gap-1"><OutcomeBadge outcome={c.from} /><ArrowRight size={12} className="text-slate-400" /><OutcomeBadge outcome={c.to} /></span></td>
                <td className="text-xs text-slate-500">{c.rule}</td></tr>))}</tbody></table>
          </div>
        </>
      )}
    </Card>
  );
}

export default function Rules() {
  const qc = useQueryClient();
  const [flow, setFlow] = useState<Flow>("claim");
  const q = useQuery({ queryKey: ["rules", flow], queryFn: () => api.get<RulesResp>(`/rules/${flow}`) });
  const [draft, setDraft] = useState<RuleSet | null>(null);
  const [note, setNote] = useState("");
  useEffect(() => { if (q.data) setDraft(structuredClone({ default: q.data.active.default, rules: q.data.active.rules })); }, [q.data]);
  const dirty = useMemo(() => q.data && draft && JSON.stringify({ default: q.data.active.default, rules: q.data.active.rules }) !== JSON.stringify(draft), [q.data, draft]);

  const validate = useMutation({ mutationFn: (b: RuleSet) => api.post<{ problems: { id: string; error: string }[] }>(`/rules/${flow}/validate`, b) });
  const backtest = useMutation({ mutationFn: (b: RuleSet) => api.post<any>(`/rules/${flow}/backtest`, { ...b, limit: 3000 }) });
  const publish = useMutation({
    mutationFn: (b: RuleSet) => api.post<{ version: number }>(`/rules/${flow}/publish`, { ...b, note }),
    onSuccess: () => { setNote(""); backtest.reset(); qc.invalidateQueries(); },
  });
  const activate = useMutation({ mutationFn: (v: number) => api.post(`/rules/${flow}/activate/${v}`), onSuccess: () => qc.invalidateQueries() });

  const problemsFrom = (e: unknown) => (e instanceof ApiError ? ((e.detail as any)?.problems ?? []) : []) as { id: string; error: string }[];
  const problems = [...(validate.data?.problems ?? []), ...problemsFrom(backtest.error), ...problemsFrom(publish.error)];
  const probs = (id: string) => problems.filter((p) => p.id === id).map((p) => p.error);

  if (!q.data || !draft) return <><PageHeader title="Rules" /><div className="text-sm text-slate-500">Loading…</div></>;
  const update = (i: number, r: Rule) => setDraft({ ...draft, rules: draft.rules.map((x, j) => (j === i ? r : x)) });
  const addRule = () => setDraft({ ...draft, rules: [...draft.rules, {
    id: `rule_${draft.rules.length + 1}`, name: "New rule", enabled: true,
    condition: flow === "claim" ? "claim.total_paid > 1000 and fraud.score >= 0.95" : "request.est_cost > 5000",
    action: { outcome: flow === "claim" ? "PEND_REVIEW" : "PEND_CLINICAL", queue: flow === "claim" ? "claims_review" : "clinical_review", reason: "" } }] });

  return (
    <>
      <PageHeader title="Rules"
        subtitle="Business rules are data, not code: edit conditions in a safe expression language, backtest against recent decisions, then publish a new version. Every decision records the version it used."
        actions={
          <div className="inline-flex rounded-lg ring-1 ring-slate-300 bg-white p-0.5">
            {(["claim", "prior_auth"] as Flow[]).map((f) => (
              <button key={f} onClick={() => { setFlow(f); backtest.reset(); validate.reset(); }}
                className={`px-3 py-1 text-sm rounded-md ${flow === f ? "bg-brand-600 text-white" : "text-slate-600"}`}>{f === "claim" ? "Claims" : "Prior auth"}</button>
            ))}
          </div>
        } />
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-4 items-start">
        <div className="space-y-4">
          <Card title={<span>Active ruleset <span className="text-slate-400 font-normal">v{q.data.active.version}{dirty ? " · edited (unpublished)" : ""}</span></span>}
            actions={<button className="btn-outline" onClick={addRule}><Plus size={14} />Add rule</button>}>
            <div className="px-5 pb-2 text-xs text-slate-500">When several rules fire, the most severe outcome wins ({q.data.outcomes.slice().reverse().map((o) => OUTCOME_STYLE[o]?.label ?? o).join(" < ")}).</div>
            <div className="divide-y divide-slate-100 border-t border-slate-100">
              {draft.rules.map((r, i) => (
                <RuleEditor key={i} rule={r} outcomes={q.data.outcomes} stat={q.data.fire_stats[r.id]} problems={probs(r.id)}
                  onChange={(nr) => update(i, nr)} onDelete={() => setDraft({ ...draft, rules: draft.rules.filter((_, j) => j !== i) })} />
              ))}
              <div className="px-5 py-3 text-sm text-slate-600 bg-slate-50/60 flex items-center gap-2">
                <span className="label">If no rule fires</span><OutcomeBadge outcome={draft.default?.outcome ?? "APPROVE"} /><span className="text-xs">{draft.default?.reason}</span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-t border-slate-100">
              <button className="btn-outline" onClick={() => validate.mutate(draft)} disabled={validate.isPending}><CheckCircle2 size={14} />Validate</button>
              <button className="btn-outline" onClick={() => backtest.mutate(draft)} disabled={backtest.isPending}>
                {backtest.isPending ? <Loader2 size={14} className="animate-spin" /> : <FlaskConical size={14} />}Backtest</button>
              {dirty && <button className="btn-ghost" onClick={() => setDraft(structuredClone({ default: q.data.active.default, rules: q.data.active.rules }))}><Undo2 size={14} />Discard</button>}
              <div className="flex-1" />
              <input className="input w-72" placeholder="Change note (required to publish)" value={note} onChange={(e) => setNote(e.target.value)} />
              <button className="btn-primary" disabled={!dirty || !note || publish.isPending} onClick={() => publish.mutate(draft)}><Rocket size={14} />Publish v{q.data.active.version + 1}</button>
            </div>
            {validate.data && validate.data.problems.length === 0 && <div className="px-5 pb-3 text-xs text-emerald-600">All conditions are valid.</div>}
            {publish.data && <div className="px-5 pb-3 text-xs text-emerald-600">Published version {publish.data.version}. New decisions use it immediately.</div>}
          </Card>
          {backtest.data && <BacktestResult bt={backtest.data} flow={flow} />}
        </div>
        <div className="space-y-4">
          <Card title="Available facts (latest decision)"><FactTree facts={q.data.sample_facts} /></Card>
          <Card title="Versions" icon={<History size={16} className="text-slate-500" />}>
            <div className="divide-y divide-slate-100">
              {q.data.versions.map((v) => (
                <div key={v.version} className="px-5 py-2.5 flex items-start gap-3">
                  <span className={`mono text-sm ${v.is_active ? "font-semibold text-brand-700" : "text-slate-500"}`}>v{v.version}</span>
                  <div className="flex-1"><div className="text-sm">{v.note}</div><div className="text-xs text-slate-400">{datetime(v.created_at)}</div></div>
                  {v.is_active ? <span className="text-xs text-brand-700">active</span> :
                    <button className="text-xs text-slate-500 hover:text-brand-700" onClick={() => confirm(`Re-publish v${v.version} as a new version?`) && activate.mutate(v.version)}>restore</button>}
                </div>
              ))}
            </div>
          </Card>
          <Card title="Expression language">
            <div className="px-5 pb-4 text-xs text-slate-600 space-y-1.5">
              <div><code className="mono">and or not</code>, comparisons, <code className="mono">+ - * /</code>, <code className="mono">in [..]</code></div>
              <div>Functions: <code className="mono">abs min max len round any_prefix(list, 'pre') count_prefix(list, 'pre')</code></div>
              <div>Example: <code className="mono">any_prefix(claim.hcpcs, '7') and member.age &lt; 50</code></div>
              <div className="text-slate-400">Imports, attribute calls and private names are rejected, so rules can be edited safely from the browser.</div>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

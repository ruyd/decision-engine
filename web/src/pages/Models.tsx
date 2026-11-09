import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BrainCircuit, ExternalLink } from "lucide-react";
import { api } from "../api";
import { Card, Loading, PageHeader } from "../components/ui";
import { pct } from "../lib/format";

const LABELS: Record<string, string> = {
  ip_cost: "Inpatient cost (prior yr)", dx3_distinct: "Distinct diagnoses", ip_days: "Hospital days", esrd: "ESRD", op_cost: "Outpatient cost",
  car_claims: "Physician claims", ip_stays: "Hospital stays", rx_cost: "Drug cost", car_cost: "Physician cost", age: "Age", n_chronic: "# chronic conditions",
  n_lines_above_p95: "Lines > p95 price", dup_count: "Duplicate count", total_paid: "Total billed", lab_lines: "Lab lines",
  max_price_ratio: "Max price ratio", n_distinct_hcpcs: "Distinct codes", n_lines: "Lines", high_em_lines: "Top-level visits",
  op_claims: "Outpatient visits", rx_fills: "Rx fills", rx_distinct_ndc: "Distinct drugs", partd_months: "Part D months", state: "State",
  n_dx: "Diagnoses on claim", member_claims_30d: "Member claims (30d)", prov_known: "Provider known", prov_log_claims: "Provider volume",
  prov_lines_per_member: "Provider lines/patient", prov_paid_per_line: "Provider $/line", prov_high_em_share: "Provider top-visit share",
  prov_lab_share: "Provider lab share", prov_distinct_hcpcs: "Provider distinct codes", sp_chrnkidn: "Chronic kidney disease", sp_chf: "Heart failure",
};

const KEY_METRICS: Record<string, [string, string, (v: number) => string][]> = {
  next_year_cost: [["valid_r2", "R² (held-out)", (v) => v.toFixed(3)], ["valid_gini_norm", "Gini (ranking)", (v) => v.toFixed(3)],
    ["valid_top10_capture", "Cost in predicted top 10%", (v) => pct(v, 0)], ["test_predictive_ratio", "2010 pred/actual (drift)", (v) => v.toFixed(2)]],
  claim_fraud: [["auc_unbundling", "AUC unbundling", (v) => v.toFixed(3)], ["auc_upcoding", "AUC upcoding", (v) => v.toFixed(3)],
    ["auc_duplicate", "AUC duplicate", (v) => v.toFixed(3)], ["auc_price_inflation", "AUC price inflation", (v) => v.toFixed(3)],
    ["normal_flag_rate_at_0.99", "Normal claims ≥ 0.99", (v) => pct(v)], ["recall_all_at_0.99", "Fraud recall ≥ 0.99 (model alone)", (v) => pct(v, 0)]],
};

export default function Models() {
  const q = useQuery({ queryKey: ["models"], queryFn: () => api.get<any[]>("/models") });
  if (!q.data) return <Loading />;
  return (
    <>
      <PageHeader title="Models" subtitle="Champion models are loaded from the MLflow registry at startup; every decision records the versions it used." />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {q.data.map((m) => {
          const imp = Object.entries(m.importance as Record<string, number>).slice(0, 10).map(([k, v]) => ({ k: LABELS[k] ?? k, v }));
          return (
            <Card key={m.name} title={<span className="flex items-center gap-2">{m.title} <span className="mono text-xs font-normal text-slate-500">{m.name} v{m.version}</span></span>}
              icon={<BrainCircuit size={16} className="text-brand-600" />}
              actions={<a href={m.mlflow_url} target="_blank" rel="noreferrer" className="text-xs font-normal text-brand-700 hover:underline inline-flex items-center gap-1">MLflow <ExternalLink size={11} /></a>}>
              <div className="px-5 pb-3 text-sm text-slate-600">{m.purpose}</div>
              <div className="px-5 pb-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500"><span>{m.kind}</span><span>Explained by {m.explainer}</span></div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 px-5 pb-4">
                {KEY_METRICS[m.name].filter(([k]) => m.metrics[k] != null).map(([k, label, fmt]) => (
                  <div key={k} className="rounded-lg bg-slate-50 px-3 py-2"><div className="text-[11px] text-slate-500">{label}</div><div className="text-lg font-semibold tabular-nums">{fmt(m.metrics[k])}</div></div>
                ))}
              </div>
              <div className="px-5 label">{m.name === "claim_fraud" ? "Mean |SHAP| on injected fraud" : "Permutation importance (drop in R²)"}</div>
              <div className="h-64 px-2 pb-3">
                <ResponsiveContainer>
                  <BarChart data={imp} layout="vertical" margin={{ left: 30, right: 20 }}>
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="k" width={170} tick={{ fontSize: 11 }} interval={0} />
                    <Tooltip formatter={(v) => Number(v).toFixed(4)} />
                    <Bar dataKey="v" fill="#14b8a6" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          );
        })}
      </div>
    </>
  );
}

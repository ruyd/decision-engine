import { useState } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "../api";
import { Card, Empty, Loading, PageHeader, TierBadge } from "../components/ui";
import { TIER_STYLE, money, num } from "../lib/format";

export default function Members() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [tier, setTier] = useState("");
  const data = useQuery({
    queryKey: ["members", q, tier],
    queryFn: () => api.get<any>(`/members?limit=100${q ? `&q=${encodeURIComponent(q)}` : ""}${tier ? `&tier=${encodeURIComponent(tier)}` : ""}`),
  });
  const tiers: any[] = data.data?.tiers ?? [];
  return (
    <>
      <PageHeader title="Members" subtitle="573k members (SynPUF samples 1–5) scored by the next-year cost model. Risk tiers feed prior-auth and care-management rules." />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        {["Low", "Moderate", "High", "Very high"].map((t) => {
          const r = tiers.find((x) => x.risk_tier === t);
          return (
            <button key={t} onClick={() => setTier(tier === t ? "" : t)}
              className={`card px-4 py-3 text-left transition ${tier === t ? "ring-2 ring-brand-500" : "hover:shadow-md"}`}>
              <span className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${TIER_STYLE[t]}`}>{t} risk</span>
              <div className="mt-1.5 text-xl font-semibold tabular-nums">{r ? num(r.n) : "—"}</div>
              <div className="text-xs text-slate-500">avg predicted {r ? money(r.avg_cost) : "—"} / yr</div>
            </button>
          );
        })}
      </div>
      <Card>
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100">
          <div className="relative"><Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
            <input className="input pl-8 w-72 mono" placeholder="Member id prefix" onKeyDown={(e) => e.key === "Enter" && setQ((e.target as HTMLInputElement).value.trim())} /></div>
          <span className="text-xs text-slate-500">{tier ? `${tier} risk · ` : ""}sorted by predicted cost</span>
        </div>
        {!data.data ? <Loading /> : data.data.items.length === 0 ? <Empty>No members found.</Empty> : (
          <table className="tbl">
            <thead><tr><th>Member</th><th>Age</th><th>Sex</th><th>State</th><th className="text-right">Chronic conditions</th><th className="text-right">2009 cost</th><th className="text-right">Predicted 2010</th><th>Risk</th></tr></thead>
            <tbody>
              {data.data.items.map((m: any) => (
                <tr key={m.member_id} className="row-link" onClick={() => nav(`/members/${m.member_id}`)}>
                  <td className="mono text-brand-700">{m.member_id}{m.death_date && <span className="ml-2 text-[11px] text-rose-600">† {m.death_date}</span>}</td>
                  <td className="tabular-nums">{m.age}</td><td>{m.sex === 1 ? "M" : "F"}</td><td className="tabular-nums">{m.state}</td>
                  <td className="text-right tabular-nums">{m.n_chronic}</td>
                  <td className="text-right tabular-nums text-slate-500">{money(m.cost_2009)}</td>
                  <td className="text-right tabular-nums font-medium">{money(m.predicted_cost)}</td>
                  <td><TierBadge tier={m.risk_tier} /> <span className="text-xs text-slate-400 tabular-nums">p{Math.round(m.risk_pct)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}

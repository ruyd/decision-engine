import { useNavigate, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { api, type DecisionRow } from "../api";
import { Card, Empty, Loading, MemberLink, OutcomeBadge, PageHeader, ScenarioBadge, ScoreBar, TierBadge, queueLabel } from "../components/ui";
import { money, time } from "../lib/format";

export default function Queues() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [sp, setSp] = useSearchParams();
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<any>("/dashboard") });
  const queues: any[] = dash.data?.queues ?? [];
  const active = sp.get("queue") ?? queues[0]?.queue ?? "";
  const list = useQuery({
    queryKey: ["decisions", "queue", active], enabled: !!active,
    queryFn: () => api.get<{ total: number; items: DecisionRow[] }>(`/decisions?review_status=open&queue=${active}&limit=100`),
  });
  const review = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "approve" | "deny" }) => api.post(`/decisions/${id}/review`, { action, note: "Quick action from queue" }),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <>
      <PageHeader title="Review queues" subtitle="Work the engine routed to people. Reviewer outcomes are stored next to the automated decision, ready to become training labels." />
      {!dash.data ? <Loading /> : queues.length === 0 ? <Card><Empty>All queues are empty.</Empty></Card> : (
        <>
          <div className="flex flex-wrap gap-2 mb-3">
            {queues.map((q) => (
              <button key={q.flow + q.queue} onClick={() => setSp({ queue: q.queue })}
                className={`rounded-lg px-3 py-2 text-left ring-1 transition ${active === q.queue ? "bg-white ring-brand-500 shadow-sm" : "bg-white/60 ring-slate-200 hover:bg-white"}`}>
                <div className="text-sm font-medium">{queueLabel(q.queue)}</div>
                <div className="text-xs text-slate-500">{q.n} open · {money(q.amount)}</div>
              </button>
            ))}
          </div>
          <Card>
            {!list.data ? <Loading /> : list.data.items.length === 0 ? <Empty>Nothing open in this queue.</Empty> : (
              <table className="tbl">
                <thead><tr><th>Received</th><th>Subject</th><th>Member</th><th className="text-right">Amount</th><th>Signal</th><th>Engine outcome</th><th>Reason</th><th className="text-right">Resolve</th></tr></thead>
                <tbody>
                  {list.data.items.map((r) => (
                    <tr key={r.id} className="row-link" onClick={() => nav(`/decisions/${r.id}`)}>
                      <td className="text-xs text-slate-500 tabular-nums">{time(r.created_at)}</td>
                      <td className="mono whitespace-nowrap">{r.subject_id} <ScenarioBadge scenario={r.injected} /></td>
                      <td><MemberLink id={r.member_id} /></td>
                      <td className="text-right tabular-nums">{money(r.amount)}</td>
                      <td>{r.flow === "claim" ? <ScoreBar score={r.fraud_score} /> : <TierBadge tier={r.risk_tier} />}</td>
                      <td><OutcomeBadge outcome={r.outcome} /></td>
                      <td className="text-xs text-slate-500 max-w-[300px] truncate" title={r.reasons[0]?.reason}>{r.reasons[0]?.reason}</td>
                      <td className="text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                        <button className="btn-ghost text-emerald-700" title="Approve" onClick={() => review.mutate({ id: r.id, action: "approve" })}><Check size={15} /></button>
                        <button className="btn-ghost text-rose-700" title="Deny" onClick={() => review.mutate({ id: r.id, action: "deny" })}><X size={15} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      )}
    </>
  );
}

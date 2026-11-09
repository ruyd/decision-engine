import { NavLink, Outlet } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Activity, BrainCircuit, ClipboardCheck, FileText, Inbox, LayoutDashboard, ListChecks, Users } from "lucide-react";
import { api } from "../api";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/claims", label: "Claims", icon: FileText },
  { to: "/prior-auth", label: "Prior authorization", icon: ClipboardCheck },
  { to: "/queues", label: "Review queues", icon: Inbox },
  { to: "/members", label: "Members", icon: Users },
  { to: "/rules", label: "Rules", icon: ListChecks },
  { to: "/models", label: "Models", icon: BrainCircuit },
];

interface Meta { company: string; today: string; models: Record<string, string>; rulesets: Record<string, number> }

export default function Layout() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api.get<Meta>("/meta") });
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<any>("/dashboard"), refetchInterval: 15000 });
  const open = dash.data?.totals?.open_reviews ?? 0;
  return (
    <div className="flex h-full">
      <aside className="w-60 shrink-0 bg-ink-900 text-slate-300 flex flex-col">
        <div className="px-5 pt-5 pb-4 border-b border-white/5">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-brand-600 grid place-items-center"><Activity size={18} className="text-white" /></div>
            <div className="leading-tight">
              <div className="text-white font-semibold text-[15px]">{meta.data?.company ?? "Ridgeline Health Plan"}</div>
              <div className="text-[11px] text-slate-400">Decision Engine</div>
            </div>
          </div>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition ${
                isActive ? "bg-white/10 text-white" : "hover:bg-white/5 hover:text-white"}`}>
              <Icon size={16} />
              <span className="flex-1">{label}</span>
              {to === "/queues" && open > 0 && (
                <span className="rounded-full bg-amber-500/90 px-1.5 text-[11px] font-semibold text-ink-900 tabular-nums">{open}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="px-5 py-4 border-t border-white/5 text-[11px] text-slate-400 space-y-1">
          <div>Simulated date <span className="text-slate-200">{meta.data?.today ?? "—"}</span></div>
          <div>Rules: claims v{meta.data?.rulesets?.claim ?? "–"} · PA v{meta.data?.rulesets?.prior_auth ?? "–"}</div>
          <div>Models: cost v{meta.data?.models?.next_year_cost ?? "–"} · fraud v{meta.data?.models?.claim_fraud ?? "–"}</div>
          <div className="pt-1 text-slate-500">Fictional insurer · CMS DE-SynPUF synthetic data</div>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1400px] px-6 py-6"><Outlet /></div>
      </main>
    </div>
  );
}

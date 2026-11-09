import { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, CircleSlash, XCircle } from "lucide-react";
import type { Explanation, TraceEntry } from "../api";
import { money } from "../lib/format";
import { OutcomeBadge, queueLabel } from "./ui";

/** Horizontal SHAP bars: red pushes toward the risky/expensive side, blue pushes away. */
export function ShapBars({ expl, top = 10, dollars = false }: { expl: Explanation; top?: number; dollars?: boolean }) {
  const [all, setAll] = useState(false);
  const items = all ? expl.contributions : expl.contributions.slice(0, top);
  const max = Math.max(...expl.contributions.map((c) => Math.abs(c.contribution)), 1e-9);
  const fmtV = (v: number) => (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : Number.isInteger(v) ? v : v.toFixed(2));
  return (
    <div className="px-5 pb-4">
      <div className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,2fr)_72px] gap-x-3 gap-y-1.5 items-center text-[13px]">
        {items.map((c) => {
          const w = (Math.abs(c.contribution) / max) * 50;
          const pos = c.contribution > 0;
          return (
            <div key={c.feature} className="contents">
              <div className="truncate text-slate-700" title={c.label}>
                {c.label} <span className="text-slate-400 tabular-nums">= {fmtV(c.value)}</span>
              </div>
              <div className="relative h-4">
                <div className="absolute left-1/2 top-0 bottom-0 w-px bg-slate-200" />
                <div className={`absolute top-0.5 bottom-0.5 rounded-sm ${pos ? "bg-rose-400" : "bg-sky-400"}`}
                  style={pos ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }} />
              </div>
              <div className={`text-right tabular-nums text-xs ${pos ? "text-rose-600" : "text-sky-600"}`}>
                {pos ? "+" : "−"}{dollars ? money(Math.abs(c.contribution)) : Math.abs(c.contribution).toFixed(3)}
              </div>
            </div>
          );
        })}
      </div>
      {expl.contributions.length > top && (
        <button className="mt-2 text-xs text-brand-700 hover:underline" onClick={() => setAll(!all)}>
          {all ? "Show top factors" : `Show all ${expl.contributions.length} factors`}
        </button>
      )}
    </div>
  );
}

export function CostWaterfallSummary({ expl }: { expl: Explanation }) {
  const up = expl.contributions.filter((c) => c.contribution > 0).reduce((a, c) => a + c.contribution, 0);
  const down = expl.contributions.filter((c) => c.contribution < 0).reduce((a, c) => a + c.contribution, 0);
  return (
    <div className="px-5 pb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      <span className="text-slate-500">Average member</span>
      <span className="font-semibold tabular-nums">{money(expl.base_value)}</span>
      <span className="text-rose-600 tabular-nums">+ {money(up)}</span>
      <span className="text-sky-600 tabular-nums">− {money(Math.abs(down))}</span>
      <span className="text-slate-400">=</span>
      <span className="font-semibold text-slate-900 tabular-nums">{money(expl.prediction)}</span>
      <span className="text-slate-500">predicted next year</span>
    </div>
  );
}

export function ScoreGauge({ score }: { score: number }) {
  const zones = [
    { to: 0.98, cls: "bg-slate-200", label: "Normal" },
    { to: 0.995, cls: "bg-amber-300", label: "Elevated (top 2%)" },
    { to: 1, cls: "bg-violet-400", label: "Extreme (top 0.5%)" },
  ];
  const zone = zones.find((z) => score < z.to) ?? zones[2];
  // stretch the top of the scale so the interesting region is visible
  const pos = (s: number) => (s < 0.9 ? (s / 0.9) * 60 : 60 + ((s - 0.9) / 0.1) * 40);
  return (
    <div className="px-5 pb-4">
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-semibold tabular-nums">{(score * 100).toFixed(1)}</span>
        <span className="text-sm text-slate-500">percentile vs. normal claims · {zone.label}</span>
      </div>
      <div className="relative mt-3 h-2.5 rounded-full overflow-hidden flex">
        <div className="bg-slate-200" style={{ width: `${pos(0.98)}%` }} />
        <div className="bg-amber-300" style={{ width: `${pos(0.995) - pos(0.98)}%` }} />
        <div className="bg-violet-400 flex-1" />
      </div>
      <div className="relative h-4">
        <div className="absolute -top-3.5 h-4 w-0.5 bg-slate-900 rounded" style={{ left: `calc(${pos(score)}% - 1px)` }} />
      </div>
      <div className="relative h-3 text-[10px] text-slate-400 -mt-1">
        {[0, 0.9, 0.98, 0.995].map((t) => (
          <span key={t} className="absolute -translate-x-1/2 tabular-nums" style={{ left: `${pos(t)}%` }}>{+(t * 100).toFixed(1)}</span>
        ))}
      </div>
    </div>
  );
}

function fmtVal(v: unknown): string {
  if (v == null) return "null";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  if (Array.isArray(v)) return `[${v.slice(0, 6).map((x) => JSON.stringify(x)).join(", ")}${v.length > 6 ? ", …" : ""}]`;
  return JSON.stringify(v);
}

export function RuleTrace({ trace }: { trace: TraceEntry[] }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  return (
    <div className="divide-y divide-slate-100">
      {trace.map((t) => {
        const isOpen = open[t.id] ?? t.matched;
        const Icon = !t.enabled ? CircleSlash : t.matched ? CheckCircle2 : XCircle;
        return (
          <div key={t.id} className={`px-5 py-2.5 ${t.matched ? "bg-amber-50/40" : ""}`}>
            <button className="w-full flex items-center gap-2 text-left" onClick={() => setOpen({ ...open, [t.id]: !isOpen })}>
              {isOpen ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
              <Icon size={16} className={!t.enabled ? "text-slate-300" : t.matched ? "text-amber-600" : "text-slate-300"} />
              <span className={`text-sm ${t.matched ? "font-medium text-slate-900" : "text-slate-600"}`}>{t.name}</span>
              {!t.enabled && <span className="text-xs text-slate-400">disabled</span>}
              {t.error && <span className="text-xs text-rose-600">error</span>}
              <span className="ml-auto flex items-center gap-2">
                {t.matched && <OutcomeBadge outcome={t.action.outcome} />}
                <span className="text-xs text-slate-400 hidden md:inline">{queueLabel(t.action.queue)}</span>
              </span>
            </button>
            {isOpen && (
              <div className="ml-10 mt-2 space-y-1.5">
                <code className="block mono rounded bg-slate-900 text-slate-100 px-2.5 py-1.5 whitespace-pre-wrap">{t.condition}</code>
                {Object.keys(t.values).length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(t.values).map(([k, v]) => (
                      <span key={k} className="mono rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">{k} = <b>{fmtVal(v)}</b></span>
                    ))}
                  </div>
                )}
                {t.error && <div className="text-xs text-rose-600">{t.error}</div>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

"use client";
// Battery health at a glance: SOH (how big the battery still is), SOC (how full it is now),
// cycles used against what it's rated for, when it reaches the 80% line, what the heat costs,
// and a resale grade. The full story is on the battery report page.
import Link from "next/link";
import type { BatteryReport } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Failed, Loading } from "../Section";

export function Gauge({ percent, size = "max-w-[220px]" }: { percent: number; size?: string }) {
  const angle = (p: number) => Math.PI * (1 - (Math.min(100, Math.max(50, p)) - 50) / 50);
  const pt = (p: number, r: number) => [100 + r * Math.cos(angle(p)), 100 - r * Math.sin(angle(p))];
  const arc = (from: number, to: number) => {
    const [x0, y0] = pt(from, 80), [x1, y1] = pt(to, 80);
    return `M${x0} ${y0} A80 80 0 0 1 ${x1} ${y1}`;
  };
  const [tx0, ty0] = pt(80, 68), [tx1, ty1] = pt(80, 92);
  const [lx, ly] = pt(80, 106);
  const color = percent >= 90 ? "#1e9e6a" : percent >= 80 ? "#c9a400" : "#c93636";
  return (
    <svg viewBox="0 -16 200 134" className={`w-full ${size}`} role="img" aria-label={`Battery health ${percent}%`}>
      <path d={arc(50, 100)} stroke="#e3e8ee" strokeWidth="16" fill="none" strokeLinecap="round" />
      <path d={arc(50, percent)} stroke={color} strokeWidth="16" fill="none" strokeLinecap="round" />
      <path d={`M${tx0} ${ty0} L${tx1} ${ty1}`} stroke="#16233f" strokeWidth="2.5" />
      <text x={lx} y={ly} fontSize="10" fill="#5e6b80" textAnchor="middle">80% line</text>
      <text x="100" y="94" textAnchor="middle" fontSize="32" fontWeight="700" fill="#16233f">{percent}%</text>
      <text x="100" y="112" textAnchor="middle" fontSize="10.5" fill="#5e6b80">SOH: size left vs new</text>
    </svg>
  );
}

export const GRADE_COLOUR = { A: "bg-charge", B: "bg-[#c9a400]", C: "bg-warn", D: "bg-alarm" } as const;
export const monthYear = (ts: string | null) => ts ? new Date(ts).toLocaleDateString("en-NG", { month: "short", year: "numeric" }) : "–";

function Bar({ label, value, max, text, tone }: { label: string; value: number; max: number; text: string; tone: string }) {
  return (
    <div>
      <div className="flex justify-between text-sm"><span className="text-muted">{label}</span><span className="font-semibold">{text}</span></div>
      <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-sky"><div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.min(100, (100 * value) / max)}%` }} /></div>
    </div>
  );
}

export function BatteryHealth({ code }: { code: string }) {
  const { data: r, error, loading } = useApi<BatteryReport>(`/api/sites/${code}/views/battery_report`);
  return (
    <section className="rounded-3xl bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold">Battery health</h2>
          {r && <p className="text-sm text-muted">{r.nameplate_kwh} kWh {r.chemistry}{r.age_years !== undefined ? `, ${r.age_years} years old` : ""}</p>}
        </div>
        {r?.measured && <span title={r.grade_text} className={`grid h-11 w-11 place-items-center rounded-full font-display text-xl font-bold text-white ${GRADE_COLOUR[r.grade]}`}>{r.grade}</span>}
      </div>
      {loading && <Loading what="battery health" />}
      {error && <Failed message={error} />}
      {r && (
        <div className="mt-3 grid gap-5 sm:grid-cols-[200px_1fr] sm:items-center">
          {r.soh_percent !== null ? <Gauge percent={r.soh_percent} /> : <p className="text-sm text-muted">SOH not measured yet: it needs a few nights where the battery drops by 30% or more.</p>}
          <div className="space-y-3">
            {r.soc_percent !== null && <Bar label="SOC: charged right now" value={r.soc_percent} max={100} text={`${r.soc_percent}%`} tone="bg-charge" />}
            <Bar label="Cycles used" value={r.cycles} max={r.rated_cycles} text={`${r.cycles.toLocaleString()} of ~${r.rated_cycles.toLocaleString()}`} tone="bg-nepa" />
            <dl className="grid grid-cols-2 gap-3 pt-1 text-sm">
              <div><dt className="text-muted">Reaches 80% around</dt><dd className="font-semibold">{monthYear(r.reaches_80_at)}</dd></div>
              <div><dt className="text-muted">Heat is costing (vs 25°C)</dt><dd className={`font-semibold ${(r.life_lost_to_heat_months ?? 0) >= 3 ? "text-[#d9480f]" : ""}`}>{r.life_lost_to_heat_months ? `${r.life_lost_to_heat_months} months of life` : "under a month"}</dd></div>
              <div><dt className="text-muted">Losing per year</dt><dd className="font-semibold">{r.fade_per_year_percent}% <span className="font-normal text-muted">(normal 2–5%)</span></dd></div>
              <div><dt className="text-muted">Replace around</dt><dd className="font-semibold">{monthYear(r.replace_around)}</dd></div>
            </dl>
          </div>
        </div>
      )}
      {r?.measured && <p className="mt-4 rounded-2xl bg-sky px-4 py-3 text-sm"><strong>Grade {r.grade}:</strong> {r.grade_text}</p>}
      {r?.soh_percent !== null && r?.soh_percent !== undefined && r.soh_percent < 80 && (
        <p className="mt-3 text-sm text-warn">Below the usual 80% warranty line: ask your installer about a warranty claim.</p>
      )}
      <Link href={`/report/${code}`} className="mt-4 inline-flex rounded-full bg-ink px-4 py-2 text-sm font-semibold text-sky">Open the full battery report</Link>
    </section>
  );
}

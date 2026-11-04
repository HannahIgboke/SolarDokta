"use client";
// The technician's fleet screens, one per tab: Overview (what needs doing today), Map (problems,
// El Niño heat risk or NEPA hours), Sites (the full table). They share one /api/fleet load.
import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import type { Fleet as FleetData, FleetSite } from "@/lib/types";
import { kw } from "@/lib/useApi";
import { pinColour, type MapLayer } from "./fleetColours";

const FleetMap = dynamic(() => import("./FleetMap"), { ssr: false, loading: () => <div className="h-full min-h-[380px] animate-pulse bg-line/40" /> });

type SortKey = "urgency" | "battery" | "name" | "heat" | "light";

export function urgency(s: FleetSite): number {          // lower = visit sooner
  if (!s.online) return 0;
  if (s.worst === "critical") return 1;
  if (s.blackouts_7d.count >= 3) return 2;
  if (s.heat.risk === "high") return 3;
  if (s.worst === "warning") return 4;
  if (s.heat.risk === "medium") return 5;
  return 9;
}

function reason(s: FleetSite): { why: string; todo: string } {
  if (!s.online) return { why: `No readings for ${s.minutes_since_reading === null ? "a long time" : `${Math.round(s.minutes_since_reading / 60)} h`}`, todo: "Check the Link box and the customer's Wi-Fi/SIM" };
  if (s.worst === "critical") return { why: s.problems.map((p) => p.replaceAll("_", " ")).join(", "), todo: s.problems.includes("string_failure") ? "Bring a multimeter and MC4 connectors" : "Visit today" };
  if (s.blackouts_7d.count >= 3) return { why: `Ran out of power ${s.blackouts_7d.count} times this week (${s.blackouts_7d.hours} h)`, todo: "Talk about battery size or night-time loads" };
  if (s.heat.risk === "high") return { why: `Battery room averages ${s.heat.battery_avg_c}°C, ageing ${s.heat.ageing_speed}× normal`, todo: "Ventilate or move the battery" };
  if (s.worst === "warning") return { why: s.problems.map((p) => p.replaceAll("_", " ")).join(", "), todo: "Plan a visit this week" };
  if (s.heat.risk === "medium") return { why: `Warm battery room (${s.heat.battery_avg_c}°C)`, todo: "Mention ventilation on the next call" };
  return { why: "All good", todo: "" };
}

function Kpi({ label, value, note, tone = "" }: { label: string; value: string | number; note?: string; tone?: string }) {
  return (
    <div className="rounded-3xl bg-white p-5">
      <p className="text-sm text-muted">{label}</p>
      <p className={`mt-1 font-display text-4xl font-bold ${tone}`}>{value}</p>
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
    </div>
  );
}

const LAYERS: { id: MapLayer; label: string; legend: [string, string][] }[] = [
  { id: "problems", label: "Problems", legend: [["#c93636", "Urgent"], ["#e8890c", "Warning"], ["#1e9e6a", "OK"], ["#8a96a8", "Offline"]] },
  { id: "heat", label: "El Niño heat", legend: [["#d9480f", "Ageing 2× or more"], ["#f59f00", "Warm"], ["#1e9e6a", "Cool"]] },
  { id: "light", label: "NEPA hours", legend: [["#c93636", "Under 4 h/day"], ["#f59f00", "4–8 h"], ["#4c6ef5", "8 h or more"]] },
];


export function MapLegend({ layer, setLayer }: { layer: MapLayer; setLayer: (l: MapLayer) => void }) {
  const active = LAYERS.find((l) => l.id === layer)!;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div role="radiogroup" aria-label="What the map shows" className="inline-flex rounded-full bg-sky p-1">
        {LAYERS.map((l) => (
          <button key={l.id} role="radio" aria-checked={layer === l.id} onClick={() => setLayer(l.id)}
                  className={`rounded-full px-3.5 py-1.5 text-sm font-semibold ${layer === l.id ? "bg-ink text-sky" : "text-muted hover:text-ink"}`}>{l.label}</button>
        ))}
      </div>
      <ul className="flex flex-wrap gap-3 text-xs text-muted">
        {active.legend.map(([c, label]) => <li key={label} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />{label}</li>)}
      </ul>
    </div>
  );
}

function VisitFirst({ sites, limit = 6 }: { sites: FleetSite[]; limit?: number }) {
  const work = [...sites].sort((a, b) => urgency(a) - urgency(b)).filter((s) => urgency(s) < 9);
  if (work.length === 0) return <p className="mt-6 text-muted">Nothing needs a visit. Good time for preventive calls.</p>;
  return (
    <ol className="mt-4 space-y-3">
      {work.slice(0, limit).map((s, i) => {
        const r = reason(s);
        return (
          <li key={s.code}>
            <Link href={`/staff/sites/${s.code}`} className="flex gap-3 rounded-2xl border border-line p-3 hover:border-ink">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold text-white" style={{ background: pinColour(s, "problems") }}>{i + 1}</span>
              <span className="min-w-0">
                <span className="block font-semibold">{s.name}</span>
                <span className="block text-sm first-letter:uppercase">{r.why}</span>
                {r.todo && <span className="block text-sm text-muted">{r.todo}</span>}
              </span>
            </Link>
          </li>
        );
      })}
    </ol>
  );
}

export function FleetOverview({ data, name, onTab }: { data: FleetData; name?: string | null; onTab: (t: string) => void }) {
  const t = data.totals;
  const hot = data.sites.filter((s) => s.heat.risk !== "low").length;
  const h = new Date().getHours();
  return (
    <div className="space-y-6">
      <div>
        <p className="text-muted">{h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"}{name ? `, ${name.split(" ")[0]}` : ""}</p>
        <h1 className="mt-1 font-display text-3xl font-semibold md:text-4xl">
          {t.need_visit ? `${t.need_visit} of your ${t.sites} sites need a visit today.` : `All ${t.sites} sites are fine right now.`}
        </h1>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi label="Need a visit today" value={t.need_visit} tone={t.need_visit ? "text-alarm" : "text-charge"} note="critical findings or offline Links" />
        <Kpi label="Customer downtime" value={`${t.blackout_hours_7d} h`} tone={t.blackout_hours_7d ? "text-warn" : ""} note="battery hit cut-off, all sites, 7 d" />
        <Kpi label="Batteries in heat danger" value={t.heat_risk_sites} tone={t.heat_risk_sites ? "text-[#d9480f]" : ""} note="ageing ≥ 2× (Arrhenius)" />
        <Kpi label="Grid availability" value={`${t.light_hours_avg} h`} tone="text-nepa" note="NEPA hours/day, 7-day mean" />
        <Kpi label="Links reporting" value={`${t.online}/${t.sites}`} tone={t.online < t.sites ? "text-warn" : "text-charge"} note={`PV now ${t.solar_now_kw} kW`} />
      </div>
      <div className="flex flex-col gap-3 rounded-3xl bg-gradient-to-r from-[#b4400f] to-[#7a2913] p-5 text-white sm:flex-row sm:items-center">
        <p className="font-display text-lg font-semibold sm:w-56 sm:shrink-0">Super El Niño season</p>
        <p className="flex-1 text-white/85">
          {hot ? `${hot} of your ${t.sites} sites have warm or hot battery rooms. Heat is the main thing shortening battery life until early 2027: prioritise ventilation, shade and moving batteries out of sealed stores.`
            : "No battery rooms are running hot yet. Heat will stay above normal until early 2027, so keep watching."}
        </p>
        <button onClick={() => onTab("map:heat")} className="shrink-0 rounded-full bg-white px-4 py-2 text-sm font-semibold text-[#7a2913]">See heat on the map</button>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <section className="rounded-3xl bg-white p-5">
          <h2 className="font-display text-xl font-semibold">Visit first</h2>
          <p className="text-sm text-muted">Ranked by how soon each site needs you.</p>
          <VisitFirst sites={data.sites} />
        </section>
        <section className="grid content-start gap-3">
          {[
            ["map", "Map", "Problems, El Niño heat and NEPA hours by location"],
            ["sites", "All sites", "SOC, SOH, PV, grid hours, blackouts and heat in one table"],
            ["problems", "Problems inbox", "Resolve or dismiss findings with a note"],
            ["whatif", "What-if lab", "Stress-test any site: NEPA collapse, heatwave, new loads"],
            ["ask", "Ask Dokta", "Questions across the whole fleet"],
          ].map(([id, title, note]) => (
            <button key={id} onClick={() => onTab(id)} className="flex items-center justify-between rounded-2xl bg-white px-5 py-4 text-left hover:ring-2 hover:ring-ink">
              <span><span className="block font-semibold">{title}</span><span className="text-sm text-muted">{note}</span></span>
              <svg viewBox="0 0 12 12" className="h-4 w-4 text-muted" aria-hidden="true"><path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.8" /></svg>
            </button>
          ))}
        </section>
      </div>
    </div>
  );
}

export function FleetMapTab({ data, layer, setLayer }: { data: FleetData; layer: MapLayer; setLayer: (l: MapLayer) => void }) {
  return (
    <div className="grid gap-5 xl:grid-cols-[1.7fr_1fr]">
      <section className="overflow-hidden rounded-3xl bg-white">
        <div className="px-5 pt-4 pb-3"><MapLegend layer={layer} setLayer={setLayer} /></div>
        <div className="h-[560px]"><FleetMap sites={data.sites} layer={layer} /></div>
      </section>
      <section className="rounded-3xl bg-white p-5">
        <h2 className="font-display text-xl font-semibold">Visit first</h2>
        <p className="text-sm text-muted">Tap a pin for details, or a site to open it.</p>
        <VisitFirst sites={data.sites} limit={8} />
      </section>
    </div>
  );
}

export function FleetTable({ data }: { data: FleetData }) {
  const [sort, setSort] = useState<SortKey>("urgency");
  const sites = [...data.sites].sort((a, b) =>
    sort === "urgency" ? urgency(a) - urgency(b)
      : sort === "battery" ? (a.battery ?? 101) - (b.battery ?? 101)
        : sort === "heat" ? (b.heat.ageing_speed ?? 0) - (a.heat.ageing_speed ?? 0)
          : sort === "light" ? (a.light_hours_7d ?? 99) - (b.light_hours_7d ?? 99)
            : a.name.localeCompare(b.name));
  const th = (k: SortKey, label: string) => (
    <th className="px-3 py-3 text-left font-medium">
      <button onClick={() => setSort(k)} className={sort === k ? "text-ink underline" : "hover:text-ink"}>{label}</button>
    </th>
  );
  return (
    <div className="overflow-x-auto rounded-3xl bg-white">
      <table className="w-full min-w-[1120px] text-sm [&_td]:whitespace-nowrap">
        <thead className="border-b border-line text-muted">
          <tr>{th("urgency", "Status")}{th("name", "Site")}
            <th className="px-3 py-3 text-left font-medium">Link</th>
            {th("battery", "SOC")}
            <th className="px-3 py-3 text-left font-medium">PV / load</th>
            {th("light", "Grid h/day")}
            <th className="px-3 py-3 text-left font-medium">Blackouts (7 d)</th>
            {th("heat", "Battery temp / ageing")}
            <th className="px-3 py-3 text-left font-medium">SOH</th>
            <th className="px-3 py-3 text-left font-medium">Open findings</th></tr>
        </thead>
        <tbody>
          {sites.map((s) => (
            <tr key={s.code} className="border-b border-line last:border-0 hover:bg-sky/60">
              <td className="px-3 py-3"><span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: pinColour(s, "problems") }} />
                <span className="ml-2">{!s.online ? "Offline" : s.worst === "critical" ? "Urgent" : s.worst ? "Attention" : "OK"}</span></td>
              <td className="px-3 py-3"><Link href={`/staff/sites/${s.code}`} className="font-semibold hover:underline">{s.name}</Link>
                <span className="block text-xs text-muted">{s.code}, {s.city}{s.simulated ? ", simulated" : ""}</span></td>
              <td className="px-3 py-3">{s.online ? <span className="text-charge">online</span> : <span className="text-alarm">no signal</span>}
                <span className="block text-xs text-muted">{s.minutes_since_reading === null ? "never" : s.minutes_since_reading < 60 ? `${s.minutes_since_reading} min ago` : `${Math.round(s.minutes_since_reading / 60)} h ago`}</span></td>
              <td className="px-3 py-3">{s.battery !== undefined ? `${s.battery}%` : "–"}</td>
              <td className="px-3 py-3">{s.solar_w !== undefined ? `${kw(s.solar_w)} / ${kw(s.house_w ?? 0)}` : "–"}</td>
              <td className="px-3 py-3" style={{ color: pinColour(s, "light") }}>{s.light_hours_7d ?? "–"}</td>
              <td className="px-3 py-3">{s.blackouts_7d.count ? `${s.blackouts_7d.count}× (${s.blackouts_7d.hours} h)` : <span className="text-muted">None</span>}</td>
              <td className="px-3 py-3" style={{ color: pinColour(s, "heat") }}>{s.heat.battery_avg_c !== null ? `${s.heat.battery_avg_c}°C, ${s.heat.ageing_speed}×` : "–"}</td>
              <td className="px-3 py-3">{s.battery_health !== null ? `${s.battery_health}%` : <span className="text-muted">not measured</span>}</td>
              <td className="px-3 py-3">{s.problems.length ? s.problems.map((p) => p.replaceAll("_", " ")).join(", ") : <span className="text-muted">None</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

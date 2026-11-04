"use client";
// What-if tests: change NEPA hours, the weather, the battery room, dust, a panel group or add an
// appliance, and see how this site would cope over the next days, compared with things as they
// are. Simulation only: nothing is saved and the customer never sees it.
import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, ApiError } from "@/lib/api";
import type { WhatIf as Result, WhatIfRun } from "@/lib/types";

type Scenario = {
  days: number; nepa_hours: number | null; heatwave_c: number; battery_room_c: number; dust_percent: number;
  panel_group_off: "pv1" | "pv2" | null;
  new_appliance: { name: string; watts: number; hours_per_day: number; from_hour: number } | null;
};
const BLANK: Scenario = { days: 7, nepa_hours: null, heatwave_c: 0, battery_room_c: 0, dust_percent: 0, panel_group_off: null, new_appliance: null };

const PRESETS: { label: string; note: string; s: Partial<Scenario> }[] = [
  { label: "Worst El Niño week", note: "+6°C outside, +10°C battery room, 2 h NEPA", s: { heatwave_c: 6, battery_room_c: 10, nepa_hours: 2 } },
  { label: "NEPA collapse", note: "only 1 hour of light a day", s: { nepa_hours: 1 } },
  { label: "Heatwave", note: "6°C hotter than forecast", s: { heatwave_c: 6 } },
  { label: "Sealed battery store", note: "battery room 12°C hotter", s: { battery_room_c: 12 } },
  { label: "Harmattan dust", note: "35% less from the panels", s: { dust_percent: 35 } },
  { label: "Panel group 2 dies", note: "string 2 makes nothing", s: { panel_group_off: "pv2" } },
  { label: "New AC at night", note: "1.2 kW, 8 pm to 2 am", s: { new_appliance: { name: "AC", watts: 1200, hours_per_day: 6, from_hour: 20 } } },
  { label: "New deep freezer", note: "about 200 W all day", s: { new_appliance: { name: "Deep freezer", watts: 200, hours_per_day: 24, from_hour: 0 } } },
];

function Slider({ label, value, min, max, step = 1, unit, onChange }: { label: string; value: number; min: number; max: number; step?: number; unit: string; onChange: (v: number) => void }) {
  return (
    <label className="block text-sm">
      <span className="flex justify-between"><span>{label}</span><strong>{value}{unit}</strong></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="mt-1 w-full accent-[#16233f]" />
    </label>
  );
}

const ROWS: { key: keyof WhatIfRun; label: string; unit: string; worseIfHigher: boolean }[] = [
  { key: "blackout_hours", label: "Hours without power", unit: " h", worseIfHigher: true },
  { key: "nights_without_power", label: "Days with a blackout", unit: "", worseIfHigher: true },
  { key: "battery_lowest_percent", label: "Battery lowest", unit: "%", worseIfHigher: false },
  { key: "solar_kwh", label: "Solar used", unit: " kWh", worseIfHigher: false },
  { key: "nepa_hours_per_day", label: "NEPA per day", unit: " h", worseIfHigher: false },
  { key: "battery_hottest_c", label: "Battery hottest", unit: "°C", worseIfHigher: true },
  { key: "battery_ageing_speed", label: "Battery ageing speed", unit: "×", worseIfHigher: true },
];

export function WhatIf({ code }: { code: string }) {
  const [s, setS] = useState<Scenario>(BLANK);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const set = (p: Partial<Scenario>) => setS((x) => ({ ...x, ...p }));

  async function run(next = s) {
    setBusy(true);
    setError(null);
    try {
      setRes(await api<Result>(`/api/sites/${code}/whatif`, { method: "POST", body: JSON.stringify(next) }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't run the test");
    } finally {
      setBusy(false);
    }
  }

  const chart = res ? res.as_is.days.map((d, i) => ({
    day: d.day, now: d.battery_low, test: res.what_if.days[i]?.battery_low,
    blackNow: d.blackout_hours, blackTest: res.what_if.days[i]?.blackout_hours,
  })) : [];

  return (
    <section className="overflow-hidden rounded-3xl bg-white">
      <div className="border-b border-line bg-[#fff6e0] px-5 py-4">
        <h2 className="font-display text-2xl font-semibold">What if…?</h2>
        <p className="text-sm text-muted">Test how this site would cope over the next {s.days} days. Simulation only: nothing is saved and the customer doesn&apos;t see it.</p>
      </div>
      <div className="grid gap-6 p-5 lg:grid-cols-[minmax(0,340px)_1fr]">
        <div className="space-y-5">
          <div>
            <p className="mb-2 text-sm font-semibold">Quick tests</p>
            <div className="flex flex-wrap gap-2">
              {PRESETS.map((p) => (
                <button key={p.label} title={p.note} disabled={busy}
                        onClick={() => { const next = { ...BLANK, days: s.days, ...p.s }; setS(next); run(next); }}
                        className="rounded-full border border-line px-3 py-1.5 text-sm hover:border-ink disabled:opacity-50">{p.label}</button>
              ))}
            </div>
          </div>
          <div className="space-y-4 rounded-2xl bg-sky p-4">
            <p className="text-sm font-semibold">Or set your own</p>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={s.nepa_hours !== null} onChange={(e) => set({ nepa_hours: e.target.checked ? 4 : null })} />
              Change NEPA hours {s.nepa_hours === null && <span className="text-muted">(now: as it has been)</span>}
            </label>
            {s.nepa_hours !== null && <Slider label="NEPA light per day" value={s.nepa_hours} min={0} max={20} unit=" h" onChange={(v) => set({ nepa_hours: v })} />}
            <Slider label="Hotter outside (heatwave)" value={s.heatwave_c} min={0} max={10} unit="°C" onChange={(v) => set({ heatwave_c: v })} />
            <Slider label="Hotter battery room" value={s.battery_room_c} min={0} max={15} unit="°C" onChange={(v) => set({ battery_room_c: v })} />
            <Slider label="Dust on panels" value={s.dust_percent} min={0} max={60} step={5} unit="%" onChange={(v) => set({ dust_percent: v })} />
            <label className="block text-sm">Panel group not working
              <select value={s.panel_group_off ?? ""} onChange={(e) => set({ panel_group_off: (e.target.value || null) as Scenario["panel_group_off"] })}
                      className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2">
                <option value="">None</option><option value="pv1">Group 1</option><option value="pv2">Group 2</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={s.new_appliance !== null}
                     onChange={(e) => set({ new_appliance: e.target.checked ? { name: "New appliance", watts: 1000, hours_per_day: 3, from_hour: 19 } : null })} />
              Add an appliance
            </label>
            {s.new_appliance && (
              <div className="space-y-3 pl-6">
                <Slider label="Power" value={s.new_appliance.watts} min={50} max={3000} step={50} unit=" W" onChange={(v) => set({ new_appliance: { ...s.new_appliance!, watts: v } })} />
                <Slider label="Hours a day" value={s.new_appliance.hours_per_day} min={0.5} max={24} step={0.5} unit=" h" onChange={(v) => set({ new_appliance: { ...s.new_appliance!, hours_per_day: v } })} />
                <Slider label="Starting at" value={s.new_appliance.from_hour} min={0} max={23} unit=":00" onChange={(v) => set({ new_appliance: { ...s.new_appliance!, from_hour: v } })} />
              </div>
            )}
            <Slider label="Days to test" value={s.days} min={2} max={7} unit="" onChange={(v) => set({ days: v })} />
            <button onClick={() => run()} disabled={busy} className="w-full rounded-full bg-ink px-4 py-3 font-semibold text-sky disabled:opacity-60">
              {busy ? "Running the simulation…" : "Run this test"}
            </button>
          </div>
        </div>

        <div aria-live="polite">
          {error && <p className="text-alarm">{error}</p>}
          {!res && !busy && !error && (
            <div className="grid h-full min-h-[260px] place-items-center rounded-2xl border-2 border-dashed border-line p-6 text-center text-muted">
              Pick a quick test or set your own, then run it. You&apos;ll see this site as it is next to how it would be.
            </div>
          )}
          {busy && !res && <p className="animate-pulse text-muted">Simulating every 5 minutes of the next {s.days} days, twice…</p>}
          {res && (
            <div className={`space-y-5 ${busy ? "opacity-50" : ""}`}>
              <ul className="space-y-1.5 rounded-2xl bg-ink p-4 text-sky">
                {res.summary.map((line) => <li key={line} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sun" />{line}</li>)}
              </ul>
              <table className="w-full text-sm">
                <thead className="text-muted"><tr><th className="py-1 text-left font-medium" /><th className="py-1 text-right font-medium">As things are</th><th className="py-1 text-right font-medium">What if</th></tr></thead>
                <tbody>
                  {ROWS.map((r) => {
                    const a = res.as_is[r.key] as number, b = res.what_if[r.key] as number;
                    const worse = r.worseIfHigher ? b > a * 1.02 + 0.05 : b < a * 0.98 - 0.05;
                    const better = r.worseIfHigher ? b < a * 0.98 - 0.05 : b > a * 1.02 + 0.05;
                    return (
                      <tr key={r.key} className="border-t border-line">
                        <td className="py-2">{r.label}</td>
                        <td className="py-2 text-right tabular-nums">{a}{r.unit}</td>
                        <td className={`py-2 text-right font-semibold tabular-nums ${worse ? "text-alarm" : better ? "text-charge" : ""}`}>{b}{r.unit}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div>
                <p className="text-sm font-semibold">Battery low point and blackouts, day by day</p>
                <p className="text-xs text-muted">Lines: lowest battery each day. Bars: hours without power.</p>
                <div className="mt-2 h-56">
                  <ResponsiveContainer>
                    <ComposedChart data={chart}>
                      <CartesianGrid stroke="#e9eef3" vertical={false} />
                      <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#5e6b80" }} />
                      <YAxis yAxisId="p" domain={[0, 100]} unit="%" width={40} tick={{ fontSize: 11, fill: "#5e6b80" }} />
                      <YAxis yAxisId="h" orientation="right" unit=" h" width={36} tick={{ fontSize: 11, fill: "#5e6b80" }} />
                      <Tooltip contentStyle={{ borderRadius: 10, fontSize: 12 }} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar yAxisId="h" dataKey="blackNow" name="Blackout now (h)" fill="#c3ccd8" isAnimationActive={false} />
                      <Bar yAxisId="h" dataKey="blackTest" name="Blackout what-if (h)" fill="#c93636" isAnimationActive={false} />
                      <Line yAxisId="p" dataKey="now" name="Battery low, now" stroke="#1e9e6a" strokeWidth={2} isAnimationActive={false} />
                      <Line yAxisId="p" dataKey="test" name="Battery low, what-if" stroke="#d9480f" strokeWidth={2} strokeDasharray="5 4" isAnimationActive={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

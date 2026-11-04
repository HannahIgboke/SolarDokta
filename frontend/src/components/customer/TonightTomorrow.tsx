"use client";
// Will the battery last tonight, and how sunny will tomorrow be (with the best hours lit up).
import type { BatteryNow, TomorrowPlan } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Failed, Loading, Section } from "../Section";

const SKY: Record<string, string> = { sunny: "Sunny", "partly cloudy": "Partly cloudy", cloudy: "Cloudy" };

function Tonight({ b }: { b: BatteryNow }) {
  const ok = b.tonight?.startsWith("enough");
  return (
    <div className="flex gap-3">
      <span className={`mt-0.5 h-3 w-3 shrink-0 rounded-full ${ok ? "bg-charge" : "bg-warn"}`} />
      <div>
        <p className="font-medium first-letter:uppercase">{b.tonight ?? "Not enough history yet"}</p>
        <p className="text-sm text-muted">
          {b.needed_until_morning_kwh !== undefined
            ? `Needs about ${b.needed_until_morning_kwh} kWh until morning; ${b.energy_left_kwh} kWh left now.`
            : b.normal_night_use_kwh !== undefined
              ? `A normal night uses about ${b.normal_night_use_kwh} kWh; a full battery gives ${b.full_battery_holds_kwh} kWh.`
              : null}
        </p>
      </div>
    </div>
  );
}

function HourStrip({ plan }: { plan: TomorrowPlan }) {
  const solar = plan.hourly_solar_kw ?? [];
  const use = plan.hourly_use_kw ?? [];
  const max = Math.max(0.5, ...solar);
  return (
    <div className="mt-3" aria-label="Expected solar for each hour tomorrow">
      <div className="flex h-16 items-end gap-[3px]">
        {solar.map((s, h) => {
          const spare = s - (use[h] ?? 0) >= 0.8;
          return (
            <div key={h} title={`${h}:00, about ${s.toFixed(1)} kW`}
                 className={`flex-1 rounded-t-sm ${spare ? "bg-sun" : "bg-[#e5d9ac]"}`}
                 style={{ height: `${Math.max(3, (s / max) * 100)}%` }} />
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-muted">
        <span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>11pm</span>
      </div>
    </div>
  );
}

export function TonightTomorrow({ code }: { code: string }) {
  const battery = useApi<BatteryNow>(`/api/sites/${code}/tools/battery_now`, 5 * 60_000);
  const plan = useApi<TomorrowPlan>(`/api/sites/${code}/tools/tomorrow_plan`);
  const p = plan.data;
  return (
    <Section title="Tonight and tomorrow">
      {battery.loading ? <Loading what="tonight" /> : battery.data && <Tonight b={battery.data} />}
      <div className="mt-5 border-t border-line pt-4">
        {plan.loading && <Loading what="tomorrow's forecast" />}
        {(plan.error || p?.error) && <Failed message={plan.error ?? p?.error ?? ""} />}
        {p && !p.error && (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="font-medium">{p.date}: {SKY[p.sky] ?? p.sky}</p>
              <p className="text-sm text-muted">about {p.expected_solar_kwh} kWh of solar</p>
            </div>
            <HourStrip plan={p} />
            <p className="mt-3 text-sm">
              {p.best_hours_for_heavy_appliances?.length
                ? <>Best time for ironing, pumping or washing: <strong>{p.best_hours_for_heavy_appliances.join(", ")}</strong> (the bright bars).</>
                : "Not much spare sun expected. Spread heavy appliances out, or use them when NEPA is on."}
            </p>
            {p.weak_panel_strings && (
              <p className="mt-1 text-sm text-warn">Forecast lowered: some panels are underperforming.</p>
            )}
          </>
        )}
      </div>
    </Section>
  );
}

"use client";
// Today in one chart: what the panels could make, what they made, what the home used,
// and the battery level, with a strip underneath showing when NEPA was on.
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Today } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Failed, Loading, Section } from "../Section";

const KEY = [
  { label: "Panels could make", swatch: "border-2 border-dashed border-[#d9a300] bg-[#fdf3cf]" },
  { label: "Solar used", swatch: "bg-sun" },
  { label: "Home used", swatch: "bg-ink" },
  { label: "Battery %", swatch: "bg-charge" },
];

export function TodayChart({ code }: { code: string }) {
  const { data, error, loading } = useApi<Today>(`/api/sites/${code}/views/today`, 5 * 60_000);
  const points = (data?.points ?? []).map((p) => ({
    ...p,
    solar: p.solar_w !== undefined ? p.solar_w / 1000 : undefined,
    could: p.could_make_w !== undefined ? p.could_make_w / 1000 : undefined,
    house: p.house_w !== undefined ? p.house_w / 1000 : undefined,
  }));
  return (
    <Section title="Today" aside={data?.solar_kwh !== undefined && `${data.solar_kwh} kWh from solar · ${data.house_kwh} kWh used`}>
      {loading && <Loading what="today's chart" />}
      {error && <Failed message={error} />}
      {points.length > 0 && (
        <>
          <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            {KEY.map((k) => (
              <li key={k.label} className="flex items-center gap-1.5">
                <span className={`inline-block h-2.5 w-4 rounded-sm ${k.swatch}`} />{k.label}
              </li>
            ))}
          </ul>
          <div className="h-64 w-full">
            <ResponsiveContainer>
              <ComposedChart data={points} margin={{ top: 6, right: 0, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#e3e8ee" vertical={false} />
                <XAxis dataKey="time" interval={11} tick={{ fontSize: 11, fill: "#5e6b80" }} tickLine={false} />
                <YAxis yAxisId="kw" tick={{ fontSize: 11, fill: "#5e6b80" }} width={52}
                       tickFormatter={(v: number) => `${Number(v.toFixed(1))} kW`} />
                <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} tick={{ fontSize: 11, fill: "#5e6b80" }} unit="%" width={40} />
                <Tooltip formatter={(v: number, n: string) => n === "Battery %" ? `${Math.round(v)}%` : `${v.toFixed(2)} kW`}
                         contentStyle={{ borderRadius: 8, borderColor: "#d5dde6", fontSize: 12 }} />
                <Area yAxisId="kw" dataKey="could" name="Panels could make" stroke="#d9a300" strokeDasharray="4 3"
                      fill="#fdf3cf" fillOpacity={0.8} isAnimationActive={false} />
                <Area yAxisId="kw" dataKey="solar" name="Solar used" stroke="#f2b705" fill="#f2b705" fillOpacity={0.75} isAnimationActive={false} />
                <Line yAxisId="kw" dataKey="house" name="Home used" stroke="#16233f" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line yAxisId="pct" dataKey="battery_percent" name="Battery %" stroke="#1e9e6a" strokeWidth={2} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-1 flex items-center pr-[40px] text-xs text-muted">
            <span className="w-[52px] shrink-0 pr-2 text-right">NEPA</span>
            <div className="flex h-2.5 flex-1 overflow-hidden rounded-sm bg-sky" aria-label="When NEPA was on today">
              {points.map((p) => (
                <span key={p.time} className={`h-full flex-1 ${p.nepa_on ? "bg-nepa" : ""}`} />
              ))}
            </div>
          </div>
        </>
      )}
    </Section>
  );
}

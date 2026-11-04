"use client";
// Long-term charts for technicians: each panel string's performance (a dead or weak string, dust
// or shade show up as a line falling away), the battery's health estimates with the fade trend,
// and the last 30 days of energy and NEPA hours.
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from "recharts";
import type { History } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Failed, Loading, Section } from "../Section";

const axis = { fontSize: 11, fill: "#5e6b80" };
const tip = { borderRadius: 8, borderColor: "#d5dde6", fontSize: 12 };

export function BatteryTrendChart({ data }: { data: History }) {
  const trend = data.battery_trend;
  const battery = data.battery.map((b) => ({ ...b, t: new Date(b.ts).getTime(), pct: b.soh * 100 }));
  const trendLine = trend
    ? [{ t: new Date(trend.from.ts).getTime(), trend: trend.from.soh * 100 }, { t: new Date(trend.to.ts).getTime(), trend: trend.to.soh * 100 }]
    : [];
  if (battery.length === 0) return <p className="text-sm text-muted">No deep discharges measured yet.</p>;
  return (
    <>
      <div className="h-56">
        <ResponsiveContainer>
          <ComposedChart>
            <CartesianGrid stroke="#e3e8ee" vertical={false} />
            <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tick={axis}
                   tickFormatter={(t: number) => new Date(t).toLocaleDateString("en-NG", { month: "short" })} />
            <YAxis domain={[60, 105]} unit="%" tick={axis} width={44} />
            <Tooltip labelFormatter={(t: number) => new Date(t).toLocaleDateString("en-NG")} formatter={(v: number) => `${v.toFixed(1)}%`} contentStyle={tip} />
            <Scatter data={battery} dataKey="pct" name="Estimate" fill="#1e9e6a" isAnimationActive={false} />
            {trendLine.length > 0 && <Line data={trendLine} dataKey="trend" name="Trend" stroke="#16233f" strokeDasharray="5 4" dot={false} isAnimationActive={false} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-muted">Each dot: usable capacity measured during a night where the battery dropped 30% or more. Normal ageing is 2–5% a year.</p>
    </>
  );
}

export function HistoryCharts({ code }: { code: string }) {
  const { data, error, loading } = useApi<History>(`/api/sites/${code}/history`);
  if (loading) return <Loading what="history" />;
  if (error || !data) return <Failed message={error ?? "No history"} />;
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Section title="Panel strings" aside="actual ÷ expected solar, daily">
        {data.strings.length === 0 ? <p className="text-sm text-muted">No daily health numbers yet.</p> : (
          <div className="h-56">
            <ResponsiveContainer>
              <ComposedChart data={data.strings.map((d) => ({ ...d, pv1: d.pv1 !== null ? d.pv1 * 100 : null, pv2: d.pv2 !== null ? d.pv2 * 100 : null }))}>
                <CartesianGrid stroke="#e3e8ee" vertical={false} />
                <XAxis dataKey="day" tick={axis} minTickGap={24} />
                <YAxis domain={[0, 120]} unit="%" tick={axis} width={44} />
                <Tooltip formatter={(v: number) => `${Math.round(v)}%`} contentStyle={tip} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line dataKey="pv1" name="String 1" stroke="#3b5b92" dot={false} strokeWidth={2} connectNulls isAnimationActive={false} />
                <Line dataKey="pv2" name="String 2" stroke="#f2b705" dot={false} strokeWidth={2} connectNulls isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
        <p className="mt-2 text-xs text-muted">Around 85–100% is healthy. Both strings falling together means dust or weather; one string falling alone means a fault on that string.</p>
      </Section>

      <Section title="Battery health estimates" aside={data.battery_trend ? `losing ${(data.battery_trend.fade_per_year * 100).toFixed(1)}% a year` : "one dot per deep discharge"}>
        <BatteryTrendChart data={data} />
      </Section>

      <Section title="Last 30 days" aside="energy and hours of NEPA" className="xl:col-span-2">
        <div className="h-64">
          <ResponsiveContainer>
            <ComposedChart data={data.energy}>
              <CartesianGrid stroke="#e3e8ee" vertical={false} />
              <XAxis dataKey="day" tick={axis} minTickGap={16} />
              <YAxis yAxisId="kwh" unit=" kWh" tick={axis} width={60} />
              <YAxis yAxisId="h" orientation="right" domain={[0, 24]} unit=" h" tick={axis} width={40} />
              <Tooltip contentStyle={tip} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar yAxisId="kwh" dataKey="solar_kwh" name="Solar (kWh)" fill="#f2b705" isAnimationActive={false} />
              <Bar yAxisId="kwh" dataKey="nepa_kwh" name="From NEPA (kWh)" fill="#4c6ef5" isAnimationActive={false} />
              <Line yAxisId="kwh" dataKey="use_kwh" name="Used (kWh)" stroke="#16233f" strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line yAxisId="h" dataKey="light_hours" name="NEPA hours" stroke="#4c6ef5" strokeDasharray="4 3" dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Section>
    </div>
  );
}

"use client";
// Light tracker: hours of NEPA each day for the last two weeks, against what the band promises.
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { LightTracker as Data } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Failed, Loading, Section } from "../Section";

export function LightTracker({ code }: { code: string }) {
  const { data: d, error, loading } = useApi<Data>(`/api/sites/${code}/tools/light_tracker?days=14`, 30 * 60_000);
  const poor = d && !d.error && d.average_hours_per_day < d.normal_hours_for_band * 0.6;
  return (
    <Section title="Light tracker" aside="NEPA hours per day, last 14 days">
      {loading && <Loading what="NEPA hours" />}
      {(error || d?.error) && <Failed message={error ?? d?.error ?? ""} />}
      {d && !d.error && (
        <>
          <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
            <div>
              <p className={`font-display text-4xl font-bold ${poor ? "text-warn" : "text-nepa"}`}>
                {d.average_hours_per_day} h
              </p>
              <p className="text-sm text-muted">of light a day on average (Band {d.tariff_band} should give about {d.normal_hours_for_band} h)</p>
            </div>
            <div className="text-sm">
              <p>Worst day: <strong>{d.worst_day.day}</strong>, {d.worst_day.hours} h</p>
              <p>
                Home completely without power: <strong>{d.home_blackout_hours} h</strong>
                {d.home_blackouts ? ` (${d.home_blackouts} time${d.home_blackouts > 1 ? "s" : ""})` : ""}
              </p>
            </div>
          </div>
          {d.situation && (
            <p className="mt-3 rounded-lg bg-sky px-3 py-2 text-sm">
              Since {d.situation_since}: {d.situation}.
            </p>
          )}
          <div className="mt-4 h-40">
            <ResponsiveContainer>
              <BarChart data={d.days} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#e3e8ee" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#5e6b80" }} tickLine={false}
                       tickFormatter={(v: string) => v.slice(4, 6)} interval={0} />
                <YAxis domain={[0, 24]} ticks={[0, 6, 12, 18, 24]} width={28} tick={{ fontSize: 11, fill: "#5e6b80" }} />
                <Tooltip formatter={(v: number) => `${v} h of light`} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                <ReferenceLine y={d.normal_hours_for_band} stroke="#5e6b80" strokeDasharray="4 3"
                               label={{ value: "normal", position: "insideTopRight", fontSize: 10, fill: "#5e6b80" }} />
                <Bar dataKey="hours" fill="#4c6ef5" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          {d.battery_lowest_percent_avg !== null && (
            <p className="mt-2 text-sm text-muted">Your battery drops to about {d.battery_lowest_percent_avg}% on a typical day.</p>
          )}
        </>
      )}
    </Section>
  );
}

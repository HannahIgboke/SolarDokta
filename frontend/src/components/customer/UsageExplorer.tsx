"use client";
// Pick any day (hour by hour) or range of days (day by day) and see the power story in plain
// words and three simple charts, each with a sentence saying how to read it.
import { useMemo, useState } from "react";
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useLang } from "@/lib/i18n";
import type { Usage } from "@/lib/types";
import { naira, useApi } from "@/lib/useApi";
import { usePhone } from "@/lib/usePhone";
import { Failed, Loading } from "../Section";

const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const daysAgo = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return ymd(d); };
const axis = { fontSize: 11, fill: "#5e6b80" };
const tip = { borderRadius: 10, borderColor: "#d5dde6", fontSize: 12 };

function ChartCard({ title, how, children }: { title: string; how: string; children: React.ReactNode }) {
  return (
    <section className="rounded-3xl bg-white p-5">
      <h3 className="font-display text-lg font-semibold">{title}</h3>
      <p className="mt-1 max-w-2xl text-sm text-muted">{how}</p>
      <div className="mt-4 h-56">{children}</div>
    </section>
  );
}

export function UsageExplorer({ code }: { code: string }) {
  const { t } = useLang();
  const quick = [
    { id: "today", label: t("usage.today"), start: daysAgo(0), end: daysAgo(0) },
    { id: "yesterday", label: t("usage.yesterday"), start: daysAgo(1), end: daysAgo(1) },
    { id: "week", label: t("usage.week"), start: daysAgo(6), end: daysAgo(0) },
    { id: "month", label: t("usage.month"), start: daysAgo(29), end: daysAgo(0) },
  ];
  const [range, setRange] = useState({ start: daysAgo(6), end: daysAgo(0) });
  const phone = usePhone();
  const { data, error, loading } = useApi<Usage>(`/api/sites/${code}/views/usage?start=${range.start}&end=${range.end}`);
  const active = quick.find((q) => q.start === range.start && q.end === range.end)?.id;
  const points = useMemo(() => (data?.points ?? []).map((p) => ({
    ...p, band: p.battery_low !== null && p.battery_high !== null ? [p.battery_low, p.battery_high] : null,
  })), [data]);
  const wide = data?.mode === "hours" ? 2 : points.length > 14 ? Math.ceil(points.length / 10) - 1 : 0;
  const tick = phone ? Math.max(wide, Math.ceil(points.length / 4) - 1) : wide;   // about 4 labels on a phone

  return (
    <div className="space-y-5">
      <div className="rounded-3xl bg-white p-5">
        <h2 className="font-display text-2xl font-semibold">{t("usage.pick")}</h2>
        <p className="mt-1 text-sm text-muted">{t("usage.hint")}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          {quick.map((q) => (
            <button key={q.id} onClick={() => setRange({ start: q.start, end: q.end })} aria-pressed={active === q.id}
                    className={`rounded-full px-4 py-2 text-sm font-medium ${active === q.id ? "bg-ink text-sky" : "bg-sky hover:bg-line"}`}>
              {q.label}
            </button>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:flex sm:gap-3">
          <label className="block text-xs text-muted">{t("usage.from")}
            <input type="date" value={range.start} max={range.end} onChange={(e) => e.target.value && setRange((r) => ({ ...r, start: e.target.value }))}
                   className="mt-1 block w-full min-w-0 rounded-full border border-line bg-sky px-3 py-1.5 text-sm text-ink sm:w-auto" />
          </label>
          <label className="block text-xs text-muted">{t("usage.to")}
            <input type="date" value={range.end} min={range.start} max={daysAgo(0)} onChange={(e) => e.target.value && setRange((r) => ({ ...r, end: e.target.value }))}
                   className="mt-1 block w-full min-w-0 rounded-full border border-line bg-sky px-3 py-1.5 text-sm text-ink sm:w-auto" />
          </label>
        </div>
      </div>

      {loading && !data && <Loading what="your usage" />}
      {error && <Failed message={error} />}
      {data?.error && <Failed message={data.error} />}
      {data && !data.error && points.length === 0 && <p className="rounded-3xl bg-white p-5 text-muted">{t("usage.none")}</p>}

      {data?.totals && (
        <div className="grid gap-5 lg:grid-cols-[1.2fr_1fr]">
          <section className="rounded-3xl bg-ink p-6 text-sky">
            <p className="text-sm text-sky/70">{data.span}</p>
            <h3 className="mt-1 font-display text-xl font-semibold">{t("usage.inShort")}</h3>
            <ul className="mt-3 space-y-2">
              {data.story?.map((s) => <li key={s} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sun" />{s}</li>)}
            </ul>
          </section>
          <dl className="grid grid-cols-2 gap-3">
            {[
              [t("usage.solar"), `${data.totals.solar_kwh} kWh`, "text-[#9a7400]"],
              [t("usage.used"), `${data.totals.use_kwh} kWh`, ""],
              [t("usage.light.total"), `${data.totals.light_hours} h`, "text-nepa"],
              [t("usage.saved"), naira(data.totals.saved_ngn) + (data.estimate ? "*" : ""), "text-charge"],
            ].map(([label, value, tone]) => (
              <div key={label} className="rounded-3xl bg-white p-4">
                <dt className="text-sm text-muted">{label}</dt>
                <dd className={`font-display text-2xl font-semibold ${tone}`}>{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {points.length > 0 && (
        <>
          <ChartCard title={t("usage.energy")} how={t("usage.energyHow")}>
            <ResponsiveContainer>
              <BarChart data={points} barGap={1}>
                <CartesianGrid stroke="#e9eef3" vertical={false} />
                <XAxis dataKey="label" tick={axis} interval={tick} tickLine={false} />
                <YAxis tick={axis} width={52} unit=" kWh" />
                <Tooltip contentStyle={tip} formatter={(v: number) => `${v} kWh`} />
                <Bar dataKey="solar_kwh" name={t("usage.solar")} fill="#f2b705" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                <Bar dataKey="use_kwh" name={t("usage.used")} fill="#16233f" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <div className="grid gap-5 lg:grid-cols-2">
            <ChartCard title={t("usage.battery")} how={t("usage.batteryHow")}>
              <ResponsiveContainer>
                <ComposedChart data={points}>
                  <CartesianGrid stroke="#e9eef3" vertical={false} />
                  <XAxis dataKey="label" tick={axis} interval={tick} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={axis} width={40} unit="%" />
                  <Tooltip contentStyle={tip} formatter={(v: number | number[]) => Array.isArray(v) ? `${v[0]}% to ${v[1]}%` : `${v}%`} />
                  <ReferenceLine y={20} stroke="#c93636" strokeDasharray="4 3" />
                  <Area dataKey="band" name={t("stat.battery")} stroke="#1e9e6a" fill="#1e9e6a" fillOpacity={0.25} isAnimationActive={false} />
                  <Line dataKey="battery_low" stroke="#1e9e6a" strokeWidth={2} dot={false} legendType="none" tooltipType="none" isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title={t("usage.light")} how={t("usage.lightHow")}>
              <ResponsiveContainer>
                <BarChart data={points}>
                  <CartesianGrid stroke="#e9eef3" vertical={false} />
                  <XAxis dataKey="label" tick={axis} interval={tick} tickLine={false} />
                  <YAxis tick={axis} width={36} domain={[0, data?.mode === "hours" ? 1 : 24]} unit=" h" />
                  <Tooltip contentStyle={tip} formatter={(v: number) => `${v} h`} />
                  <Bar dataKey="light_hours" name={t("usage.light.total")} fill="#4c6ef5" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        </>
      )}
    </div>
  );
}

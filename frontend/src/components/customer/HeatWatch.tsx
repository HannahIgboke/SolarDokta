"use client";
// Heat watch: what this El Niño season's heat is doing to the battery, in one sentence people
// remember ("about 3 months of battery life"), a 30-day picture of the battery room, and tips.
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { HeatOutlook } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Failed, Loading } from "../Section";

const tempColour = (c: number) => (c >= 35 ? "#d9480f" : c >= 30 ? "#f59f00" : "#1e9e6a");

function Thermometer({ c }: { c: number }) {
  const fill = Math.max(0.08, Math.min(1, (c - 15) / 35));
  return (
    <svg viewBox="0 0 40 120" className="h-28 w-10 shrink-0" aria-hidden="true">
      <rect x="13" y="6" width="14" height="88" rx="7" fill="#fff" stroke="#16233f" strokeWidth="2" />
      <rect x="17" y={10 + 80 * (1 - fill)} width="6" height={80 * fill} rx="3" fill={tempColour(c)} />
      <circle cx="20" cy="102" r="13" fill={tempColour(c)} stroke="#16233f" strokeWidth="2" />
      <path d="M27 31h6M27 51h6M27 71h6" stroke="#16233f" strokeWidth="1.5" />
    </svg>
  );
}

export function HeatWatch({ code }: { code: string }) {
  const { data: h, error, loading } = useApi<HeatOutlook>(`/api/sites/${code}/tools/heat_outlook`, 30 * 60_000);
  const speed = h?.ageing_speed_vs_25c;
  const months = h?.life_lost_months_this_season ?? 0;
  return (
    <section className="overflow-hidden rounded-3xl bg-white">
      <div className="bg-gradient-to-r from-[#b4400f] to-[#7a2913] px-5 py-4 text-white">
        <p className="text-sm text-white/80">Heat watch, El Niño season</p>
        {h && speed !== undefined ? (
          <p className="mt-1 font-display text-xl leading-snug font-semibold">
            {months >= 0.5 ? `This season's heat could take about ${months.toFixed(months < 3 ? 1 : 0)} months off your battery's life.`
              : "Your battery room is staying cool. The heat isn't hurting it yet."}
          </p>
        ) : <p className="mt-1 font-display text-xl font-semibold">How the heat is treating your battery</p>}
      </div>
      <div className="p-5">
        {loading && <Loading what="heat" />}
        {error && <Failed message={error} />}
        {h?.heatwave_tomorrow && (
          <p className="mb-4 rounded-2xl bg-[#fdecd8] px-4 py-3 text-sm text-warn">
            <strong>Very hot tomorrow (about {h.tomorrow_high_c}°C).</strong> Panels lose about {h.panel_midday_loss_percent}% at midday. Run heavy appliances in the morning.
          </p>
        )}
        {h && speed !== undefined ? (
          <>
            <div className="flex items-center gap-4">
              <Thermometer c={h.battery_average_c ?? 25} />
              <dl className="grid flex-1 grid-cols-2 gap-3">
                <div><dt className="text-xs text-muted">Battery room, 30-day average</dt><dd className="font-display text-2xl font-bold" style={{ color: tempColour(h.battery_average_c ?? 25) }}>{h.battery_average_c}°C</dd></div>
                <div><dt className="text-xs text-muted">Ageing speed</dt><dd className="font-display text-2xl font-bold">{speed.toFixed(1)}×</dd><dd className="text-xs text-muted">compared with 25°C</dd></div>
                <div><dt className="text-xs text-muted">Days over 35°C</dt><dd className="font-display text-xl font-semibold">{h.battery_hot_days_last_30} of 30</dd></div>
                <div><dt className="text-xs text-muted">{h.tomorrow_high_c !== undefined ? "Tomorrow outside" : "Hottest reading"}</dt>
                  <dd className="font-display text-xl font-semibold">{h.tomorrow_high_c !== undefined ? `${h.tomorrow_high_c}°C` : `${h.battery_hottest_c}°C`}</dd></div>
              </dl>
            </div>
            {h.daily_max_c && h.daily_max_c.length > 3 && (
              <div className="mt-5">
                <p className="text-sm font-semibold">Hottest battery temperature each day</p>
                <p className="text-xs text-muted">Green is fine, orange is warm, red (over 35°C) wears the battery fast.</p>
                <div className="mt-2 h-32">
                  <ResponsiveContainer>
                    <BarChart data={h.daily_max_c} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                      <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#5e6b80" }} interval={6} tickLine={false} />
                      <YAxis domain={[20, 45]} width={30} tick={{ fontSize: 10, fill: "#5e6b80" }} unit="°" />
                      <Tooltip formatter={(v: number) => `${v}°C`} contentStyle={{ borderRadius: 10, fontSize: 12 }} />
                      <ReferenceLine y={35} stroke="#d9480f" strokeDasharray="4 3" />
                      <Bar dataKey="c" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                        {h.daily_max_c.map((d) => <Cell key={d.day} fill={tempColour(d.c)} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
            <ul className="mt-4 space-y-1.5 text-sm">
              {h.tips.map((t) => <li key={t} className="flex gap-2"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#d9480f]" /><span className="first-letter:uppercase">{t}.</span></li>)}
            </ul>
            <details className="mt-4 text-sm text-muted">
              <summary className="cursor-pointer font-medium text-ink">How we work this out</summary>
              <p className="mt-2">Battery chemistry wears roughly twice as fast for every 10°C above 25°C. We measure your battery&apos;s temperature every 5 minutes, work out how much faster it is ageing, and count the extra wear between now and the end of February, when El Niño is expected to ease. {h.el_nino}</p>
            </details>
          </>
        ) : !loading && <p className="text-sm text-muted">Not enough battery temperature readings yet.</p>}
      </div>
    </section>
  );
}

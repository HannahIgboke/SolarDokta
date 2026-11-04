"use client";
// Battery health report: one printable page for the customer, a warranty claim or a buyer.
// From installation to replacement: SOH and SOC explained, cycles against the rating, the
// measured health over time, where it is heading with this El Niño heat and if kept cool,
// a resale grade, and how it was measured.
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { GRADE_COLOUR, Gauge, monthYear } from "@/components/customer/BatteryHealth";
import { Logo } from "@/components/Logo";
import type { BatteryReport } from "@/lib/types";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

function Fact({ k, v, note }: { k: string; v: React.ReactNode; note?: string }) {
  return (
    <div className="rounded-2xl border border-line p-4 print:break-inside-avoid">
      <dt className="text-sm text-muted">{k}</dt>
      <dd className="mt-0.5 font-display text-2xl font-semibold">{v}</dd>
      {note && <dd className="mt-0.5 text-xs text-muted">{note}</dd>}
    </div>
  );
}

function Timeline({ r }: { r: BatteryReport }) {
  const t = (ts: string) => new Date(ts).getTime();
  const measured = r.history.filter((h) => !h.install).map((h) => ({ t: t(h.ts), measured: h.soh * 100 }));
  const install = r.history.filter((h) => h.install).map((h) => ({ t: t(h.ts), install: 100 }));
  const hot = r.projection.map((p) => ({ t: t(p.ts), hot: p.soh * 100 }));
  const cool = r.projection_cool.map((p) => ({ t: t(p.ts), cool: p.soh * 100 }));
  const all = [...install, ...measured, ...hot, ...cool].sort((a, b) => a.t - b.t);
  const y0 = new Date(all[0]?.t ?? Date.now()).getFullYear(), y1 = new Date(all[all.length - 1]?.t ?? Date.now()).getFullYear();
  const step = y1 - y0 > 10 ? 2 : 1;
  const ticks = Array.from({ length: Math.floor((y1 - y0) / step) + 1 }, (_, k) => new Date(y0 + k * step, 0, 1).getTime());
  return (
    <div className="h-72">
      <ResponsiveContainer>
        <ComposedChart data={all}>
          <CartesianGrid stroke="#e9eef3" vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} ticks={ticks} tick={{ fontSize: 11, fill: "#5e6b80" }}
                 tickFormatter={(v: number) => new Date(v).getFullYear().toString()} />
          <YAxis domain={[65, 102]} unit="%" width={44} tick={{ fontSize: 11, fill: "#5e6b80" }} />
          <Tooltip labelFormatter={(v: number) => new Date(v).toLocaleDateString("en-NG", { month: "short", year: "numeric" })}
                   formatter={(v: number) => `${v.toFixed(1)}%`} contentStyle={{ borderRadius: 10, fontSize: 12 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <ReferenceLine y={80} stroke="#c93636" strokeDasharray="5 4" label={{ value: "80% warranty line", position: "insideBottomLeft", fontSize: 11, fill: "#c93636" }} />
          <Scatter dataKey="install" name="Installed (100%)" fill="#16233f" isAnimationActive={false} />
          <Scatter dataKey="measured" name="Measured SOH" fill="#1e9e6a" isAnimationActive={false} />
          <Line dataKey="hot" name="Ahead, as now (with El Niño heat)" stroke="#d9480f" strokeWidth={2.5} dot={false} connectNulls isAnimationActive={false} />
          <Line dataKey="cool" name="Ahead, if kept at 25°C" stroke="#4c6ef5" strokeWidth={2} strokeDasharray="6 4" dot={false} connectNulls isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function ReportPage() {
  const { code } = useParams<{ code: string }>();
  const { loading, session, demo, me } = useSession();
  const router = useRouter();
  const site = me?.sites.find((s) => s.code === code);
  const { data: r, error } = useApi<BatteryReport>(site ? `/api/sites/${code}/views/battery_report` : null);

  useEffect(() => {
    if (!loading && !session && !demo) router.replace("/");
  }, [loading, session, demo, router]);

  if (loading || !me) return <p className="p-8 text-muted">Loading…</p>;
  if (!site) return <p className="p-8 text-muted">No system called {code} on your account.</p>;
  return (
    <main className="mx-auto max-w-4xl space-y-6 px-4 py-8 print:max-w-none print:py-0">
      <div className="flex items-center justify-between print:hidden">
        <Link href={me.role === "staff" ? `/staff/sites/${code}#health` : "/my#usage"} className="text-sm underline">Back</Link>
        <button onClick={() => window.print()} className="rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-sky">Print or save as PDF</button>
      </div>

      <header className="overflow-hidden rounded-3xl bg-ink text-sky print:rounded-none">
        <div className="flex flex-wrap items-center justify-between gap-4 p-6">
          <div>
            <p className="text-sm text-sky/70">Battery health report</p>
            <h1 className="font-display text-3xl font-semibold">{site.name}</h1>
            <p className="text-sky/80">{site.city}{r ? `, ${r.nameplate_kwh} kWh ${r.chemistry}` : ""}, {new Date().toLocaleDateString("en-NG", { day: "numeric", month: "long", year: "numeric" })}</p>
          </div>
          <div className="flex items-center gap-2"><Logo className="h-9 w-9" /><span className="font-display font-semibold">SolarDokta</span></div>
        </div>
      </header>

      {error && <p className="text-alarm">{error}</p>}
      {!r && !error && <p className="animate-pulse text-muted">Putting the report together…</p>}
      {r && (
        <>
          <section className="grid gap-6 rounded-3xl bg-white p-6 md:grid-cols-[260px_1fr] md:items-center">
            <div className="flex flex-col items-center">
              {r.soh_percent !== null ? <Gauge percent={r.soh_percent} size="max-w-[260px]" /> : <p className="text-muted">SOH not measured yet</p>}
              {r.measured && (
                <div className="mt-2 flex items-center gap-3">
                  <span className={`grid h-12 w-12 place-items-center rounded-full font-display text-2xl font-bold text-white ${GRADE_COLOUR[r.grade]}`}>{r.grade}</span>
                  <span className="text-sm">Resale grade<br /><span className="text-muted">{r.grade_text}</span></span>
                </div>
              )}
            </div>
            <div>
              <h2 className="font-display text-xl font-semibold">In short</h2>
              <ul className="mt-2 space-y-2">
                {r.summary.map((s) => <li key={s} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sun" />{s}</li>)}
              </ul>
            </div>
          </section>

          <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Fact k="SOH (state of health)" v={r.soh_percent !== null ? `${r.soh_percent}%` : "–"} note={`${r.usable_kwh} of ${r.nameplate_kwh} kWh still usable`} />
            <Fact k="SOC (state of charge) now" v={r.soc_percent !== null ? `${r.soc_percent}%` : "–"} note="how full it is at this moment" />
            <Fact k="Cycles used" v={r.cycles.toLocaleString()} note={`of ~${r.rated_cycles.toLocaleString()} rated (${((100 * r.cycles) / r.rated_cycles).toFixed(1)}%), ~${r.cycles_per_year}/year`} />
            <Fact k="Typical daily depth" v={r.typical_depth_of_discharge_percent !== null ? `${r.typical_depth_of_discharge_percent}%` : "–"} note="how much is used up on a normal day" />
            <Fact k="Installed" v={r.install_date ? new Date(r.install_date).toLocaleDateString("en-NG", { month: "short", year: "numeric" }) : "–"} note={r.age_years !== undefined ? `${r.age_years} years ago` : undefined} />
            <Fact k="Losing per year" v={`${r.fade_per_year_percent}%`} note={r.fade_measured ? "measured from its own readings" : "estimated from use and temperature"} />
            <Fact k="Reaches 80% around" v={monthYear(r.reaches_80_at)} note={r.reaches_80_years !== null ? `in about ${r.reaches_80_years} years` : undefined} />
            <Fact k="Replace around" v={monthYear(r.replace_around)} note="when it drops to about 70%" />
          </dl>

          <section className="rounded-3xl bg-white p-6 print:break-inside-avoid">
            <h2 className="font-display text-xl font-semibold">From installation to replacement</h2>
            <p className="mt-1 text-sm text-muted">Dots: health measured on nights the battery was used deeply. Lines: where it&apos;s heading. The gap between the orange and blue lines is what the heat is costing.</p>
            <div className="mt-4"><Timeline r={r} /></div>
          </section>

          <section className="grid gap-5 rounded-3xl bg-gradient-to-r from-[#b4400f] to-[#7a2913] p-6 text-white md:grid-cols-3 print:break-inside-avoid">
            <div className="md:col-span-1">
              <h2 className="font-display text-xl font-semibold">The super El Niño effect</h2>
              <p className="mt-1 text-white/80">Hotter than usual until early 2027 (WMO, NiMet). Battery wear roughly doubles for every 10°C above 25°C.</p>
            </div>
            <dl className="grid grid-cols-2 gap-4 md:col-span-2">
              <div><dt className="text-sm text-white/75">Battery room, last 30 days</dt><dd className="font-display text-3xl font-bold">{r.battery_avg_temp_c_30d ?? "–"}°C</dd></div>
              <div><dt className="text-sm text-white/75">Ageing speed now</dt><dd className="font-display text-3xl font-bold">{r.ageing_speed_now}×</dd></div>
              <div><dt className="text-sm text-white/75">Wear per year: this season vs kept cool</dt><dd className="font-display text-3xl font-bold">{r.fade_el_nino_percent}% vs {r.fade_cool_percent}%</dd></div>
              <div><dt className="text-sm text-white/75">Extra wear from this El Niño season</dt><dd className="font-display text-3xl font-bold">{r.el_nino_extra_months >= 0.5 ? `${r.el_nino_extra_months} months` : "under a month"}</dd>
                <dd className="text-xs text-white/70">Heat overall (vs a 25°C room): {r.life_lost_to_heat_months ?? 0} months of life</dd></div>
            </dl>
          </section>

          <section className="grid gap-5 md:grid-cols-2 print:break-inside-avoid">
            <div className="rounded-3xl bg-white p-6">
              <h2 className="font-display text-lg font-semibold">SOH and SOC, in plain words</h2>
              <p className="mt-2 text-sm"><strong>SOH (state of health)</strong> is how big the battery still is compared with when it was new. Think of the size of a water tank: at 90% SOH, a 10 kWh battery holds about 9 kWh when full.</p>
              <p className="mt-2 text-sm"><strong>SOC (state of charge)</strong> is how full it is right now, the &ldquo;battery %&rdquo;. Think of how much water is in the tank today.</p>
              <p className="mt-2 text-sm">SOC goes up and down every day. SOH only goes down, slowly, with use, time and heat.</p>
            </div>
            <div className="rounded-3xl bg-white p-6">
              <h2 className="font-display text-lg font-semibold">How to make it last longer</h2>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm">
                <li>Keep the battery room cool and airy, out of direct sun. This matters most until February.</li>
                <li>Avoid running it nearly empty every night: move heavy loads to the daytime when the sun can cover them.</li>
                <li>Keep vents clear and dust off the inverter and battery.</li>
                <li>Ask your installer to check connections once a year.</li>
              </ul>
            </div>
          </section>

          <p className="text-xs text-muted">
            How this was measured: SolarDokta reads the system every 5 minutes. On every night the battery drops by 30% or more, the energy that
            came out is compared with the charge it used, giving one SOH estimate. The trend uses the median rate across many nights, so single
            readings don&apos;t mislead. Projections assume the same use; the El Niño line uses the last 30 days&apos; battery temperatures until
            the end of February 2027. Cycle rating: about {r.rated_cycles.toLocaleString()} full cycles to 80% for this chemistry.
          </p>
        </>
      )}
    </main>
  );
}

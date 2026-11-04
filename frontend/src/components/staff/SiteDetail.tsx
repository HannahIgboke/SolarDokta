"use client";
// One site, technician view, in tabs: Live, Health & history, What-if, Problems, Ask Dokta.
import Link from "next/link";
import type { Live } from "@/lib/types";
import { kw, useApi } from "@/lib/useApi";
import { AskDokta } from "../customer/AskDokta";
import { BatteryHealth } from "../customer/BatteryHealth";
import { HeatWatch } from "../customer/HeatWatch";
import { LightTracker } from "../customer/LightTracker";
import { LiveSystem } from "../customer/LiveSystem";
import { TodayChart } from "../customer/TodayChart";
import { Failed, Loading, Section } from "../Section";
import { TabBar, useHashTab } from "../TabBar";
import { DemoPanel } from "./DemoPanel";
import { HistoryCharts } from "./HistoryCharts";
import { ProblemsInbox } from "./ProblemsInbox";
import { WhatIf } from "./WhatIf";

type CustomerInfo = {
  customer: { full_name: string | null; whatsapp_number: string | null; preferred_language: string } | null;
  install_date: string | null;
  system: { pv1_kwp: number; pv2_kwp: number; inverter_kw: number; battery_kwh: number; battery: string;
            mode: string; tariff_band: string; tilt: number; azimuth: number };
};

function Stat({ k, v, tone = "" }: { k: string; v: React.ReactNode; tone?: string }) {
  return <div className="rounded-2xl bg-sky px-3 py-2"><dt className="text-xs text-muted">{k}</dt><dd className={`font-display text-lg font-semibold ${tone}`}>{v}</dd></div>;
}

export function SiteDetail({ code, name }: { code: string; name: string }) {
  const live = useApi<Live>(`/api/sites/${code}/views/live`, 60_000);
  const info = useApi<CustomerInfo>(`/api/sites/${code}/customer`);
  const { tab, setTab } = useHashTab(["live", "health", "whatif", "problems", "ask"], "live");
  const l = live.data;
  const sys = info.data?.system;
  const ok = l && !l.error;

  return (
    <div className="pb-10">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href="/staff#sites" className="text-sm text-muted hover:underline">All sites</Link>
          <h1 className="font-display text-3xl font-semibold">{name}</h1>
          {ok && <p className={`mt-1 ${l.stale || l.inverter.fault ? "text-alarm" : "text-muted"}`}>{l.headline}</p>}
          {l?.device && (
            <p className={`mt-2 inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm ${l.device.connected ? "bg-[#ecf8f2] text-charge" : "bg-[#fdeeee] text-alarm"}`}>
              <span className={`h-2 w-2 rounded-full ${l.device.connected ? "bg-charge" : "bg-alarm"}`} />
              Link {l.device.connected ? "online" : "not sending"}, last reading {l.device.last_seen_minutes} min ago
              {l.device.readings_today !== null && `, ${l.device.readings_today}/${l.device.readings_expected_today} readings today`}
            </p>
          )}
        </div>
        <Link href={`/report/${code}`} className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-sky">Battery report</Link>
      </div>
      {ok && (
        <dl className="mb-2 grid grid-cols-3 gap-2 sm:grid-cols-6">
          <Stat k="SOC" v={`${l.battery.percent}%`} tone="text-charge" />
          <Stat k="PV" v={kw(l.solar_w)} tone="text-[#9a7400]" />
          <Stat k="Load" v={`${kw(l.house_w)} (${l.inverter.load_percent}%)`} />
          <Stat k="Grid" v={l.nepa_on ? "On" : "Off"} tone={l.nepa_on ? "text-nepa" : "text-muted"} />
          <Stat k="Battery temp" v={l.battery.temp_c !== null ? `${Math.round(l.battery.temp_c)}°C` : "–"} tone={l.battery.hot ? "text-warn" : ""} />
          <Stat k="Mode" v={l.inverter.mode} />
        </dl>
      )}

      <TabBar label="Site sections" active={tab} onChange={setTab} tabs={[
        { id: "live", label: "Live" }, { id: "health", label: "Health & history" }, { id: "whatif", label: "What-if" },
        { id: "problems", label: "Problems", badge: ok ? l.problems.length : undefined }, { id: "ask", label: "Ask Dokta" },
      ]} />

      {tab === "live" && (
        <div className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-[1.65fr_1fr]">
            {live.loading && !l ? <Loading what="live data" /> : ok ? <LiveSystem code={code} live={l} />
              : <Failed message={live.error ?? l?.error ?? "No data"} />}
            <div className="space-y-5">
              <Section title="Customer and system">
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  <div><dt className="text-muted">Customer</dt><dd className="font-medium">{info.data?.customer?.full_name ?? "Not linked"}</dd></div>
                  <div><dt className="text-muted">WhatsApp</dt><dd className="font-medium">{info.data?.customer?.whatsapp_number ?? "–"}</dd></div>
                  {sys && <>
                    <div><dt className="text-muted">PV strings</dt><dd className="font-medium">{sys.pv1_kwp} + {sys.pv2_kwp} kWp</dd></div>
                    <div><dt className="text-muted">Inverter</dt><dd className="font-medium">{sys.inverter_kw} kW, {sys.mode}</dd></div>
                    <div><dt className="text-muted">Battery</dt><dd className="font-medium">{sys.battery_kwh} kWh {sys.battery}</dd></div>
                    <div><dt className="text-muted">Tilt / azimuth</dt><dd className="font-medium">{sys.tilt}° / {sys.azimuth}°</dd></div>
                    <div><dt className="text-muted">Tariff band</dt><dd className="font-medium">{sys.tariff_band}</dd></div>
                    <div><dt className="text-muted">Installed</dt><dd className="font-medium">{info.data?.install_date ?? "–"}</dd></div>
                  </>}
                </dl>
              </Section>
              <DemoPanel code={code} onChanged={live.reload} />
            </div>
          </div>
          <TodayChart code={code} />
        </div>
      )}

      {tab === "health" && (
        <div className="space-y-5">
          <HistoryCharts code={code} />
          <div className="grid gap-5 lg:grid-cols-2">
            <BatteryHealth code={code} />
            <HeatWatch code={code} />
          </div>
          <LightTracker code={code} />
        </div>
      )}
      {tab === "whatif" && <WhatIf code={code} />}
      {tab === "problems" && <Section title="Problems at this site"><ProblemsInbox site={code} /></Section>}
      {tab === "ask" && <AskDokta code={code} staff />}
    </div>
  );
}

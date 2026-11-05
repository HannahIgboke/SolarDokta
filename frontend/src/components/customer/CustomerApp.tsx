"use client";
// The customer's app, in five tabs instead of one long page:
//   Home      what's happening right now (live picture, can I use..., problems, tonight)
//   My usage  any day or range of days, light tracker, heat watch, money, battery health
//   Learn     every solar word explained with pictures and small things to try
//   Tell us   receipts, fuel price, voice notes, photos, appliances
//   Ask Dokta chat by typing or voice, in English, Pidgin or Igbo
import { useCallback, useEffect, useState } from "react";
import type { Me } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import type { Live } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Failed, Loading } from "../Section";
import { AskDokta } from "./AskDokta";
import { BatteryHealth } from "./BatteryHealth";
import { CanIUse } from "./CanIUse";
import { HeatWatch } from "./HeatWatch";
import { PhoneAlerts } from "../PhoneAlerts";
import { DeviceBadge, ElNinoBanner } from "./HomeExtras";
import { Learn } from "./Learn";
import { LightTracker } from "./LightTracker";
import { LiveSystem } from "./LiveSystem";
import { Money } from "./Money";
import { Problems } from "./Problems";
import { StatusHeader } from "./StatusHeader";
import { TonightTomorrow } from "./TonightTomorrow";
import { UsageExplorer } from "./UsageExplorer";
import { YourInputs } from "./YourInputs";

type Tab = "home" | "usage" | "learn" | "tell" | "ask";
const TABS: Tab[] = ["home", "usage", "learn", "tell", "ask"];

function TabIcon({ tab }: { tab: Tab }) {
  const p = { fill: "none", stroke: "currentColor", strokeWidth: 1.9, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true">
      {tab === "home" && <path {...p} d="M3 11 12 4l9 7M5 10v10h14V10M10 20v-5h4v5" />}
      {tab === "usage" && <path {...p} d="M4 20V10M10 20V4M16 20v-7M22 20H2" />}
      {tab === "learn" && <><path {...p} d="M2 7l10-4 10 4-10 4Z" /><path {...p} d="M6 9v5c3 3 9 3 12 0V9" /></>}
      {tab === "tell" && <><path {...p} d="M4 4h16v12H8l-4 4Z" /><path {...p} d="M8 9h8M8 12h5" /></>}
      {tab === "ask" && <><rect {...p} x="9" y="3" width="6" height="11" rx="3" /><path {...p} d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>}
    </svg>
  );
}

export function CustomerApp({ me, code }: { me: Me; code: string }) {
  const { t, lang } = useLang();
  const [tab, setTabState] = useState<Tab>("home");
  const [learnStart, setLearnStart] = useState<string | undefined>();
  const { data: live, error, loading, reload } = useApi<Live>(`/api/sites/${code}/views/live?lang=${lang}`, 60_000);

  useEffect(() => {
    const h = window.location.hash.slice(1) as Tab;
    if (TABS.includes(h)) setTabState(h);
  }, []);
  const setTab = useCallback((next: Tab, opts?: { learn?: string; anchor?: string }) => {
    setTabState(next);
    if (opts?.learn) setLearnStart(opts.learn);
    history.replaceState(null, "", `#${next}`);
    setTimeout(() => {
      if (opts?.anchor) document.getElementById(opts.anchor)?.scrollIntoView({ behavior: "smooth", block: "start" });
      else window.scrollTo({ top: 0, behavior: "smooth" });
    }, 60);
  }, []);

  if (loading && !live) return <Loading what="your system" />;
  if (error && !live) return <Failed message={error} />;
  if (!live || live.error) return <Failed message={live?.error ?? "No data from this system yet."} />;

  return (
    <div className="pb-24 lg:pb-6">
      {/* desktop tabs */}
      <nav aria-label="Sections" className="sticky top-0 z-20 -mx-4 mb-6 hidden bg-sky/90 px-4 py-3 backdrop-blur lg:block">
        <div className="flex gap-1.5">
          {TABS.map((x) => (
            <button key={x} onClick={() => setTab(x)} aria-current={tab === x ? "page" : undefined}
                    className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold ${tab === x ? "bg-ink text-sky" : "text-muted hover:bg-white hover:text-ink"}`}>
              <TabIcon tab={x} /> {t(`nav.${x}`)}
            </button>
          ))}
        </div>
      </nav>

      {tab === "home" && (
        <div className="space-y-5">
          <StatusHeader name={me.full_name} live={live} />
          <DeviceBadge device={live.device} onLearn={() => setTab("learn", { learn: "link" })} />
          <ElNinoBanner onMore={() => setTab("usage", { anchor: "heat" })} />
          <PhoneAlerts />
          <div className="grid gap-5 lg:grid-cols-[1.65fr_1fr]">
            <LiveSystem code={code} live={live} />
            <div className="space-y-5">
              <CanIUse code={code} appliances={live.appliances} />
              <Problems code={code} />
              <button onClick={() => setTab("learn", { learn: "group" })} className="text-sm font-medium underline">{t("home.learnLink")}</button>
            </div>
          </div>
          <TonightTomorrow code={code} />
        </div>
      )}

      {tab === "usage" && (
        <div className="space-y-5">
          <h2 className="font-display text-3xl font-semibold">{t("usage.title")}</h2>
          <UsageExplorer code={code} />
          <div className="grid gap-5 lg:grid-cols-2">
            <div id="heat" className="scroll-mt-20"><HeatWatch code={code} /></div>
            <BatteryHealth code={code} />
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <LightTracker code={code} />
            <Money code={code} />
          </div>
        </div>
      )}

      {tab === "learn" && <Learn key={learnStart} live={live} start={learnStart} />}
      {tab === "tell" && <YourInputs code={code} onSaved={reload} />}
      {tab === "ask" && <AskDokta code={code} />}

      {/* phone tabs */}
      <nav aria-label="Sections" className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
        <div className="mx-auto grid max-w-lg grid-cols-5">
          {TABS.map((x) => (
            <button key={x} onClick={() => setTab(x)} aria-current={tab === x ? "page" : undefined}
                    className={`flex flex-col items-center gap-0.5 py-2.5 text-[11px] font-semibold ${tab === x ? "text-ink" : "text-muted"}`}>
              <span className={`grid h-8 w-12 place-items-center rounded-full ${tab === x ? "bg-sun" : ""}`}><TabIcon tab={x} /></span>
              {t(`nav.${x}`)}
            </button>
          ))}
        </div>
      </nav>

      {tab !== "ask" && (
        <button onClick={() => setTab("ask")}
                className="fixed right-5 bottom-5 z-30 hidden items-center gap-2 rounded-full bg-ink px-5 py-3 font-semibold text-sky shadow-lg shadow-ink/30 lg:flex">
          <span className="h-2.5 w-2.5 rounded-full bg-sun" /> {t("nav.ask")}
        </button>
      )}
    </div>
  );
}

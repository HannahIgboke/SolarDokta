"use client";
// The top of the customer's Home: a greeting, one plain sentence, and the four live numbers.
import { useLang } from "@/lib/i18n";
import type { Live } from "@/lib/types";
import { kw } from "@/lib/useApi";

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="min-w-0 rounded-2xl bg-white/70 px-4 py-3">
      <p className="text-xs text-muted">{label}</p>
      <p className={`font-display text-2xl font-semibold ${tone}`}>{value}</p>
    </div>
  );
}

export function StatusHeader({ name, live }: { name: string | null; live: Live }) {
  const { t } = useLang();
  const h = new Date().getHours();
  const greet = t(h < 12 ? "greet.morning" : h < 17 ? "greet.afternoon" : "greet.evening");
  return (
    <div>
      <p className="text-muted">{greet}{name ? `, ${name.split(" ")[0]}` : ""}</p>
      <h1 className={`mt-1 max-w-3xl font-display text-2xl leading-snug font-semibold md:text-[2rem] ${
        live.stale || live.inverter.fault ? "text-alarm" : ""}`}>
        {live.headline}
      </h1>
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label={t("stat.battery")} value={`${live.battery.percent}%`} tone="text-charge" />
        <Stat label={t("stat.solar")} value={kw(live.solar_w)} tone="text-[#9a7400]" />
        <Stat label={t("stat.using")} value={kw(live.house_w)} tone="" />
        <Stat label={t("stat.nepa")} value={live.nepa_on ? t("on") : t("off")} tone={live.nepa_on ? "text-nepa" : "text-muted"} />
      </div>
    </div>
  );
}

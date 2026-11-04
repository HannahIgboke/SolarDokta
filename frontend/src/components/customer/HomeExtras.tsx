"use client";
// Two strips on the customer's Home: the SolarDokta Link (is the box on the inverter sending
// readings?) and the El Niño season warning.
import { useLang } from "@/lib/i18n";
import type { Device } from "@/lib/types";

export function DeviceBadge({ device, onLearn }: { device?: Device; onLearn: () => void }) {
  const { t } = useLang();
  if (!device) return null;
  const ok = device.connected;
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border px-4 py-3 text-sm ${ok ? "border-[#bfe6d3] bg-[#ecf8f2]" : "border-[#f3c4c4] bg-[#fdeeee]"}`}>
      <span className="relative flex h-3 w-3 shrink-0">
        {ok && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-charge opacity-50 motion-reduce:hidden" />}
        <span className={`relative inline-flex h-3 w-3 rounded-full ${ok ? "bg-charge" : "bg-alarm"}`} />
      </span>
      <svg viewBox="0 0 40 28" className="h-6 w-8 shrink-0" aria-hidden="true">
        <rect x="1" y="4" width="26" height="20" rx="4" fill="#f2b705" />
        <circle cx="21" cy="10" r="2.2" fill={ok ? "#1e9e6a" : "#c93636"} />
        <path d="M30 9q4 5 0 10M34 6q6 8 0 16" fill="none" stroke="#16233f" strokeWidth="2" strokeLinecap="round" opacity={ok ? 1 : 0.3} />
      </svg>
      <strong className="font-semibold">{t(ok ? "device.connected" : "device.offline")}</strong>
      <span className="text-muted">{t("device.seen", { n: device.last_seen_minutes })}</span>
      {device.readings_today !== null && <span className="text-muted">{t("device.readings", { n: device.readings_today })}</span>}
      <span className="text-muted">{t("device.via", { how: device.connection })}{device.simulated ? `, ${t("device.simulated")}` : ""}</span>
      <button onClick={onLearn} className="ml-auto font-medium underline">{t("device.what")}</button>
    </div>
  );
}

export function ElNinoBanner({ onMore }: { onMore: () => void }) {
  const { t } = useLang();
  return (
    <div className="flex flex-col gap-3 overflow-hidden rounded-2xl bg-gradient-to-r from-[#b4400f] to-[#7a2913] p-4 text-white sm:flex-row sm:items-center sm:gap-5 sm:p-5">
      <svg viewBox="0 0 48 48" className="h-12 w-12 shrink-0" aria-hidden="true">
        <circle cx="24" cy="24" r="10" fill="#ffd34d" />
        {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
          <path key={a} d="M24 4v6" stroke="#ffd34d" strokeWidth="3" strokeLinecap="round" transform={`rotate(${a} 24 24)`} />
        ))}
      </svg>
      <div className="flex-1">
        <p className="font-display text-lg font-semibold">{t("elnino.title")}</p>
        <p className="text-white/85">{t("elnino.body")}</p>
      </div>
      <button onClick={onMore} className="shrink-0 rounded-full bg-white px-4 py-2 text-sm font-semibold text-[#7a2913]">
        {t("elnino.link")}
      </button>
    </div>
  );
}

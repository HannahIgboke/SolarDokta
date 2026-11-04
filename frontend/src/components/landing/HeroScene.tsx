"use client";
// One day in a Lagos home, played in about 20 seconds: the sun crosses, the battery fills and
// empties, NEPA comes and goes, and SolarDokta sends the messages it would really send.
import { useEffect, useState } from "react";

type Msg = { at: number; text: string; tone: "ok" | "warn" | "info" };
const MESSAGES: Msg[] = [
  { at: 6.8, text: "Good morning. The sun is up and your battery is charging again.", tone: "ok" },
  { at: 10.7, text: "Panel group 2 stopped producing at 10:40. Your installer has been told.", tone: "warn" },
  { at: 13.5, text: "Battery is full. Good time to iron or pump water.", tone: "ok" },
  { at: 19.2, text: "NEPA is off. Your battery will last until 6 am if the AC stays off.", tone: "info" },
  { at: 22.4, text: "Heatwave tomorrow (38°C). Keep the battery room airy.", tone: "warn" },
];
const DAY_SECONDS = 20;                         // one simulated day

function battery(t: number) {                   // % through the day
  if (t < 6.5) return 62 - (t / 6.5) * 18;
  if (t < 13) return 44 + ((t - 6.5) / 6.5) * 56;
  if (t < 17.5) return 100;
  return 100 - ((t - 17.5) / 6.5) * 38;
}
const nepaOn = (t: number) => (t >= 3 && t < 6) || (t >= 15 && t < 18.5);   // about 6 hours of light
const fmt = (t: number) => {
  const h = Math.floor(t) % 24, m = Math.floor((t % 1) * 60);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
};

export function HeroScene() {
  const [t, setT] = useState(13.6);
  const [still, setStill] = useState(false);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setStill(reduce);
    if (reduce) return;
    const start = performance.now() - (5.5 / 24) * DAY_SECONDS * 1000;
    let id = 0;
    const step = (now: number) => {
      setT((((now - start) / 1000 / DAY_SECONDS) * 24) % 24);
      id = requestAnimationFrame(step);
    };
    id = requestAnimationFrame(step);
    return () => cancelAnimationFrame(id);
  }, []);

  const day = t > 6 && t < 18.6;
  const sunAngle = Math.PI * ((t - 6) / 12.6);
  const sunX = 140 + 920 * ((t - 6) / 12.6);
  const sunY = 250 - Math.sin(sunAngle) * 200;
  const strength = day ? Math.max(0, Math.sin(sunAngle)) : 0;
  const pv2Dead = t >= 10.67;
  const soc = battery(t);
  const grid = nepaOn(t);
  const shown = still ? MESSAGES.slice(1, 4) : MESSAGES.filter((m) => m.at <= t).slice(-3);

  return (
    <div className="relative overflow-hidden rounded-[28px] border border-white/10 bg-[#0d1830]">
      <svg viewBox="0 0 1200 360" preserveAspectRatio="xMidYMid slice" className="block h-[190px] w-full sm:h-auto" role="img"
           aria-label="A house with solar panels, a battery and NEPA over one day">
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={day ? "#3f6fb5" : "#0d1830"} />
            <stop offset="1" stopColor={day ? "#f6c95a" : "#1c2b4d"} stopOpacity={day ? 0.55 + strength * 0.3 : 1} />
          </linearGradient>
          <radialGradient id="glow"><stop offset="0" stopColor="#ffd34d" stopOpacity="0.8" /><stop offset="1" stopColor="#ffd34d" stopOpacity="0" /></radialGradient>
        </defs>
        <rect width="1200" height="360" fill="url(#sky)" style={{ transition: "fill 0.6s" }} />
        {!day && [80, 260, 410, 640, 790, 980, 1130].map((x, i) => (
          <circle key={x} cx={x} cy={40 + (i % 3) * 38} r="1.6" fill="#eef2f5" opacity="0.7" />
        ))}
        {day && <><circle cx={sunX} cy={sunY} r="70" fill="url(#glow)" /><circle cx={sunX} cy={sunY} r="26" fill="#ffd34d" /></>}
        {!day && <circle cx="1040" cy="70" r="20" fill="#e9edf5" opacity="0.85" />}

        {/* ground */}
        <path d="M0 300 Q300 285 600 296 T1200 292 V360 H0Z" fill="#203a2c" />

        {/* NEPA pole and line */}
        <g transform="translate(110 150)">
          <rect x="-4" y="0" width="8" height="150" fill="#5b4a3a" />
          <rect x="-34" y="10" width="68" height="6" fill="#5b4a3a" />
          <circle cx="0" cy="-10" r="9" fill={grid ? "#7ea2ff" : "#3a4660"} />
          <text x="0" y="-28" textAnchor="middle" fontSize="15" fill="#eef2f5" fontWeight="600">NEPA {grid ? "on" : "off"}</text>
        </g>
        <path d="M144 163 Q400 200 640 220" fill="none" stroke={grid ? "#7ea2ff" : "#3a4660"} strokeWidth="2.5"
              className={grid ? "twin-flow" : ""} />

        {/* house */}
        <g transform="translate(560 130)">
          <rect x="0" y="86" width="260" height="84" fill="#e9e1d3" />
          {/* roof, seen from the front, with panel group 1 (left) and group 2 (right) */}
          <path d="M-16 88 L274 88 L214 18 L46 18 Z" fill="#8a4b2f" />
          <rect x="105" y="110" width="50" height="60" fill="#6b4a2e" />
          <rect x="30" y="104" width="46" height="36" fill={day ? "#9bb4d6" : "#ffd98a"} />
          <rect x="185" y="104" width="46" height="36" fill={day ? "#9bb4d6" : "#ffd98a"} />
          {[0, 1, 2].map((i) => {
            const x = 30 + i * 34;
            return <path key={`a${i}`} d={`M${x} 80 L${x + 30} 80 L${x + 38} 28 L${x + 12} 28 Z`}
                         fill="#2d4f86" stroke="#9fb7e0" strokeWidth="1.4" opacity={0.65 + strength * 0.35} />;
          })}
          {[0, 1].map((i) => {
            const x = 150 + i * 36;
            return <path key={`b${i}`} d={`M${x} 80 L${x + 32} 80 L${x + 24} 28 L${x - 2} 28 Z`}
                         fill={pv2Dead ? "#4a4f5c" : "#2d4f86"} stroke={pv2Dead ? "#ffb347" : "#9fb7e0"} strokeWidth="1.4" />;
          })}
          {pv2Dead && <g><circle cx="186" cy="12" r="11" fill="#c46a00" /><text x="186" y="17" textAnchor="middle" fontSize="15" fontWeight="800" fill="#fff">!</text></g>}
        </g>

        {/* battery */}
        <g transform="translate(870 190)">
          <rect x="0" y="0" width="64" height="104" rx="8" fill="#1a2a48" stroke="#eef2f5" strokeWidth="2.5" />
          <rect x="22" y="-8" width="20" height="8" rx="2" fill="#eef2f5" />
          <rect x="6" y={6 + 92 * (1 - soc / 100)} width="52" height={92 * (soc / 100)} rx="4"
                fill={soc > 30 ? "#1e9e6a" : "#c93636"} />
          <text x="32" y="130" textAnchor="middle" fontSize="20" fontWeight="700" fill="#eef2f5">{Math.round(soc)}%</text>
        </g>
        <path d="M820 270 H868" stroke="#1e9e6a" strokeWidth="3" className={day || !grid ? "twin-flow" : ""} />

        {/* clock */}
        <g transform="translate(1100 300)">
          <text textAnchor="end" fontSize="26" fontWeight="700" fill="#eef2f5">{fmt(t)}</text>
        </g>
      </svg>

      <ol aria-live="polite" className="flex min-h-[132px] flex-col justify-end gap-2 p-3 sm:pointer-events-none sm:absolute sm:top-4 sm:right-4 sm:min-h-0 sm:w-[340px] sm:items-end sm:justify-start sm:p-0">
        {shown.map((m, i) => (
          <li key={m.at} className={`msg-in w-full ${i < shown.length - 2 ? "hidden sm:block" : ""} rounded-2xl rounded-tr-sm bg-white/95 px-3.5 py-2.5 text-[13px] leading-snug text-ink shadow-lg sm:text-sm`}>
            <span className={`mr-1.5 inline-block h-2 w-2 rounded-full align-middle ${m.tone === "warn" ? "bg-warn" : m.tone === "ok" ? "bg-charge" : "bg-nepa"}`} />
            {m.text}
          </li>
        ))}
      </ol>
    </div>
  );
}

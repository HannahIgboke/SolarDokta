"use client";
// The live "digital twin": a drawing of the customer's own system that moves with the real data.
// Panels on the roof (one slope per string), inverter and battery inside, their appliances,
// and the NEPA pole outside. Moving lines show where power is flowing; thicker = more watts.
// Every part can be clicked (or reached with Tab + Enter) to see its details.
import type { Live, PanelString } from "@/lib/types";
import { kw } from "@/lib/useApi";
import { applianceLabel, applianceShort } from "@/lib/labels";
import { ApplianceIcon } from "./ApplianceIcon";

export type Part = "string-1" | "string-2" | "inverter" | "battery" | "nepa" | "home";

const C = {
  ink: "#16233f", panel: "#3b5b92", sun: "#f2b705", charge: "#1e9e6a", nepa: "#4c6ef5",
  warn: "#c46a00", alarm: "#c93636", muted: "#8a96a8", line: "#d5dde6",
};

function Flow({ d, watts, color, peak, reverse = false, label, lx, ly }: {
  d: string; watts: number; color: string; peak: number; reverse?: boolean;
  label?: string; lx?: number; ly?: number;
}) {
  const active = watts >= 20;
  const width = active ? 2.5 + 6 * Math.min(1, watts / peak) : 1.5;
  const seconds = active ? Math.max(0.35, 1.6 - 1.2 * Math.min(1, watts / peak)) : 0;
  return (
    <g>
      <path d={d} fill="none" stroke={active ? color : C.line} strokeOpacity={active ? 0.25 : 1}
            strokeWidth={width + 3} strokeLinecap="round" />
      {active && (
        <path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round"
              className="twin-flow" style={{ animationDuration: `${seconds}s`,
                animationDirection: reverse ? "reverse" : "normal" }} />
      )}
      {label && lx !== undefined && (
        <text x={lx} y={ly} fontSize="13" fontWeight="600" fill={active ? C.ink : C.muted}>{label}</text>
      )}
    </g>
  );
}

function Clickable({ part, selected, onSelect, label, children }: {
  part: Part; selected: Part | null; onSelect: (p: Part) => void; label: string;
  children: React.ReactNode;
}) {
  return (
    <g role="button" tabIndex={0} aria-label={label} aria-pressed={selected === part}
       className={`twin-part ${selected === part ? "twin-selected" : ""}`}
       onClick={() => onSelect(part)}
       onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(part))}>
      {children}
    </g>
  );
}

function Panels({ s, x0, y0, angle }: { s: PanelString; x0: number; y0: number; angle: number }) {
  const shown = Math.min(Math.max(s.panels, 2), 8);
  const span = 210, gap = 4, w = span / shown - gap;
  const fill = s.status === "dead" ? "#9aa5b4" : C.panel;
  return (
    <g transform={`translate(${x0} ${y0}) rotate(${angle})`}>
      {Array.from({ length: shown }, (_, i) => {
        const x = 18 + i * (w + gap);
        return (
          <g key={i}>
            <rect x={x} y={-21} width={w} height={18} rx={2} fill={fill}
                  stroke={s.status === "weak" ? C.warn : "#eef2f5"} strokeWidth={s.status === "weak" ? 2.5 : 1} />
            <path d={`M${x} ${-12} h${w} M${x + w / 2} ${-21} v18`} stroke="#eef2f5" strokeOpacity="0.6" strokeWidth="0.8" />
            {s.status === "dusty" && <rect x={x} y={-21} width={w} height={18} rx={2} fill="url(#dust)" />}
            {s.status === "shaded" && i >= shown / 2 && (
              <rect x={x} y={-21} width={w} height={18} rx={2} fill={C.ink} fillOpacity="0.5" />
            )}
          </g>
        );
      })}
      {s.status === "dead" && (
        <g transform={`translate(${18 + span / 2 - 12} -26)`}>
          <circle cx="12" cy="13" r="12" fill={C.alarm} />
          <path d="M7.5 8.5l9 9M16.5 8.5l-9 9" stroke="white" strokeWidth="2.4" strokeLinecap="round" />
        </g>
      )}
    </g>
  );
}

function StringTag({ s, x, y }: { s: PanelString; x: number; y: number }) {
  const tone = s.status === "dead" ? C.alarm : s.status === "ok" ? C.ink : C.warn;
  const word = s.status === "ok" ? kw(s.now_w) : s.status === "dead" ? "not working" : s.status;
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x="-4" y="-14" width="104" height="20" rx="10" fill="#ffffff" fillOpacity="0.85" />
      <text x="48" y="0.5" textAnchor="middle" fontSize="11.5" fontWeight="600" fill={tone}>
        Panel group {s.number}: {word}
      </text>
    </g>
  );
}

export function Twin({ live, selected, onSelect }: {
  live: Live; selected: Part | null; onSelect: (p: Part) => void;
}) {
  const day = live.is_day;
  const peak = Math.max(1500, live.inverter.kw * 1000 * 0.6);
  const b = live.battery;
  const level = Math.max(0.02, Math.min(1, b.percent / 100));
  const battColor = b.hot ? C.warn : b.percent < 20 ? C.alarm : C.charge;
  const [s1, s2] = live.strings;
  const apps = live.appliances.slice(0, 12);
  const battFlow = Math.abs(b.power_w);

  return (
    <svg viewBox="0 0 800 470" className="h-auto w-full" role="group"
         aria-label={`Live picture of your system. ${live.headline}`}>
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={day ? "#bcd7ee" : "#16233f"} />
          <stop offset="1" stopColor={day ? "#eef2f5" : "#2a3d63"} />
        </linearGradient>
        <radialGradient id="glow">
          <stop offset="0" stopColor={C.sun} stopOpacity="0.55" />
          <stop offset="1" stopColor={C.sun} stopOpacity="0" />
        </radialGradient>
        <pattern id="dust" width="6" height="6" patternUnits="userSpaceOnUse">
          <rect width="6" height="6" fill="#b08550" fillOpacity="0.6" />
          <circle cx="2" cy="2" r="1.2" fill="#6e4f2a" fillOpacity="0.8" />
          <circle cx="5" cy="4.5" r="1" fill="#6e4f2a" fillOpacity="0.7" />
        </pattern>
      </defs>

      {/* sky and ground */}
      <rect width="800" height="470" rx="14" fill="url(#sky)" />
      <rect y="428" width="800" height="42" fill={day ? "#cfd9cb" : "#1d2b47"} />
      {day ? (
        <g opacity={0.35 + 0.65 * live.sun}>
          <circle cx="86" cy="78" r={70} fill="url(#glow)" />
          <circle cx="86" cy="78" r={22 + 12 * live.sun} fill={C.sun} />
        </g>
      ) : (
        <g>
          <circle cx="90" cy="76" r="20" fill="#e8ecf3" />
          <circle cx="99" cy="70" r="18" fill="#1b2a4a" />
          {[[180, 40], [260, 80], [520, 50], [640, 95], [720, 40], [420, 30]].map(([x, y]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r="1.6" fill="#e8ecf3" opacity="0.8" />
          ))}
        </g>
      )}

      {/* NEPA pole and service wire */}
      <Clickable part="nepa" selected={selected} onSelect={onSelect}
                 label={`NEPA ${live.nepa_on ? "on" : "off"}`}>
        <rect x="660" y="140" width="110" height="295" fill="transparent" />
        <path d="M712 150 V430 M676 166 H748" stroke={C.ink} strokeWidth="5" strokeLinecap="round" />
        <path d="M684 166 v-8 M740 166 v-8" stroke={C.ink} strokeWidth="3" />
        <path d="M688 170 C 650 205, 610 222, 582 238" fill="none"
              stroke={live.nepa_on ? C.nepa : C.muted} strokeWidth={live.nepa_on ? 3 : 2}
              strokeDasharray={live.nepa_on ? undefined : "5 5"} />
        <g transform="translate(676 104)">
          <rect width="74" height="26" rx="13" fill={live.nepa_on ? C.nepa : "#ffffff"}
                stroke={live.nepa_on ? C.nepa : C.line} />
          <text x="37" y="17.5" textAnchor="middle" fontSize="12.5" fontWeight="700"
                fill={live.nepa_on ? "#ffffff" : C.muted}>NEPA {live.nepa_on ? "on" : "off"}</text>
        </g>
      </Clickable>

      {/* house */}
      <rect x="150" y="214" width="432" height="214" fill={day ? "#ffffff" : "#e3e9f1"} stroke={C.ink} strokeWidth="2.5" />
      <path d="M126 218 L366 118 L606 218 Z" fill={day ? "#dfe6ee" : "#c9d3df"} stroke={C.ink} strokeWidth="2.5" strokeLinejoin="round" />

      {s1 && (
        <Clickable part="string-1" selected={selected} onSelect={onSelect}
                   label={`Panel string 1: ${kw(s1.now_w)}, ${s1.status}`}>
          <Panels s={s1} x0={130} y0={214} angle={-22.1} />
          <StringTag s={s1} x={150} y={150} />
        </Clickable>
      )}
      {s2 && (
        <Clickable part="string-2" selected={selected} onSelect={onSelect}
                   label={`Panel string 2: ${kw(s2.now_w)}, ${s2.status}`}>
          <Panels s={s2} x0={366} y0={120} angle={22.1} />
          <StringTag s={s2} x={500} y={128} />
        </Clickable>
      )}

      {/* power lines inside */}
      <Flow d="M366 205 C 366 236, 214 228, 214 262" watts={live.solar_w} color={C.sun} peak={peak}
            label={`☀ ${kw(live.solar_w)}`} lx={300} ly={198} />
      <Flow d="M580 240 H 262 V 262" watts={live.nepa_w} color={C.nepa} peak={peak} />
      <Flow d="M250 318 H 292" watts={battFlow} color={C.charge} peak={peak} reverse={b.power_w < 0} />
      <Flow d="M250 296 C 300 296, 320 300, 360 300" watts={live.house_w} color={C.ink} peak={peak}
            label={`${kw(live.house_w)} in use`} lx={258} ly={286} />

      {/* inverter */}
      <Clickable part="inverter" selected={selected} onSelect={onSelect}
                 label={`Inverter ${live.inverter.kw} kW, ${live.inverter.load_percent}% loaded`}>
        <rect x="178" y="262" width="72" height="96" rx="8" fill={C.ink} />
        <rect x="186" y="274" width="56" height="26" rx="3" fill={live.inverter.fault ? C.alarm : "#a6e3c4"} />
        <text x="214" y="292" textAnchor="middle" fontSize="12" fontWeight="700" fill={C.ink}>
          {live.inverter.fault ? "FAULT" : kw(live.house_w)}
        </text>
        <circle cx="198" cy="320" r="4" fill={live.nepa_on ? C.nepa : "#3d4f73"} />
        <circle cx="214" cy="320" r="4" fill={live.solar_w > 20 ? C.sun : "#3d4f73"} />
        <circle cx="230" cy="320" r="4" fill={b.status !== "resting" ? C.charge : "#3d4f73"} />
        <text x="214" y="376" textAnchor="middle" fontSize="12" fill={C.ink}>Inverter</text>
      </Clickable>

      {/* battery */}
      <Clickable part="battery" selected={selected} onSelect={onSelect}
                 label={`Battery ${b.percent}%, ${b.status}`}>
        <rect x="306" y="252" width="16" height="8" rx="2" fill={C.ink} />
        <rect x="292" y="258" width="44" height="112" rx="6" fill="#ffffff" stroke={C.ink} strokeWidth="2.5" />
        <rect x="297" y={263 + 102 * (1 - level)} width="34" height={102 * level} rx="3" fill={battColor} />
        <text x="314" y="392" textAnchor="middle" fontSize="15" fontWeight="700" fill={C.ink}>{b.percent}%</text>
        <text x="314" y="408" textAnchor="middle" fontSize="11" fill={C.muted}>
          {b.status === "charging" ? "charging" : b.status === "discharging" ? "in use" : "resting"}
        </text>
      </Clickable>

      {/* appliances */}
      <Clickable part="home" selected={selected} onSelect={onSelect}
                 label={`Appliances: ${apps.filter((a) => a.on).length} probably on`}>
        <rect x="362" y="250" width="210" height="172" fill="transparent" />
        {apps.map((a, i) => {
          const cx = 392 + (i % 4) * 50, cy = 274 + Math.floor(i / 4) * 52;
          return (
            <g key={a.name} style={{ color: a.on ? C.ink : "#a3aebd" }}>
              <title>{`${applianceLabel(a.name)}: ${a.on ? "probably on" : "off"}`}</title>
              <circle cx={cx} cy={cy} r="18" fill={a.on ? "#fdf0c4" : "#f1f4f7"}
                      stroke={a.on ? C.sun : C.line} strokeWidth={a.on ? 2.5 : 1} />
              <ApplianceIcon name={a.name} x={cx - 10} y={cy - 10} />
              <text x={cx} y={cy + 30} textAnchor="middle" fontSize="9.5" fill={a.on ? C.ink : C.muted}>
                {applianceShort(a.name)}
              </text>
            </g>
          );
        })}
      </Clickable>
    </svg>
  );
}

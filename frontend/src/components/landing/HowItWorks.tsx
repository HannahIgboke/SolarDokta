"use client";
// How SolarDokta connects: the SolarDokta Link box on the inverter, the readings travelling every
// 5 minutes, the checks in the cloud, and the answers on WhatsApp and the technician's screen.
import { useEffect, useState } from "react";

const STEPS = [
  { title: "A small box plugs into your inverter",
    body: "The SolarDokta Link connects to the inverter's data port. No rewiring, no opening the battery. Installers fit it in about 15 minutes." },
  { title: "Every 5 minutes it sends a reading",
    body: "Sun on each panel group, battery level and temperature, what the house is using, and whether NEPA is on. It uses Wi-Fi, or a SIM card where there's no Wi-Fi." },
  { title: "SolarDokta checks it against the weather",
    body: "We know how much sun fell on your roof, so we know what your panels should have made. When the numbers don't add up, we find out why: dust, shade, a dead panel group, a tired battery." },
  { title: "You get a plain answer. Your installer gets the exact fault.",
    body: "You see “Can I use the iron?” answered in your language, on WhatsApp or the web. Your technician sees which site, which part, and what to bring." },
];

export function HowItWorks() {
  const [active, setActive] = useState(0);
  const [auto, setAuto] = useState(true);

  useEffect(() => {
    if (!auto || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => setActive((a) => (a + 1) % STEPS.length), 4500);
    return () => clearInterval(id);
  }, [auto]);

  const on = (i: number) => (active === i ? 1 : 0.5);

  return (
    <div className="grid items-center gap-10 lg:grid-cols-[1fr_1.15fr]">
      <ol className="space-y-2">
        {STEPS.map((s, i) => (
          <li key={s.title}>
            <button onClick={() => { setActive(i); setAuto(false); }} aria-pressed={active === i}
                    className={`flex w-full gap-4 rounded-2xl p-4 text-left transition-colors ${active === i ? "bg-white shadow-[0_1px_0_#d5dde6]" : "hover:bg-white/60"}`}>
              <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full font-display text-lg font-bold ${active === i ? "bg-sun text-ink" : "bg-line text-muted"}`}>{i + 1}</span>
              <span>
                <span className="block font-display text-lg leading-snug font-semibold">{s.title}</span>
                {active === i && <span className="mt-1 block text-muted">{s.body}</span>}
              </span>
            </button>
          </li>
        ))}
      </ol>

      <svg viewBox="0 0 640 420" className="h-auto w-full" role="img"
           aria-label="Diagram: inverter with the SolarDokta Link, readings sent to the cloud, answers to a phone and a laptop">
        <rect x="0" y="0" width="640" height="420" rx="28" fill="#16233f" />
        {/* inverter + link */}
        <g opacity={active <= 1 ? 1 : 0.6} style={{ transition: "opacity .4s" }}>
          <rect x="44" y="140" width="120" height="170" rx="12" fill="#e9edf3" />
          <rect x="62" y="162" width="84" height="40" rx="5" fill="#1d3a2e" />
          <text x="104" y="188" textAnchor="middle" fontSize="16" fill="#7ce3b0" fontWeight="700">78%</text>
          <text x="104" y="232" textAnchor="middle" fontSize="13" fill="#5e6b80">Inverter</text>
          <rect x="164" y="214" width="20" height="10" fill="#9aa7bb" />
          <g>
            <rect x="184" y="196" width="62" height="46" rx="9" fill="#f2b705" />
            <circle cx="234" cy="208" r="4.5" fill="#1e9e6a" className="led" />
            <text x="208" y="226" textAnchor="middle" fontSize="11" fontWeight="700" fill="#16233f">Link</text>
          </g>
          <text x="215" y="268" textAnchor="middle" fontSize="13" fill="#eef2f5" >SolarDokta Link</text>
        </g>

        {/* signal */}
        <g opacity={on(1)} style={{ transition: "opacity .4s" }}>
          {[0, 1, 2].map((i) => (
            <path key={i} d={`M${262 + i * 16} ${196 - i * 6} q14 22 0 46`} fill="none" stroke="#f2b705" strokeWidth="3"
                  strokeLinecap="round" className="wave" style={{ animationDelay: `${i * 0.25}s` }} />
          ))}
          <path d="M318 214 C360 180 380 140 410 128" fill="none" stroke="#f2b705" strokeWidth="2.5" className="twin-flow" />
          <text x="300" y="150" fontSize="13" fill="#eef2f5" textAnchor="end">every 5 minutes</text>
          <text x="300" y="168" fontSize="12" fill="#9fb0c8" textAnchor="end">Wi-Fi or SIM card</text>
        </g>

        {/* cloud */}
        <g opacity={on(2) + 0.2} style={{ transition: "opacity .4s" }}>
          <path d="M420 140 a34 34 0 0 1 12 -66 a46 46 0 0 1 88 -10 a32 32 0 0 1 40 46 a30 30 0 0 1 -12 30 Z" fill="#2c4470" stroke="#7ea2ff" strokeWidth="2" />
          <text x="490" y="104" textAnchor="middle" fontSize="15" fontWeight="700" fill="#eef2f5">SolarDokta</text>
          <text x="490" y="124" textAnchor="middle" fontSize="12" fill="#c6d3ea">checks + weather</text>
        </g>

        {/* outputs */}
        <g opacity={on(3)} style={{ transition: "opacity .4s" }}>
          <path d="M470 145 C450 200 420 230 404 262" fill="none" stroke="#1e9e6a" strokeWidth="2.5" className="twin-flow" />
          <path d="M520 145 C540 200 556 226 566 262" fill="none" stroke="#1e9e6a" strokeWidth="2.5" className="twin-flow" />
          {/* phone */}
          <rect x="360" y="262" width="86" height="140" rx="14" fill="#eef2f5" />
          <rect x="366" y="280" width="74" height="40" rx="8" fill="#ffffff" stroke="#d5dde6" />
          <text x="372" y="297" fontSize="10" fill="#16233f">Yes, iron now.</text>
          <text x="372" y="311" fontSize="10" fill="#16233f">Battery 78%</text>
          <text x="403" y="392" textAnchor="middle" fontSize="11" fill="#5e6b80">You</text>
          {/* laptop */}
          <rect x="506" y="276" width="116" height="78" rx="6" fill="#eef2f5" />
          <rect x="492" y="354" width="144" height="10" rx="3" fill="#c3ccd8" />
          <circle cx="536" cy="306" r="7" fill="#c93636" />
          <rect x="550" y="300" width="58" height="6" rx="3" fill="#9aa7bb" />
          <circle cx="536" cy="330" r="7" fill="#1e9e6a" />
          <rect x="550" y="324" width="44" height="6" rx="3" fill="#9aa7bb" />
          <text x="564" y="392" textAnchor="middle" fontSize="11" fill="#c6d3ea">Your installer</text>
        </g>
      </svg>
    </div>
  );
}

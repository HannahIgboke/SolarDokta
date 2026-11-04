"use client";
// "Learn": every solar word SolarDokta uses, with a picture, a plain explanation in the
// customer's language, how theirs is doing right now, and for some, a small thing to try.
import { useState } from "react";
import { useLang, type Lang } from "@/lib/i18n";
import type { Live } from "@/lib/types";
import { kw } from "@/lib/useApi";

type L3 = [string, string, string];
const I: Record<Lang, number> = { en: 0, pcm: 1, ig: 2 };

type Term = {
  id: string;
  title: L3;
  short: L3;
  body: L3;
  yours: (live: Live) => L3 | null;
  Picture: (p: { live: Live }) => React.ReactElement;
  Try?: (p: { lang: Lang }) => React.ReactElement;
};

const stroke = { fill: "none", stroke: "#16233f", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

function PanelArt({ x, y, w = 60, h = 40, dead = false, dusty = false }: { x: number; y: number; w?: number; h?: number; dead?: boolean; dusty?: boolean }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx="3" fill={dead ? "#6b7280" : "#2d4f86"} stroke="#16233f" strokeWidth="2" />
      {[1, 2].map((i) => <path key={`v${i}`} d={`M${x + (w / 3) * i} ${y} V${y + h}`} stroke="#9fb7e0" strokeWidth="1.2" />)}
      <path d={`M${x} ${y + h / 2} H${x + w}`} stroke="#9fb7e0" strokeWidth="1.2" />
      {dusty && [[8, 6], [22, 14], [40, 9], [50, 24], [14, 28], [33, 31]].map(([dx, dy]) => (
        <circle key={`${dx}-${dy}`} cx={x + (dx / 60) * w} cy={y + (dy / 40) * h} r="2.6" fill="#b08d5b" />
      ))}
    </g>
  );
}

const TERMS: Term[] = [
  {
    id: "panel",
    title: ["Solar panel", "Solar panel", "Panel anyanwụ"],
    short: ["Turns sunlight into electricity", "E dey change sunlight to light", "Na-agbanwe ìhè anyanwụ ka ọ bụrụ ọkụ"],
    body: [
      "The flat blue sheets on your roof. When sunlight falls on them they make electricity. More sun means more power, so they make most around midday and nothing at night.",
      "Na the flat blue things wey dey your roof. When sun touch dem, dem dey make light. Sun plenty, power plenty. Dem dey make pass for afternoon, and nothing for night.",
      "Ihe ndị na-acha anụnụ anụnụ dị n'elu ụlọ gị. Mgbe anyanwụ dakwasịrị ha, ha na-emepụta ọkụ. Anyanwụ ka ukwuu, ọkụ ka ukwuu. Ha na-emepụta kacha n'ehihie, ọ dịghị ihe n'abalị.",
    ],
    yours: (l) => [
      `Your panels are making ${kw(l.solar_w)} right now.`,
      `Your panels dey make ${kw(l.solar_w)} now.`,
      `Panel gị na-emepụta ${kw(l.solar_w)} ugbu a.`,
    ],
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <circle cx="48" cy="40" r="20" fill="#f2b705" />
        {[0, 1, 2].map((i) => <path key={i} d={`M${72 + i * 6} ${50 + i * 8} L${118 + i * 6} ${76 + i * 8}`} stroke="#f2b705" strokeWidth="3" strokeDasharray="6 5" />)}
        <PanelArt x={120} y={70} w={90} h={60} />
        <path d="M210 100 H245" {...stroke} stroke="#1e9e6a" strokeWidth="3" />
        <path d="M238 93 l8 7 -8 7" {...stroke} stroke="#1e9e6a" strokeWidth="3" />
      </svg>
    ),
  },
  {
    id: "group",
    title: ["Panel group (a “string”)", "Panel group (dem dey call am “string”)", "Otu panel (a na-akpọ ya “string”)"],
    short: ["Panels wired together in a line", "Panels wey dem join together", "Panel ndị e jikọtara ọnụ"],
    body: [
      "Installers wire panels together in groups, called strings. Your system has two groups. If one group stops, the other keeps working, so your lights still come on, just with less power. That's why a dead group can go unnoticed for months.",
      "Installer dey join panels together for groups, dem dey call am string. Your system get two groups. If one group stop, the other one go still work, so light go still dey but e no go strong. Na why person fit no notice for months.",
      "Ndị na-arụnye na-ejikọ panel ọnụ n'otu n'otu, a na-akpọ ha string. Usoro gị nwere otu abụọ. Ọ bụrụ na otu akwụsị, nke ọzọ na-arụ ọrụ, ya mere ọkụ ka na-enwu mana ọ dịghị ike. Ọ bụ ya mere enwere ike ọ gaghị ama ruo ọnwa ole na ole.",
    ],
    yours: (l) => {
      if (!l.is_day && !l.strings.some((s) => s.status === "dead")) {
        return ["It's night, so neither group is making power. Both were working normally today.",
                "Na night, so no group dey make power now. Both dey work well today.",
                "Ọ bụ abalị, ya mere otu ọ bụla anaghị emepụta ọkụ. Ha abụọ rụrụ ọrụ nke ọma taa."];
      }
      const parts = l.strings.map((s) => [
        `Group ${s.number}: ${s.status === "dead" ? "not working" : s.status === "ok" ? `making ${kw(s.now_w)}` : `${s.status}, making ${kw(s.now_w)}`}`,
        `Group ${s.number}: ${s.status === "dead" ? "no dey work" : `dey make ${kw(s.now_w)}`}`,
        `Otu ${s.number}: ${s.status === "dead" ? "anaghị arụ ọrụ" : `na-emepụta ${kw(s.now_w)}`}`,
      ]);
      return [0, 1, 2].map((i) => parts.map((p) => p[i]).join(". ") + ".") as L3;
    },
    Picture: ({ live }) => {
      const dead = (n: number) => live.strings.find((s) => s.number === n)?.status === "dead";
      return (
        <svg viewBox="0 0 260 160" className="h-full w-full">
          <text x="10" y="20" fontSize="12" fontWeight="700" fill="#16233f">Group 1</text>
          {[0, 1, 2].map((i) => <PanelArt key={i} x={10 + i * 44} y={28} w={40} h={28} dead={dead(1)} />)}
          <text x="10" y="92" fontSize="12" fontWeight="700" fill="#16233f">Group 2</text>
          {[0, 1].map((i) => <PanelArt key={i} x={10 + i * 44} y={100} w={40} h={28} dead={dead(2)} />)}
          <path d="M142 42 H190 V80" {...stroke} stroke={dead(1) ? "#9aa3b2" : "#1e9e6a"} strokeWidth="3" />
          <path d="M98 114 H190 V96" {...stroke} stroke={dead(2) ? "#9aa3b2" : "#1e9e6a"} strokeWidth="3" />
          <rect x="176" y="76" width="70" height="24" rx="6" fill="#16233f" />
          <text x="211" y="92" textAnchor="middle" fontSize="11" fill="#eef2f5">inverter</text>
        </svg>
      );
    },
    Try: ({ lang }) => {
      const [off, setOff] = useState(false);
      const power = off ? 72 : 100;
      return (
        <div>
          <button onClick={() => setOff(!off)} aria-pressed={off}
                  className={`rounded-full px-4 py-2 text-sm font-semibold ${off ? "bg-alarm text-white" : "bg-ink text-sky"}`}>
            {off ? ["Turn group 2 back on", "On group 2 back", "Gbanye otu 2 ọzọ"][I[lang]] : ["Switch group 2 off", "Off group 2", "Gbanyụọ otu 2"][I[lang]]}
          </button>
          <div className="mt-3 h-3 overflow-hidden rounded-full bg-sky"><div className="h-full rounded-full bg-sun transition-all" style={{ width: `${power}%` }} /></div>
          <p className="mt-2 text-sm">{[
            `Power from your panels: ${power}%. ${off ? "The lights stay on, so it's easy to miss. SolarDokta notices within minutes." : ""}`,
            `Power from your panels: ${power}%. ${off ? "Light still dey, so person fit no notice. SolarDokta go catch am quick." : ""}`,
            `Ọkụ site na panel gị: ${power}%. ${off ? "Ọkụ ka na-enwu, ya mere ọ dị mfe ịhụghị ya. SolarDokta na-ahụ ya ngwa ngwa." : ""}`,
          ][I[lang]]}</p>
        </div>
      );
    },
  },
  {
    id: "inverter",
    title: ["Inverter", "Inverter", "Inverter"],
    short: ["The box that runs everything", "The box wey run everything", "Igbe na-achịkwa ihe niile"],
    body: [
      "The inverter is the boss of your system. It takes power from the panels, the battery and NEPA, decides which to use, and turns it into the kind of power your sockets need. If too many big things run at once, it switches off to protect itself.",
      "Inverter na the oga of your system. E dey collect power from panels, battery and NEPA, choose which one to use, and change am to the kind light wey your socket need. If you put too many big things at once, e go off to protect itself.",
      "Inverter bụ onye isi usoro gị. Ọ na-anara ọkụ site na panel, batrị na NEPA, kpebie nke a ga-eji, ma gbanwee ya ka ọ dabara soket gị. Ọ bụrụ na ihe buru ibu dị ukwuu na-agba otu oge, ọ na-agbanyụ onwe ya iji chebe onwe ya.",
    ],
    yours: (l) => l.inverter.fault ? ["It is reporting a fault right now.", "E dey show fault now.", "Ọ na-egosi nsogbu ugbu a."] : [
      `It is working at ${l.inverter.load_percent}% of its ${l.inverter.kw} kW limit.`,
      `E dey work for ${l.inverter.load_percent}% of im ${l.inverter.kw} kW limit.`,
      `Ọ na-arụ ọrụ na ${l.inverter.load_percent}% nke ike ya bụ ${l.inverter.kw} kW.`,
    ],
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <rect x="95" y="35" width="70" height="90" rx="10" fill="#e9edf3" stroke="#16233f" strokeWidth="2" />
        <rect x="106" y="48" width="48" height="22" rx="4" fill="#1d3a2e" />
        <text x="130" y="63" textAnchor="middle" fontSize="11" fill="#7ce3b0">ON</text>
        <text x="20" y="40" fontSize="11" fill="#16233f">panels</text>
        <path d="M20 48 H92" {...stroke} stroke="#f2b705" strokeWidth="3" />
        <text x="20" y="84" fontSize="11" fill="#16233f">battery</text>
        <path d="M20 92 H92" {...stroke} stroke="#1e9e6a" strokeWidth="3" />
        <text x="20" y="126" fontSize="11" fill="#16233f">NEPA</text>
        <path d="M20 134 H70 V112 H92" {...stroke} stroke="#4c6ef5" strokeWidth="3" />
        <path d="M168 80 H215" {...stroke} strokeWidth="3" />
        <rect x="215" y="62" width="34" height="36" rx="6" fill="#fff" stroke="#16233f" strokeWidth="2" />
        <circle cx="227" cy="80" r="2.5" fill="#16233f" /><circle cx="237" cy="80" r="2.5" fill="#16233f" />
        <text x="232" y="114" textAnchor="middle" fontSize="11" fill="#16233f">socket</text>
      </svg>
    ),
  },
  {
    id: "battery",
    title: ["Battery and battery %", "Battery and battery %", "Batrị na pasentị batrị"],
    short: ["Stores power for night and blackouts", "E dey keep power for night and when light go", "Na-echekwa ọkụ maka abalị na mgbe ọkụ pụrụ"],
    body: [
      "The battery stores extra solar power so you have light at night and when NEPA is off. The % is how full it is, like a fuel gauge. Your inverter stops using it at a low level (about 20% for lithium) to protect it, so 20% means nearly empty.",
      "Battery dey keep extra solar power so you go get light for night and when NEPA no dey. The % na how full e be, like fuel gauge. Inverter go stop to use am when e low reach about 20% to protect am, so 20% mean say e don almost finish.",
      "Batrị na-echekwa ọkụ anyanwụ fọdụrụ ka ị nwee ọkụ n'abalị na mgbe NEPA anọghị. Pasentị bụ otú o si jupụta, dị ka ihe na-egosi mmanụ. Inverter na-akwụsị iji ya mgbe ọ ruru ihe dị ka 20% iji chebe ya, ya mere 20% pụtara na ọ fọrọ obere ka ọ gwụ.",
    ],
    yours: (l) => [
      `${l.battery.percent}% full, about ${l.battery.energy_left_kwh} kWh you can still use.`,
      `${l.battery.percent}% full, about ${l.battery.energy_left_kwh} kWh still dey to use.`,
      `O juru ${l.battery.percent}%, ihe dị ka ${l.battery.energy_left_kwh} kWh ka fọdụrụ.`,
    ],
    Picture: ({ live }) => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <rect x="90" y="30" width="80" height="115" rx="10" fill="#fff" stroke="#16233f" strokeWidth="3" />
        <rect x="115" y="20" width="30" height="10" rx="3" fill="#16233f" />
        <rect x="97" y={37 + 101 * (1 - live.battery.percent / 100)} width="66" height={101 * (live.battery.percent / 100)} rx="6" fill="#1e9e6a" />
        <path d="M86 117 H174" stroke="#c93636" strokeWidth="2" strokeDasharray="5 4" />
        <text x="180" y="121" fontSize="11" fill="#c93636">20%: nearly empty</text>
        <text x="130" y="96" textAnchor="middle" fontSize="20" fontWeight="800" fill="#16233f">{live.battery.percent}%</text>
      </svg>
    ),
    Try: ({ lang }) => {
      const [pct, setPct] = useState(70);
      const [watts, setWatts] = useState(400);
      const hours = Math.max(0, ((pct - 20) / 100) * 10 * 1000 * 0.95 / watts);
      return (
        <div className="space-y-3 text-sm">
          <label className="block">{["Battery level", "Battery level", "Ọkwa batrị"][I[lang]]}: <strong>{pct}%</strong>
            <input type="range" min={20} max={100} value={pct} onChange={(e) => setPct(Number(e.target.value))} className="mt-1 w-full accent-[#1e9e6a]" />
          </label>
          <label className="block">{["Your home is using", "Your house dey use", "Ụlọ gị na-eji"][I[lang]]}: <strong>{watts} W</strong>
            <input type="range" min={100} max={2500} step={50} value={watts} onChange={(e) => setWatts(Number(e.target.value))} className="mt-1 w-full accent-[#16233f]" />
          </label>
          <p className="rounded-2xl bg-sky px-3 py-2">{[
            `A 10 kWh battery would last about ${hours.toFixed(1)} hours.`,
            `10 kWh battery go last about ${hours.toFixed(1)} hours.`,
            `Batrị 10 kWh ga-adị ihe dị ka awa ${hours.toFixed(1)}.`,
          ][I[lang]]}</p>
        </div>
      );
    },
  },
  {
    id: "watts",
    title: ["Watts (W) and kWh", "Watts (W) and kWh", "Watts (W) na kWh"],
    short: ["Speed of power vs amount of energy", "How fast power dey go vs how much", "Ọsọ ọkụ na ole ọkụ"],
    body: [
      "Watts are like speed: how hard power is flowing right now. A fan uses about 70 W, a pressing iron about 1,000 W. Kilowatt-hours (kWh) are like distance: how much energy was used over time. A 1,000 W iron used for 1 hour uses 1 kWh.",
      "Watts be like speed: how hard power dey flow now. Fan dey use about 70 W, pressing iron about 1,000 W. kWh be like distance: how much energy you don use over time. If you use 1,000 W iron for 1 hour, na 1 kWh.",
      "Watts dị ka ọsọ: otú ọkụ si agba ugbu a. Fan na-eji ihe dị ka 70 W, ígwè ịgba akwa ihe dị ka 1,000 W. kWh dị ka anya ụzọ: ole ọkụ e jiri n'oge. Ígwè 1,000 W e jiri otu awa na-eri 1 kWh.",
    ],
    yours: (l) => [
      `Your home is using ${kw(l.house_w)} right now.`,
      `Your house dey use ${kw(l.house_w)} now.`,
      `Ụlọ gị na-eji ${kw(l.house_w)} ugbu a.`,
    ],
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <path d="M30 120 A50 50 0 0 1 130 120" {...stroke} strokeWidth="6" stroke="#d5dde6" />
        <path d="M30 120 A50 50 0 0 1 110 82" {...stroke} strokeWidth="6" stroke="#f2b705" />
        <path d="M80 120 L106 88" {...stroke} strokeWidth="3" />
        <text x="80" y="145" textAnchor="middle" fontSize="12" fontWeight="700" fill="#16233f">W = now</text>
        <rect x="155" y="78" width="90" height="36" rx="6" fill="#16233f" />
        <text x="200" y="102" textAnchor="middle" fontSize="16" fontWeight="700" fill="#7ce3b0">12.4 kWh</text>
        <text x="200" y="145" textAnchor="middle" fontSize="12" fontWeight="700" fill="#16233f">kWh = total</text>
      </svg>
    ),
    Try: ({ lang }) => {
      const items = [["Fan", 70], ["TV", 100], ["Fridge", 150], ["Pressing iron", 1000], ["AC", 1200]] as const;
      const [pick, setPick] = useState(3);
      const [hrs, setHrs] = useState(1);
      const kwh = (items[pick][1] * hrs) / 1000;
      return (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-1.5">
            {items.map(([n, w], i) => (
              <button key={n} onClick={() => setPick(i)} aria-pressed={pick === i}
                      className={`rounded-full px-3 py-1.5 ${pick === i ? "bg-ink text-sky" : "bg-sky"}`}>{n} ({w} W)</button>
            ))}
          </div>
          <label className="block">{["Hours used", "Hours", "Awa"][I[lang]]}: <strong>{hrs}</strong>
            <input type="range" min={0.5} max={8} step={0.5} value={hrs} onChange={(e) => setHrs(Number(e.target.value))} className="mt-1 w-full accent-[#f2b705]" />
          </label>
          <p className="rounded-2xl bg-sky px-3 py-2">{items[pick][1]} W × {hrs} h = <strong>{kwh.toFixed(2)} kWh</strong>
            {[` (about ${Math.round((kwh / 10) * 100)}% of a 10 kWh battery)`, ` (about ${Math.round((kwh / 10) * 100)}% of 10 kWh battery)`, ` (ihe dị ka ${Math.round((kwh / 10) * 100)}% nke batrị 10 kWh)`][I[lang]]}</p>
        </div>
      );
    },
  },
  {
    id: "nepa",
    title: ["NEPA (the grid)", "NEPA (the grid)", "NEPA (grid)"],
    short: ["Public electricity from the power company", "Government light", "Ọkụ ọha site n'ụlọ ọrụ ọkụ"],
    body: [
      "NEPA is the public electricity supply. When it's on, your inverter can use it to power the house and charge the battery. Since mid-October supply has been very poor in many areas, so your battery and panels are doing much more of the work.",
      "NEPA na government light. When e dey, inverter fit use am power house and charge battery. Since mid-October, light no dey well for many areas, so na battery and panels dey do most of the work.",
      "NEPA bụ ọkụ ọha. Mgbe ọ nọ, inverter gị nwere ike iji ya nye ụlọ ọkụ ma chaji batrị. Kemgbe etiti Ọktoba, ọkụ adịghị mma n'ọtụtụ ebe, ya mere batrị na panel na-arụ ọtụtụ ọrụ.",
    ],
    yours: (l) => l.nepa_on ? ["NEPA is on right now.", "NEPA dey now.", "NEPA nọ ugbu a."] : ["NEPA is off right now.", "NEPA no dey now.", "NEPA anọghị ugbu a."],
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <rect x="50" y="30" width="8" height="115" fill="#5b4a3a" /><rect x="28" y="38" width="52" height="6" fill="#5b4a3a" />
        <path d="M80 41 Q150 70 190 80" {...stroke} stroke="#4c6ef5" strokeWidth="3" />
        <path d="M160 92 L200 66 L240 92 V140 H160Z" fill="#e9e1d3" stroke="#16233f" strokeWidth="2" />
        <rect x="192" y="110" width="16" height="30" fill="#6b4a2e" />
      </svg>
    ),
  },
  {
    id: "link",
    title: ["SolarDokta Link", "SolarDokta Link", "SolarDokta Link"],
    short: ["The little box that reports your system", "The small box wey dey report your system", "Obere igbe na-akọ maka usoro gị"],
    body: [
      "A small box your installer plugs into the inverter's data port. Every 5 minutes it reads the panels, battery, inverter and NEPA and sends the numbers to SolarDokta over Wi-Fi or a SIM card. If it stops sending, we tell you and your installer.",
      "Small box wey installer go plug for inverter data port. Every 5 minutes e dey read panels, battery, inverter and NEPA, and send the numbers to SolarDokta through Wi-Fi or SIM. If e stop to send, we go tell you and your installer.",
      "Obere igbe onye na-arụnye na-etinye n'inverter. Kwa nkeji 5 ọ na-agụ panel, batrị, inverter na NEPA ma zipu ọnụọgụ na SolarDokta site na Wi-Fi ma ọ bụ SIM. Ọ bụrụ na ọ kwụsị izipu, anyị na-agwa gị na onye rụnyere ya.",
    ],
    yours: (l) => l.device ? (l.device.connected
      ? [`Connected. Last reading ${l.device.last_seen_minutes} min ago.`, `E dey connected. Last reading ${l.device.last_seen_minutes} min ago.`, `Ọ jikọrọ. Ozi ikpeazụ nkeji ${l.device.last_seen_minutes} gara aga.`]
      : ["Not sending readings right now.", "E no dey send readings now.", "Ọ naghị ezite ozi ugbu a."]) : null,
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <rect x="30" y="40" width="70" height="95" rx="8" fill="#e9edf3" stroke="#16233f" strokeWidth="2" />
        <text x="65" y="92" textAnchor="middle" fontSize="11" fill="#16233f">inverter</text>
        <rect x="100" y="80" width="14" height="8" fill="#9aa7bb" />
        <rect x="114" y="66" width="52" height="38" rx="8" fill="#f2b705" stroke="#16233f" strokeWidth="2" />
        <circle cx="155" cy="76" r="4" fill="#1e9e6a" className="led" />
        <text x="140" y="94" textAnchor="middle" fontSize="10" fontWeight="700" fill="#16233f">Link</text>
        {[0, 1, 2].map((i) => <path key={i} d={`M${178 + i * 14} ${68 - i * 6} q14 17 0 34`} {...stroke} stroke="#f2b705" strokeWidth="3" />)}
        <text x="205" y="130" textAnchor="middle" fontSize="11" fill="#16233f">every 5 min</text>
      </svg>
    ),
  },
  {
    id: "dust",
    title: ["Dust and shade", "Dust and shade", "Ájá na ndò"],
    short: ["Why panels make less than they should", "Why panels dey make less", "Ihe mere panel ji emepụta obere"],
    body: [
      "Dust (especially in harmattan) and shade from trees, tanks or new buildings block sunlight, so panels make less. SolarDokta knows how much sun fell on your roof, so it can tell when your panels made less than they should have, and why.",
      "Dust (especially for harmattan) and shade from tree, tank or new building dey block sun, so panels go make less. SolarDokta sabi how much sun touch your roof, so e fit know when panel make less than e suppose, and why.",
      "Ájá (karịsịa n'oge ugụrụ) na ndò sitere n'osisi, tank ma ọ bụ ụlọ ọhụrụ na-egbochi anyanwụ, ya mere panel na-emepụta obere. SolarDokta maara ole anyanwụ dakwasịrị n'elu ụlọ gị, ya mere ọ maara mgbe panel mere obere karịa ka o kwesịrị.",
    ],
    yours: (l) => {
      const bad = l.strings.filter((s) => s.status === "dusty" || s.status === "shaded");
      return bad.length ? [
        `Group ${bad.map((s) => s.number).join(" and ")} looks ${bad[0].status}. Have the panels washed with clean water early morning.`,
        `Group ${bad.map((s) => s.number).join(" and ")} get ${bad[0].status === "dusty" ? "dust" : "shade"}. Make dem wash the panels with clean water early morning.`,
        `Otu ${bad.map((s) => s.number).join(" na ")} nwere ${bad[0].status === "dusty" ? "ájá" : "ndò"}. Kwọọ panel ahụ mmiri dị ọcha n'isi ụtụtụ.`,
      ] : ["No dust or shade problem right now.", "No dust or shade wahala now.", "Enweghị nsogbu ájá ma ọ bụ ndò ugbu a."];
    },
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <circle cx="40" cy="36" r="16" fill="#f2b705" />
        <PanelArt x={30} y={84} w={90} h={56} dusty />
        <text x="75" y="155" textAnchor="middle" fontSize="11" fill="#16233f">dust</text>
        <circle cx="210" cy="50" r="30" fill="#2f7d4f" /><rect x="205" y="70" width="10" height="40" fill="#6b4a2e" />
        <PanelArt x={140} y={90} w={90} h={50} />
        <path d="M140 90 h56 l-20 50 h-36Z" fill="#16233f" opacity="0.35" />
        <text x="185" y="155" textAnchor="middle" fontSize="11" fill="#16233f">shade</text>
      </svg>
    ),
  },
  {
    id: "heat",
    title: ["Heat and El Niño", "Heat and El Niño", "Okpomọkụ na El Niño"],
    short: ["Why hot weather costs you battery life", "Why hot weather dey spoil battery", "Ihe mere okpomọkụ ji emebi batrị"],
    body: [
      "Batteries wear out about twice as fast for every 10°C hotter than 25°C. A strong El Niño is keeping Nigeria hotter than usual until early 2027. Keep the battery in a cool, airy room, out of the sun, and never in a sealed store.",
      "Battery dey spoil like two times faster for every 10°C wey hot pass 25°C. Strong El Niño go make Nigeria hot pass normal until early 2027. Keep battery for cool room wey air dey, no put am for sun or closed store.",
      "Batrị na-emebi ihe dị ka ugboro abụọ ngwa ngwa maka 10°C ọ bụla karịrị 25°C. El Niño siri ike na-eme ka Naịjirịa dị ọkụ karịa ka ọ na-adị ruo mmalite 2027. Debe batrị n'ime ụlọ dị jụụ nwere ikuku, ọ bụghị n'anyanwụ.",
    ],
    yours: (l) => l.battery.temp_c !== null ? [
      `Your battery is at ${Math.round(l.battery.temp_c)}°C${l.battery.temp_c > 35 ? ": too hot." : "."}`,
      `Your battery dey ${Math.round(l.battery.temp_c)}°C${l.battery.temp_c > 35 ? ": e too hot." : "."}`,
      `Batrị gị dị na ${Math.round(l.battery.temp_c)}°C${l.battery.temp_c > 35 ? ": ọ dị oke ọkụ." : "."}`,
    ] : null,
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <path d="M70 110 V35 a14 14 0 0 1 28 0 V110 a22 22 0 1 1 -28 0Z" fill="#fff" stroke="#16233f" strokeWidth="2.5" />
        <circle cx="84" cy="126" r="14" fill="#e8590c" /><rect x="79" y="48" width="10" height="70" rx="5" fill="#e8590c" />
        <rect x="150" y="50" width="62" height="90" rx="8" fill="#fff" stroke="#16233f" strokeWidth="2.5" />
        <rect x="157" y="80" width="48" height="53" rx="5" fill="#1e9e6a" />
        <path d="M150 34 q8 -10 0 -20 M170 34 q8 -10 0 -20 M190 34 q8 -10 0 -20" {...stroke} stroke="#e8590c" />
      </svg>
    ),
  },
  {
    id: "soc",
    title: ["SOC: state of charge", "SOC: state of charge", "SOC: ọkwa chaji"],
    short: ["How full the battery is right now", "How full battery dey now", "Otú batrị si jupụta ugbu a"],
    body: [
      "SOC is the “battery %” you see: how full the battery is at this moment. It goes up in the day when the sun charges it and down at night when you use it. Think of it as how much water is in your tank today.",
      "SOC na the “battery %” wey you dey see: how full battery be right now. E dey go up for afternoon when sun dey charge am, and come down for night when you dey use am. Like how much water dey your tank today.",
      "SOC bụ “pasentị batrị” ị na-ahụ: otú batrị si jupụta ugbu a. Ọ na-arị elu n'ehihie mgbe anyanwụ na-achaji ya, na-agbada n'abalị mgbe ị na-eji ya. Dị ka ole mmiri dị n'ime tank gị taa.",
    ],
    yours: (l) => [`Your SOC right now: ${l.battery.percent}% (${l.battery.status}).`, `Your SOC now: ${l.battery.percent}% (${l.battery.status}).`, `SOC gị ugbu a: ${l.battery.percent}%.`],
    Picture: ({ live }) => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <rect x="40" y="20" width="70" height="120" rx="10" fill="#fff" stroke="#16233f" strokeWidth="3" />
        <rect x="47" y={27 + 106 * (1 - live.battery.percent / 100)} width="56" height={106 * (live.battery.percent / 100)} rx="6" fill="#1e9e6a" />
        <text x="75" y="88" textAnchor="middle" fontSize="18" fontWeight="800" fill="#16233f">{live.battery.percent}%</text>
        <path d="M150 30 v100 a10 10 0 0 0 10 10 h50 a10 10 0 0 0 10 -10 v-100" fill="none" stroke="#16233f" strokeWidth="3" />
        <rect x="153" y={30 + 100 * (1 - live.battery.percent / 100)} width="64" height={100 * (live.battery.percent / 100) + 7} fill="#7ea2ff" opacity="0.7" />
        <text x="185" y="155" textAnchor="middle" fontSize="11" fill="#16233f">water in the tank</text>
      </svg>
    ),
  },
  {
    id: "soh",
    title: ["SOH: state of health", "SOH: state of health", "SOH: ahụike batrị"],
    short: ["How big the battery still is, compared with new", "How big battery still be compared to when e new", "Otú batrị si buo ibu ma e jiri ya tụnyere mgbe ọ dị ọhụrụ"],
    body: [
      "Batteries slowly shrink as they age. SOH says how much they can still hold: at 90% SOH, a 10 kWh battery holds about 9 kWh when full. If SOC is the water in the tank, SOH is the size of the tank. SOC changes every day; SOH only goes down, slowly, with use, time and heat. Most warranties cover a battery until about 80% SOH.",
      "Battery dey shrink small small as e dey old. SOH talk how much e fit still hold: for 90% SOH, 10 kWh battery go hold about 9 kWh when e full. If SOC na water inside tank, SOH na the size of the tank. SOC dey change every day; SOH dey only go down slowly with use, time and heat. Most warranty dey cover battery until about 80% SOH.",
      "Batrị na-ebelata nwayọọ ka ọ na-aka nka. SOH na-egosi ole ọ ka nwere ike ijide: na 90% SOH, batrị 10 kWh na-ejide ihe dị ka 9 kWh mgbe o juru. Ọ bụrụ na SOC bụ mmiri dị na tank, SOH bụ nha tank ahụ. Ọtụtụ warranti na-ekpuchi batrị ruo ihe dị ka 80% SOH.",
    ],
    yours: (l) => [
      `Your battery is ${l.battery.size_kwh} kWh new and holds about ${l.battery.full_kwh} kWh usable when full.${l.battery.fading ? " It is losing health faster than normal." : ""}`,
      `Your battery na ${l.battery.size_kwh} kWh when e new, and e fit give about ${l.battery.full_kwh} kWh when e full.`,
      `Batrị gị bụ ${l.battery.size_kwh} kWh mgbe ọ dị ọhụrụ, ọ na-enye ihe dị ka ${l.battery.full_kwh} kWh mgbe o juru.`,
    ],
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <rect x="30" y="20" width="80" height="115" rx="10" fill="#fff" stroke="#16233f" strokeWidth="3" />
        <rect x="37" y="27" width="66" height="101" rx="6" fill="#1e9e6a" />
        <text x="70" y="152" textAnchor="middle" fontSize="11" fill="#16233f">new: 100%</text>
        <rect x="150" y="38" width="80" height="97" rx="10" fill="#fff" stroke="#16233f" strokeWidth="3" />
        <rect x="157" y="45" width="66" height="83" rx="6" fill="#c9a400" />
        <path d="M150 20 h80" stroke="#c93636" strokeWidth="2" strokeDasharray="5 4" />
        <text x="190" y="152" textAnchor="middle" fontSize="11" fill="#16233f">older: 85%</text>
      </svg>
    ),
    Try: ({ lang }) => {
      const [soh, setSoh] = useState(90);
      const [soc, setSoc] = useState(80);
      const usable = Math.max(0, (10 * soh) / 100 * ((soc - 10) / 100) * 0.96);
      return (
        <div className="space-y-3 text-sm">
          <label className="block">SOH ({["tank size", "tank size", "nha tank"][I[lang]]}): <strong>{soh}%</strong>
            <input type="range" min={60} max={100} value={soh} onChange={(e) => setSoh(Number(e.target.value))} className="mt-1 w-full accent-[#c9a400]" />
          </label>
          <label className="block">SOC ({["how full", "how full", "otú o si jupụta"][I[lang]]}): <strong>{soc}%</strong>
            <input type="range" min={10} max={100} value={soc} onChange={(e) => setSoc(Number(e.target.value))} className="mt-1 w-full accent-[#1e9e6a]" />
          </label>
          <p className="rounded-2xl bg-sky px-3 py-2">{[
            `A 10 kWh battery at ${soh}% SOH and ${soc}% SOC can give you about ${usable.toFixed(1)} kWh right now. That's about ${(usable / 0.4).toFixed(0)} hours for a typical evening (400 W).`,
            `10 kWh battery for ${soh}% SOH and ${soc}% SOC fit give about ${usable.toFixed(1)} kWh now. Na about ${(usable / 0.4).toFixed(0)} hours for normal evening (400 W).`,
            `Batrị 10 kWh na ${soh}% SOH na ${soc}% SOC nwere ike inye ihe dị ka ${usable.toFixed(1)} kWh ugbu a: ihe dị ka awa ${(usable / 0.4).toFixed(0)} maka mgbede (400 W).`,
          ][I[lang]]}</p>
        </div>
      );
    },
  },
  {
    id: "cycles",
    title: ["Cycles and depth of discharge", "Cycles and depth of discharge", "Okirikiri na omimi ojiji"],
    short: ["How batteries wear out with use", "How battery dey wear with use", "Otú batrị si emebi site n'iji ya"],
    body: [
      "One cycle is emptying and refilling the battery's worth of energy once (two half-empties also make one cycle). Lithium (LiFePO4) batteries are rated for about 6,000 cycles before reaching 80% SOH; lead-acid for a few hundred. Depth of discharge is how far you empty it each day: emptying it very deep every night wears it faster, especially lead-acid.",
      "One cycle na when you use the battery full energy once (two half also make one cycle). Lithium (LiFePO4) fit do about 6,000 cycles before e reach 80% SOH; lead-acid na few hundred. Depth of discharge na how far you dey empty am every day: if you dey empty am too deep every night, e go wear quick, especially lead-acid.",
      "Otu okirikiri bụ iji ike batrị dum otu ugboro (ọkara abụọ na-emekwa otu). Batrị lithium (LiFePO4) nwere ike ime ihe dị ka okirikiri 6,000 tupu ọ ruo 80% SOH; lead-acid bụ narị ole na ole. Omimi ojiji bụ otú ị si emesị ya kwa ụbọchị: imesị ya nke ukwuu kwa abalị na-eme ka o mebie ngwa ngwa.",
    ],
    yours: (l) => [
      `Today your battery has gone between charging and ${l.battery.status}; it is at ${l.battery.percent}% now.`,
      `Your battery dey ${l.battery.percent}% now.`,
      `Batrị gị dị na ${l.battery.percent}% ugbu a.`,
    ],
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <path d="M20 40 C60 40 60 120 100 120 S140 40 180 40 S220 120 245 120" {...stroke} stroke="#1e9e6a" strokeWidth="4" />
        <path d="M20 30 H245" stroke="#9aa3b2" strokeDasharray="4 4" /><text x="22" y="24" fontSize="10" fill="#5e6b80">full</text>
        <path d="M20 130 H245" stroke="#9aa3b2" strokeDasharray="4 4" /><text x="22" y="145" fontSize="10" fill="#5e6b80">empty</text>
        <path d="M100 40 V120" stroke="#c93636" strokeWidth="2" /><text x="106" y="84" fontSize="11" fill="#c93636">depth</text>
      </svg>
    ),
  },
  {
    id: "mode",
    title: ["Inverter mode (SBU or SUB)", "Inverter mode (SBU or SUB)", "Ọnọdụ inverter (SBU ma ọ bụ SUB)"],
    short: ["Which power the inverter uses first", "Which power inverter dey use first", "Ọkụ inverter na-eji mbụ"],
    body: [
      "Inverters follow an order. SBU = Solar, then Battery, then Utility (NEPA): saves NEPA bills, uses the battery more. SUB = Solar, then Utility, then Battery: keeps the battery full for blackouts, uses more NEPA. With very poor NEPA like now, SBU usually makes more sense; your installer can change it.",
      "Inverter dey follow order. SBU = Solar, then Battery, then NEPA: e dey save NEPA money, but e dey use battery more. SUB = Solar, then NEPA, then Battery: e dey keep battery full for when light go, but e dey use NEPA more. As light bad like this, SBU dey make sense pass; your installer fit change am.",
      "Inverter na-eso usoro. SBU = Anyanwụ, Batrị, NEPA: ọ na-echekwa ego NEPA mana ọ na-eji batrị karịa. SUB = Anyanwụ, NEPA, Batrị: ọ na-edebe batrị juru maka mgbe ọkụ pụrụ. Ugbu a NEPA adịghị mma, SBU ka mma; onye rụnyere ya nwere ike ịgbanwe ya.",
    ],
    yours: (l) => [`Your inverter is set to ${l.inverter.mode}.`, `Your inverter dey on ${l.inverter.mode}.`, `Inverter gị dị na ${l.inverter.mode}.`],
    Picture: ({ live }) => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        {(live.inverter.mode === "SBU" ? ["Solar", "Battery", "NEPA"] : ["Solar", "NEPA", "Battery"]).map((n, i) => (
          <g key={n}>
            <rect x={20 + i * 82} y="55" width="66" height="50" rx="10" fill={["#f2b705", n === "Battery" ? "#1e9e6a" : "#4c6ef5", n === "Battery" ? "#1e9e6a" : "#4c6ef5"][i]} />
            <text x={53 + i * 82} y="85" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff">{i + 1}. {n}</text>
            {i < 2 && <path d={`M${88 + i * 82} 80 h10`} {...stroke} strokeWidth="3" />}
          </g>
        ))}
        <text x="130" y="135" textAnchor="middle" fontSize="12" fill="#16233f">{live.inverter.mode}: used in this order</text>
      </svg>
    ),
  },
  {
    id: "kwp",
    title: ["kWp: panel size", "kWp: panel size", "kWp: nha panel"],
    short: ["How much your panels can make in full sun", "How much your panels fit make for full sun", "Ole panel gị nwere ike imepụta n'anyanwụ zuru oke"],
    body: [
      "kWp (kilowatt-peak) is the size of a solar system: what the panels make in strong, ideal sunshine. In Lagos, each 1 kWp makes roughly 3.5 to 4.5 kWh on a sunny day, less in rain or harmattan haze. Real output at midday is usually 75–90% of kWp because of heat and dust.",
      "kWp na the size of solar: wetin panels go make for strong correct sun. For Lagos, each 1 kWp fit make about 3.5 to 4.5 kWh for sunny day, less for rain or harmattan. For afternoon, e dey usually give 75–90% of kWp because of heat and dust.",
      "kWp bụ nha usoro anyanwụ: ihe panel na-emepụta n'anyanwụ siri ike. N'Eko, 1 kWp ọ bụla na-emepụta ihe dị ka 3.5 ruo 4.5 kWh n'ụbọchị anyanwụ, obere n'oge mmiri ozuzo ma ọ bụ ugụrụ.",
    ],
    yours: (l) => {
      const kwp = l.strings.reduce((a, s) => a + s.kwp, 0);
      return [`Your panels add up to ${kwp.toFixed(1)} kWp (${l.strings.map((s) => s.panels).reduce((a, b) => a + b, 0)} panels).`,
              `Your panels total ${kwp.toFixed(1)} kWp.`, `Panel gị niile bụ ${kwp.toFixed(1)} kWp.`];
    },
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        {[0, 1, 2, 3].map((i) => <PanelArt key={i} x={18 + (i % 2) * 64} y={30 + Math.floor(i / 2) * 50} w={58} h={42} />)}
        <text x="78" y="148" textAnchor="middle" fontSize="11" fill="#16233f">4 × 550 W = 2.2 kWp</text>
        <circle cx="200" cy="60" r="22" fill="#f2b705" />
        <text x="200" y="118" textAnchor="middle" fontSize="13" fontWeight="700" fill="#16233f">≈ 8–10 kWh</text>
        <text x="200" y="134" textAnchor="middle" fontSize="11" fill="#5e6b80">on a sunny day</text>
      </svg>
    ),
  },
  {
    id: "heldback",
    title: ["Battery full: “held back” power", "Battery full: power wey dey waste", "Batrị juru: ọkụ a na-ejideghị"],
    short: ["Free power you can use when the battery is full", "Free power wey you fit use when battery full", "Ọkụ efu ị nwere ike iji mgbe batrị juru"],
    body: [
      "When the battery is full and the house uses little, the inverter tells the panels to slow down: that sunshine is wasted. This is the best time to run the iron, pumping machine or washing machine, because the power is effectively free and won't touch the battery.",
      "When battery don full and house no dey use much, inverter go tell panels make dem slow down: that sun dey waste. Na the best time to iron, pump water or wash, because the power free and e no go touch battery.",
      "Mgbe batrị juru ma ụlọ anaghị eji ọtụtụ ọkụ, inverter na-agwa panel ka ha belata: anyanwụ ahụ na-ala n'efu. Ọ bụ oge kacha mma ịgba ígwè, ịkpọ mmiri ma ọ bụ ịsa ákwà.",
    ],
    yours: (l) => l.held_back_w > 300
      ? [`Right now your panels are holding back about ${kw(l.held_back_w)}: use it!`, `Now your panels dey hold back about ${kw(l.held_back_w)}: use am!`, `Ugbu a panel gị na-ejide ihe dị ka ${kw(l.held_back_w)}: jiri ya!`]
      : ["No power is being held back right now.", "No power dey waste now.", "Ọ dịghị ọkụ a na-ala n'efu ugbu a."],
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <circle cx="40" cy="36" r="18" fill="#f2b705" />
        <PanelArt x={20} y={70} w={80} h={52} />
        <rect x="150" y="40" width="56" height="90" rx="8" fill="#fff" stroke="#16233f" strokeWidth="3" />
        <rect x="156" y="46" width="44" height="78" rx="5" fill="#1e9e6a" />
        <text x="178" y="92" textAnchor="middle" fontSize="13" fontWeight="800" fill="#fff">100%</text>
        <path d="M105 96 H145" {...stroke} stroke="#9aa3b2" strokeDasharray="5 4" strokeWidth="3" />
        <text x="125" y="86" textAnchor="middle" fontSize="10" fill="#5e6b80">wasted</text>
      </svg>
    ),
  },
  {
    id: "overload",
    title: ["Overload (the inverter “trips”)", "Overload (inverter dey trip)", "Ibu karịrị akarị (inverter na-agbanyụ)"],
    short: ["Too much switched on at once", "Too many things on at once", "Ọtụtụ ihe gbanyere otu oge"],
    body: [
      "Every inverter has a limit in kW. If the things switched on add up to more than that (an AC, iron and pump together, say), it switches off to protect itself and the house goes dark for a moment. Spread heavy appliances out instead of running them together.",
      "Every inverter get limit for kW. If the things wey you on pass am (like AC, iron and pump together), e go off to protect itself and light go off small. Spread heavy appliances, no on dem together.",
      "Inverter ọ bụla nwere oke kW. Ọ bụrụ na ihe niile gbanyere karịrị ya (dị ka AC, ígwè na pump ọnụ), ọ na-agbanyụ onwe ya. Kewaa ngwa ndị buru ibu, ejikọla ha ọnụ.",
    ],
    yours: (l) => [`Your inverter limit is ${l.inverter.kw} kW; it is at ${l.inverter.load_percent}% now.`,
                   `Your inverter limit na ${l.inverter.kw} kW; e dey ${l.inverter.load_percent}% now.`,
                   `Oke inverter gị bụ ${l.inverter.kw} kW; ọ dị na ${l.inverter.load_percent}% ugbu a.`],
    Picture: () => (
      <svg viewBox="0 0 260 160" className="h-full w-full">
        <path d="M30 130 A100 100 0 0 1 230 130" {...stroke} strokeWidth="10" stroke="#e3e8ee" />
        <path d="M30 130 A100 100 0 0 1 180 55" {...stroke} strokeWidth="10" stroke="#1e9e6a" />
        <path d="M180 55 A100 100 0 0 1 230 130" {...stroke} strokeWidth="10" stroke="#c93636" />
        <path d="M130 130 L196 70" {...stroke} strokeWidth="4" />
        <text x="205" y="150" textAnchor="middle" fontSize="11" fill="#c93636">trips here</text>
      </svg>
    ),
  },
];

type Quiz = { q: L3; options: L3[]; answer: number; why: L3 };
const EXTRAS: Record<string, { remember: L3; quiz: Quiz }> = {
  panel: { remember: ["More sun = more power. Nothing at night.", "Sun plenty = power plenty. Nothing for night.", "Anyanwụ ka ukwuu = ọkụ ka ukwuu. Ọ dịghị ihe n'abalị."],
    quiz: { q: ["When do panels make the most power?", "When panels dey make power pass?", "Olee mgbe panel na-emepụta ọkụ kacha?"],
      options: [["Early morning", "Early morning", "Isi ụtụtụ"], ["Around midday", "Around afternoon", "N'ehihie"], ["At night", "For night", "N'abalị"]], answer: 1,
      why: ["The sun is highest and strongest around midday.", "Sun dey strong pass for afternoon.", "Anyanwụ kachasị ike n'ehihie."] } },
  group: { remember: ["One dead group = less power, but the lights stay on. That's why it's easy to miss.", "One group die = power reduce, but light still dey. Na why e easy to miss.", "Otu otu nwụrụ = ọkụ belata, mana ọkụ ka na-enwu."],
    quiz: { q: ["Panel group 2 stops working. What happens?", "Panel group 2 stop work. Wetin go happen?", "Otu panel 2 akwụsị. Gịnị na-eme?"],
      options: [["Everything goes off", "Everything go off", "Ihe niile na-anyụ"], ["Less power, lights still on", "Power go reduce, light still dey", "Ọkụ ebelata, ọkụ ka na-enwu"], ["Nothing changes", "Nothing go change", "Ọ dịghị ihe gbanwere"]], answer: 1,
      why: ["The other group keeps working, so you only lose part of your solar.", "The other group still dey work, so na part of your solar you lose.", "Otu nke ọzọ ka na-arụ ọrụ."] } },
  inverter: { remember: ["The inverter decides where your power comes from and protects the system.", "Inverter dey decide where power go come from and e dey protect system.", "Inverter na-ekpebi ebe ọkụ si abịa ma na-echebe usoro."],
    quiz: { q: ["What does the inverter do?", "Wetin inverter dey do?", "Gịnị ka inverter na-eme?"],
      options: [["Stores power", "E dey store power", "Na-echekwa ọkụ"], ["Chooses and converts power for your sockets", "E dey choose and change power for socket", "Na-ahọrọ ma gbanwee ọkụ maka soket"], ["Makes power from sun", "E dey make power from sun", "Na-emepụta ọkụ site n'anyanwụ"]], answer: 1,
      why: ["The battery stores, the panels make, the inverter manages and converts.", "Battery dey store, panel dey make, inverter dey manage.", "Batrị na-echekwa, panel na-emepụta, inverter na-achịkwa."] } },
  battery: { remember: ["About 20% (10% for lithium) is the floor: below that the inverter stops using it.", "About 20% na the floor: below am inverter go stop to use am.", "Ihe dị ka 20% bụ ala: n'okpuru ya inverter na-akwụsị iji ya."],
    quiz: { q: ["Your battery shows 22% at 2 am. What's the best move?", "Battery dey 22% for 2am. Wetin you go do?", "Batrị dị na 22% n'elekere abụọ abalị. Gịnị ka ị ga-eme?"],
      options: [["Switch on the AC", "On AC", "Gbanye AC"], ["Switch off heavy loads until morning", "Off heavy things till morning", "Gbanyụọ ngwa ndị buru ibu ruo ụtụtụ"], ["Nothing, it's full", "Nothing, e full", "Ọ dịghị, o juru"]], answer: 1,
      why: ["It is close to the cut-off: save it until the sun returns.", "E near cut-off: save am till sun come.", "Ọ dị nso n'oke: chekwaa ya ruo mgbe anyanwụ lọghachiri."] } },
  soc: { remember: ["SOC = how full now. It goes up and down every day.", "SOC = how full now. E dey go up and down every day.", "SOC = otú o si jupụta ugbu a."],
    quiz: { q: ["Which number changes every day?", "Which number dey change every day?", "Ọnụọgụ olee na-agbanwe kwa ụbọchị?"],
      options: [["SOC", "SOC", "SOC"], ["SOH", "SOH", "SOH"], ["kWp", "kWp", "kWp"]], answer: 0,
      why: ["SOC rises with charging and falls with use. SOH and kWp barely change.", "SOC dey go up and down. SOH and kWp no dey change much.", "SOC na-arị elu ma na-agbada."] } },
  soh: { remember: ["SOH = size of the tank. Only goes down, slowly. 80% is the usual warranty line.", "SOH = size of tank. E dey only go down slowly. 80% na warranty line.", "SOH = nha tank. Ọ na-agbada nwayọọ. 80% bụ oke warranti."],
    quiz: { q: ["A 10 kWh battery has 85% SOH. About how much can it hold when full?", "10 kWh battery get 85% SOH. How much e fit hold when e full?", "Batrị 10 kWh nwere 85% SOH. Ole ka ọ na-ejide mgbe o juru?"],
      options: [["10 kWh", "10 kWh", "10 kWh"], ["8.5 kWh", "8.5 kWh", "8.5 kWh"], ["5 kWh", "5 kWh", "5 kWh"]], answer: 1,
      why: ["85% of 10 kWh is 8.5 kWh.", "85% of 10 kWh na 8.5 kWh.", "85% nke 10 kWh bụ 8.5 kWh."] } },
  cycles: { remember: ["Shallow daily use lasts longer than emptying it every night.", "Small daily use dey last pass emptying am every night.", "Iji ya nwayọọ kwa ụbọchị na-adịte aka karịa imesị ya kwa abalị."],
    quiz: { q: ["Which wears a battery faster?", "Which one dey wear battery quick?", "Olee na-emebi batrị ngwa ngwa?"],
      options: [["Using 30% each day", "Use 30% every day", "Iji 30% kwa ụbọchị"], ["Emptying it to the bottom every night", "Empty am finish every night", "Imesị ya kwa abalị"]], answer: 1,
      why: ["Deep discharges stress the battery, especially lead-acid.", "Deep discharge dey stress battery, especially lead-acid.", "Imesị ya nke ukwuu na-emebi ya."] } },
  mode: { remember: ["SBU uses the battery first (saves NEPA); SUB keeps it for blackouts.", "SBU dey use battery first; SUB dey keep am for when light go.", "SBU na-eji batrị mbụ; SUB na-edebe ya maka mgbe ọkụ pụrụ."],
    quiz: { q: ["Which mode keeps the battery full for blackouts?", "Which mode dey keep battery full for when light go?", "Ọnọdụ olee na-edebe batrị juru?"],
      options: [["SBU", "SBU", "SBU"], ["SUB", "SUB", "SUB"]], answer: 1,
      why: ["SUB uses NEPA before the battery, so the battery stays full.", "SUB dey use NEPA before battery.", "SUB na-eji NEPA tupu batrị."] } },
  kwp: { remember: ["1 kWp ≈ 4 kWh on a sunny Lagos day.", "1 kWp ≈ 4 kWh for sunny day for Lagos.", "1 kWp ≈ 4 kWh n'ụbọchị anyanwụ n'Eko."],
    quiz: { q: ["About how much does a 3 kWp system make on a sunny day in Lagos?", "How much 3 kWp go make for sunny day for Lagos?", "Ole ka usoro 3 kWp na-emepụta n'ụbọchị anyanwụ?"],
      options: [["About 3 kWh", "About 3 kWh", "Ihe dị ka 3 kWh"], ["About 12 kWh", "About 12 kWh", "Ihe dị ka 12 kWh"], ["About 50 kWh", "About 50 kWh", "Ihe dị ka 50 kWh"]], answer: 1,
      why: ["3 kWp × about 4 hours of strong sun ≈ 12 kWh.", "3 kWp × about 4 hours strong sun ≈ 12 kWh.", "3 kWp × ihe dị ka awa 4 ≈ 12 kWh."] } },
  watts: { remember: ["Watts = how hard right now. kWh = how much in total.", "Watts = how hard now. kWh = how much total.", "Watts = ugbu a. kWh = ngụkọta."],
    quiz: { q: ["A 1,000 W iron used for 30 minutes uses…", "1,000 W iron for 30 minutes go use…", "Ígwè 1,000 W maka nkeji 30 na-eri…"],
      options: [["0.5 kWh", "0.5 kWh", "0.5 kWh"], ["1,000 kWh", "1,000 kWh", "1,000 kWh"], ["30 kWh", "30 kWh", "30 kWh"]], answer: 0,
      why: ["1,000 W × 0.5 h = 500 Wh = 0.5 kWh.", "1,000 W × 0.5 h = 0.5 kWh.", "1,000 W × 0.5 h = 0.5 kWh."] } },
  heldback: { remember: ["Battery full at midday? Run heavy things now: it's free.", "Battery full for afternoon? Use heavy things now: e free.", "Batrị juru n'ehihie? Jiri ngwa buru ibu ugbu a."],
    quiz: { q: ["Best time to pump water?", "Best time to pump water?", "Oge kacha mma ịkpọ mmiri?"],
      options: [["Midday with a full battery", "Afternoon when battery full", "N'ehihie mgbe batrị juru"], ["10 pm", "10pm", "Elekere iri abalị"], ["5 am", "5am", "Elekere ise ụtụtụ"]], answer: 0,
      why: ["The panels can cover it without touching the battery.", "Panels go carry am without touching battery.", "Panel nwere ike ibu ya."] } },
  overload: { remember: ["Don't run the AC, iron and pump together.", "No on AC, iron and pump together.", "Ejikọla AC, ígwè na pump ọnụ."],
    quiz: { q: ["A 5 kW inverter. Iron (1 kW) + AC (1.5 kW) + pump (0.75 kW). Will it trip?", "5 kW inverter. Iron + AC + pump. E go trip?", "Inverter 5 kW. Ígwè + AC + pump. Ọ ga-agbanyụ?"],
      options: [["Yes", "Yes", "Ee"], ["No, 3.25 kW is under 5 kW", "No, 3.25 kW never reach 5 kW", "Mba, 3.25 kW erughị 5 kW"]], answer: 1,
      why: ["Add them: 3.25 kW, under the 5 kW limit (if nothing else big is on).", "Add dem: 3.25 kW, e no reach 5 kW.", "Gbakọọ: 3.25 kW, erughị 5 kW."] } },
  nepa: { remember: ["When NEPA is on, use it for heavy jobs and let the battery charge.", "When NEPA dey, use am for heavy work make battery charge.", "Mgbe NEPA nọ, jiri ya rụọ ọrụ buru ibu."],
    quiz: { q: ["NEPA just came on at 7 pm. Good time to iron?", "NEPA just come for 7pm. Good time to iron?", "NEPA bịara n'elekere asaa. Oge dị mma ịgba ígwè?"],
      options: [["Yes, NEPA can carry it", "Yes, NEPA fit carry am", "Ee, NEPA nwere ike ibu ya"], ["No, never at night", "No, never for night", "Mba"]], answer: 0,
      why: ["While NEPA is on, heavy loads don't drain your battery.", "As NEPA dey, heavy load no go drain battery.", "Mgbe NEPA nọ, ngwa buru ibu anaghị emesị batrị."] } },
  link: { remember: ["If the Link stops sending, SolarDokta can't see problems: check Wi-Fi or the SIM.", "If Link stop to send, SolarDokta no fit see problem: check Wi-Fi or SIM.", "Ọ bụrụ na Link kwụsị, lelee Wi-Fi ma ọ bụ SIM."],
    quiz: { q: ["How often does the Link send readings?", "How often Link dey send readings?", "Ugboro ole ka Link na-ezite ozi?"],
      options: [["Every 5 minutes", "Every 5 minutes", "Kwa nkeji 5"], ["Once a day", "Once a day", "Otu ugboro kwa ụbọchị"], ["Once a month", "Once a month", "Otu ugboro kwa ọnwa"]], answer: 0,
      why: ["Every 5 minutes, so problems are caught the same day.", "Every 5 minutes, so we go catch problem same day.", "Kwa nkeji 5, ka a hụ nsogbu n'otu ụbọchị."] } },
  dust: { remember: ["Wash panels with clean water early morning, never in hot midday sun.", "Wash panels with clean water early morning, no wash am for hot afternoon.", "Kwọọ panel n'isi ụtụtụ, ọ bụghị n'ehihie na-ekpo ọkụ."],
    quiz: { q: ["When is the safest time to wash panels?", "When be the best time to wash panels?", "Olee oge kacha mma ịkwọ panel?"],
      options: [["Early morning", "Early morning", "Isi ụtụtụ"], ["Hot midday", "Hot afternoon", "Ehihie na-ekpo ọkụ"]], answer: 0,
      why: ["Cold water on hot glass can crack it; morning is cool and safe.", "Cold water for hot glass fit crack am.", "Mmiri oyi na iko na-ekpo ọkụ nwere ike ịgbawa ya."] } },
  heat: { remember: ["Every 10°C hotter ≈ twice the wear. Keep the battery cool and airy.", "Every 10°C hot pass ≈ double wear. Keep battery cool.", "10°C ọ bụla karịa ≈ mmebi okpukpu abụọ."],
    quiz: { q: ["Where is the best place for a battery?", "Where be the best place for battery?", "Ebee kacha mma maka batrị?"],
      options: [["A sealed store in the sun", "Closed store for sun", "Ụlọ mechiri emechi n'anyanwụ"], ["A cool, airy room out of the sun", "Cool room wey air dey", "Ụlọ dị jụụ nwere ikuku"]], answer: 1,
      why: ["Cooler batteries age much more slowly.", "Cool battery dey last pass.", "Batrị dị jụụ na-adịte aka."] } },
};

const GROUPS: { name: L3; ids: string[] }[] = [
  { name: ["The basics", "The basics", "Ihe ndabere"], ids: ["panel", "group", "kwp", "inverter", "mode", "nepa"] },
  { name: ["Your battery", "Your battery", "Batrị gị"], ids: ["battery", "soc", "soh", "cycles", "heat"] },
  { name: ["Using power well", "Use power well", "Iji ọkụ nke ọma"], ids: ["watts", "heldback", "overload"] },
  { name: ["Problems and monitoring", "Problems and monitoring", "Nsogbu na nlekota"], ids: ["dust", "link"] },
];
const ORDER = GROUPS.flatMap((g) => g.ids);

function QuickCheck({ quiz, lang }: { quiz: Quiz; lang: Lang }) {
  const [pick, setPick] = useState<number | null>(null);
  const i = I[lang];
  return (
    <div className="rounded-2xl bg-[#fff6e0] p-4">
      <p className="text-sm font-semibold">{["Quick check", "Quick check", "Nyocha ngwa ngwa"][i]}</p>
      <p className="mt-1 font-medium">{quiz.q[i]}</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {quiz.options.map((o, k) => {
          const chosen = pick === k, right = k === quiz.answer;
          return (
            <button key={o[0]} onClick={() => setPick(k)} disabled={pick !== null}
                    className={`rounded-xl border px-3 py-2 text-left text-sm ${pick === null ? "border-line bg-white hover:border-ink" : right ? "border-charge bg-[#ecf8f2] font-semibold" : chosen ? "border-alarm bg-[#fdeeee]" : "border-line bg-white opacity-60"}`}>
              {o[i]}
            </button>
          );
        })}
      </div>
      {pick !== null && (
        <p className="mt-3 text-sm"><strong>{pick === quiz.answer ? ["Correct!", "Correct!", "Ọ dị mma!"][i] : ["Not quite.", "No be am.", "Ọ bụghị ya."][i]}</strong> {quiz.why[i]}</p>
      )}
    </div>
  );
}

export function Learn({ live, start }: { live: Live; start?: string }) {
  const { t, lang } = useLang();
  const byId = Object.fromEntries(TERMS.map((x) => [x.id, x]));
  const [id, setId] = useState(start && byId[start] ? start : "panel");
  const [seen, setSeen] = useState<Set<string>>(() => new Set([start && byId[start] ? start : "panel"]));
  const term = byId[id];
  const i = I[lang];
  const yours = term.yours(live);
  const Try = term.Try;
  const extra = EXTRAS[id];
  const pos = ORDER.indexOf(id);
  const go = (next: string) => { setId(next); setSeen((s) => new Set(s).add(next)); window.scrollTo({ top: 0, behavior: "smooth" }); };

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="font-display text-3xl font-semibold">{t("learn.title")}</h2>
          <p className="mt-1 max-w-2xl text-muted">{t("learn.intro")}</p>
        </div>
        <div className="w-56">
          <p className="text-sm text-muted">{[`You've explored ${seen.size} of ${ORDER.length}`, `You don see ${seen.size} of ${ORDER.length}`, `Ị hụla ${seen.size} n'ime ${ORDER.length}`][i]}</p>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-white"><div className="h-full rounded-full bg-sun transition-all" style={{ width: `${(100 * seen.size) / ORDER.length}%` }} /></div>
        </div>
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-[260px_1fr] lg:items-start">
        <nav aria-label="Words" className="space-y-4 lg:sticky lg:top-20">
          {GROUPS.map((g) => (
            <div key={g.name[0]}>
              <p className="mb-1.5 px-1 text-xs font-semibold text-muted">{g.name[i]}</p>
              <ul className="flex flex-wrap gap-1.5 lg:flex-col lg:gap-1">
                {g.ids.map((x) => (
                  <li key={x}>
                    <button onClick={() => go(x)} aria-pressed={id === x}
                            className={`flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left text-sm font-medium ${id === x ? "bg-ink text-sky" : "bg-white hover:bg-[#f7f9fb]"}`}>
                      <span>{byId[x].title[i]}</span>
                      {seen.has(x) && id !== x && <span className="text-charge" aria-label="seen">✓</span>}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <article key={term.id} className="msg-in space-y-5 rounded-3xl bg-white p-5 sm:p-7">
          <div className="grid gap-6 md:grid-cols-[1fr_1.1fr] md:items-center">
            <div className="aspect-[13/8] rounded-2xl bg-[#f4f7fa] p-3"><term.Picture live={live} /></div>
            <div>
              <h3 className="font-display text-2xl font-semibold">{term.title[i]}</h3>
              <p className="mt-1 font-medium text-[#9a7400]">{term.short[i]}</p>
              <p className="mt-3 leading-relaxed">{term.body[i]}</p>
            </div>
          </div>
          {extra && (
            <div className="flex gap-3 rounded-2xl bg-ink px-4 py-3 text-sky">
              <span className="font-display text-lg text-sun" aria-hidden="true">★</span>
              <p><span className="font-semibold">{["Remember: ", "Remember: ", "Cheta: "][i]}</span>{extra.remember[i]}</p>
            </div>
          )}
          {yours && (
            <div className="rounded-2xl border-l-4 border-charge bg-[#ecf8f2] px-4 py-3">
              <p className="text-xs font-semibold text-charge">{t("learn.yours")}</p>
              <p className="font-medium">{yours[i]}</p>
            </div>
          )}
          {Try && (
            <div className="rounded-2xl border border-line p-4">
              <p className="mb-3 text-sm font-semibold">{t("learn.try")}</p>
              <Try lang={lang} />
            </div>
          )}
          {extra && <QuickCheck key={`${id}-${lang}`} quiz={extra.quiz} lang={lang} />}
          <div className="flex justify-between gap-3 border-t border-line pt-4">
            {pos > 0 ? <button onClick={() => go(ORDER[pos - 1])} className="rounded-full border border-line px-4 py-2 text-sm font-medium hover:border-ink">← {byId[ORDER[pos - 1]].title[i]}</button> : <span />}
            {pos < ORDER.length - 1 && <button onClick={() => go(ORDER[pos + 1])} className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-sky">{byId[ORDER[pos + 1]].title[i]} →</button>}
          </div>
        </article>
      </div>
    </div>
  );
}

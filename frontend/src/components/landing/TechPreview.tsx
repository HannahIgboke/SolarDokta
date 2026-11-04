// A still picture of the technician's screen: sites on a map, worst first, and a what-if test.
const SITES = [
  { x: 90, y: 150, c: "#c93636", name: "Lekki home", why: "Panel group 2 stopped", tag: "Go today" },
  { x: 170, y: 120, c: "#c46a00", name: "Ikeja shop", why: "Battery ran out 9 nights in a row", tag: "Bigger battery?" },
  { x: 250, y: 168, c: "#c46a00", name: "Yaba clinic", why: "Battery room at 39°C", tag: "Add a vent" },
  { x: 330, y: 132, c: "#1e9e6a", name: "Port Harcourt office", why: "All good", tag: "" },
];

export function TechPreview() {
  return (
    <div className="overflow-hidden rounded-[28px] border border-line bg-white">
      <div className="relative bg-[#dfe7ee]">
        <svg viewBox="0 0 420 230" className="block h-auto w-full" aria-hidden="true">
          <path d="M0 175 C80 160 140 190 210 178 S330 150 420 165 V230 H0Z" fill="#b9d3e6" />
          <path d="M0 175 C80 160 140 190 210 178 S330 150 420 165" fill="none" stroke="#9cbcd4" strokeWidth="2" />
          {[40, 120, 200, 280, 360].map((x) => <path key={x} d={`M${x} 0 V170`} stroke="#d0dae3" />)}
          {[40, 90, 140].map((y) => <path key={y} d={`M0 ${y} H420`} stroke="#d0dae3" />)}
          {SITES.map((s) => (
            <g key={s.name}>
              {s.c !== "#1e9e6a" && <circle cx={s.x} cy={s.y} r="16" fill={s.c} opacity="0.18" />}
              <circle cx={s.x} cy={s.y} r="8" fill={s.c} stroke="#fff" strokeWidth="2.5" />
            </g>
          ))}
        </svg>
        <p className="absolute top-3 left-3 rounded-full bg-white px-3 py-1 text-xs font-semibold">4 sites, 3 need attention</p>
      </div>
      <ul className="divide-y divide-line">
        {SITES.map((s) => (
          <li key={s.name} className="flex items-center gap-3 px-4 py-3 text-sm">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: s.c }} />
            <span className="min-w-0 flex-1"><strong className="font-semibold">{s.name}</strong><span className="block text-muted">{s.why}</span></span>
            {s.tag && <span className="shrink-0 rounded-full bg-sky px-2.5 py-1 text-xs font-medium">{s.tag}</span>}
          </li>
        ))}
      </ul>
      <div className="border-t border-line bg-[#fff6e0] px-4 py-3 text-sm">
        <strong>What if</strong> NEPA drops to 2 hours and it hits 38°C? Ikeja shop runs out of power 5 nights out of 7.
      </div>
    </div>
  );
}

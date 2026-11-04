// What you see after tapping a part of the live picture.
import type { Live } from "@/lib/types";
import { kw } from "@/lib/useApi";
import type { Part } from "../twin/Twin";

const STRING_STATUS: Record<string, string> = {
  ok: "Working normally.",
  dead: "Producing nothing. Call your installer; don't climb up or touch the wiring.",
  weak: "Giving much less than it should, from the start. The panels may be substandard or wrongly rated.",
  shaded: "Something shades these panels for part of the day.",
  dusty: "Dust is cutting the power. Wash the panels with clean water, early morning or evening.",
};

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line py-1.5 last:border-0">
      <dt className="text-muted">{k}</dt>
      <dd className="text-right font-medium">{v}</dd>
    </div>
  );
}

export function PartDetails({ part, live }: { part: Part; live: Live }) {
  if (part.startsWith("string")) {
    const s = live.strings[Number(part.split("-")[1]) - 1];
    if (!s) return null;
    return (
      <div>
        <h3 className="font-display font-semibold">Panel group {s.number}</h3>
        <p className="mt-1 text-sm">{STRING_STATUS[s.status]}</p>
        <dl className="mt-3 text-sm">
          <Row k="Making now" v={kw(s.now_w)} />
          {s.could_make_w !== null && <Row k="Could make in this sunlight" v={kw(s.could_make_w)} />}
          <Row k="Size" v={`${s.kwp} kWp, about ${s.panels} panels`} />
        </dl>
        {s.could_make_w !== null && s.could_make_w - s.now_w > 300 && live.battery.percent >= 97 && (
          <p className="mt-2 text-sm text-muted">
            The gap isn&apos;t a fault: the battery is full, so the inverter only takes what the house uses.
          </p>
        )}
      </div>
    );
  }
  if (part === "battery") {
    const b = live.battery;
    return (
      <div>
        <h3 className="font-display font-semibold">Battery</h3>
        <dl className="mt-3 text-sm">
          <Row k="Charge" v={`${b.percent}% (${b.energy_left_kwh} kWh usable left)`} />
          <Row k="Right now" v={b.status === "resting" ? "Resting" : `${b.status === "charging" ? "Charging" : "Powering the house"} at ${kw(Math.abs(b.power_w))}`} />
          <Row k="A full battery gives" v={`${b.full_kwh} kWh`} />
          {b.temp_c !== null && <Row k="Temperature" v={<span className={b.hot ? "text-warn" : ""}>{b.temp_c.toFixed(0)}°C{b.hot ? " (hot)" : ""}</span>} />}
          {b.tonight && <Row k="Tonight" v={b.tonight} />}
        </dl>
        {b.fading && <p className="mt-2 text-sm text-warn">It is losing capacity faster than normal. See Battery health below.</p>}
      </div>
    );
  }
  if (part === "inverter") {
    const inv = live.inverter;
    return (
      <div>
        <h3 className="font-display font-semibold">Inverter</h3>
        <dl className="mt-3 text-sm">
          <Row k="Size" v={`${inv.kw} kW`} />
          <Row k="Load right now" v={`${inv.load_percent}% of its limit`} />
          <Row k="Priority" v={inv.mode === "SUB" ? "Solar, then NEPA; battery kept for outages" : "Solar, then battery, then NEPA"} />
          {inv.fault && <Row k="Fault" v={<span className="text-alarm">{inv.fault}</span>} />}
        </dl>
        {inv.load_percent > 85 && <p className="mt-2 text-sm text-warn">Close to its limit: don&apos;t switch on anything big now.</p>}
      </div>
    );
  }
  if (part === "nepa") {
    return (
      <div>
        <h3 className="font-display font-semibold">NEPA (grid)</h3>
        <p className="mt-1 text-sm">
          {live.nepa_on
            ? live.nepa_w > 20 ? `Light is on and supplying ${kw(live.nepa_w)}.` : "Light is on, but solar and battery are covering the house."
            : "No light from NEPA right now. Solar and the battery are powering the house."}
        </p>
      </div>
    );
  }
  const on = live.appliances.filter((a) => a.on);
  return (
    <div>
      <h3 className="font-display font-semibold">In your home</h3>
      <p className="mt-1 text-sm">Using {kw(live.house_w)} right now.</p>
      <p className="mt-2 text-sm text-muted">Probably on (estimated from the total power):</p>
      <p className="mt-1 text-sm font-medium">{on.length ? on.map((a) => a.name).join(", ") : "Nothing big"}</p>
    </div>
  );
}

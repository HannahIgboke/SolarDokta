"use client";
// Drag the battery room temperature and see how much faster the battery ages (wear roughly
// doubles for every 10°C above 25°C) and how much less the panels make in that heat.
import { useState } from "react";

export function HeatSlider() {
  const [temp, setTemp] = useState(36);
  const speed = 2 ** ((temp - 25) / 10);
  const years = Math.max(1.5, 10 / speed);
  const panelLoss = Math.round(0.35 * Math.max(0, temp + 28 - 25));   // panels run ~28°C above the air at midday
  const fill = ((temp - 20) / 30) * 100;

  return (
    <div className="rounded-[28px] bg-white/10 p-6 backdrop-blur sm:p-8">
      <label htmlFor="heat" className="block font-display text-xl font-semibold">
        How hot is the room your battery is in?
      </label>
      <div className="mt-6 flex items-end gap-6">
        <p className="font-display text-6xl font-bold tabular-nums sm:text-7xl">{temp}°C</p>
        <p className="pb-2 text-white/80">{temp <= 26 ? "Cool room" : temp < 33 ? "Warm room" : temp < 40 ? "Hot room" : "Very hot: like a sealed store in the sun"}</p>
      </div>
      <input id="heat" type="range" min={20} max={50} value={temp} onChange={(e) => setTemp(Number(e.target.value))}
             className="heat-range mt-5 w-full" style={{ ["--fill" as string]: `${fill}%` }} />
      <div className="mt-1 flex justify-between text-xs text-white/60"><span>20°C</span><span>50°C</span></div>
      <dl className="mt-7 grid gap-5 sm:grid-cols-3">
        {[
          [`${speed.toFixed(1)}×`, "how fast the battery ages, compared with a cool room"],
          [`${years.toFixed(years < 4 ? 1 : 0)} yrs`, "what a 10-year battery would last"],
          [`${panelLoss}%`, "less power from the panels at midday, if it's this hot outside"],
        ].map(([value, label]) => (
          <div key={label} className="flex flex-col-reverse">
            <dt className="mt-1 text-sm text-white/75">{label}</dt>
            <dd className="font-display text-4xl font-bold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-6 text-xs text-white/60">
        Rough guide, if the room stayed this hot all year. Battery chemistry wears about twice as fast for every
        10°C above 25°C; panels run about 28°C hotter than the air at midday and lose about 0.35% of their power for every degree above 25°C.
      </p>
    </div>
  );
}

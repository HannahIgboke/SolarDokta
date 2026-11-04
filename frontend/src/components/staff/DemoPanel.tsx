"use client";
// Break a simulated site on purpose and watch SolarDokta catch it (for demos and training).
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Section } from "../Section";

const FAULTS = [
  { kind: "string_failure", label: "Kill string 2", hint: "caught in about 10–20 minutes (daytime)" },
  { kind: "overload", label: "Overload for 30 min", hint: "a 7 kW load on top: the inverter trips" },
  { kind: "hot_battery_room", label: "Hot battery room", hint: "+12°C around the battery: caught in 2–3 days" },
  { kind: "shading", label: "Shade string 1", hint: "60% shade on string 1" },
  { kind: "soiling", label: "Heavy dust", hint: "35% loss: the dust check needs days of evidence" },
] as const;

export function DemoPanel({ code, onChanged }: { code: string; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const say = (t: string) => setLog((l) => [`${new Date().toLocaleTimeString("en-NG", { hour: "numeric", minute: "2-digit" })}: ${t}`, ...l].slice(0, 6));

  async function run(path: string, body?: object, done?: (r: Record<string, unknown>) => string) {
    setBusy(true);
    try {
      const r = await api<Record<string, unknown>>(`/api/sites/${code}/demo/${path}`, {
        method: "POST", body: body ? JSON.stringify(body) : undefined });
      say(done ? done(r) : "Done");
      onChanged();
    } catch (e) {
      say(e instanceof ApiError ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section title="Demo controls" aside="simulated sites only">
      <div className="flex flex-wrap gap-2">
        {FAULTS.map((f) => (
          <button key={f.kind} disabled={busy} title={f.hint}
                  onClick={() => run("fault", { kind: f.kind }, (r) => `${f.label}: ${String(r.message)}`)}
                  className="rounded-md border border-alarm/40 px-3 py-1.5 text-sm text-alarm hover:bg-alarm/5 disabled:opacity-50">
            {f.label}
          </button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button disabled={busy} onClick={() => run("fix", undefined, (r) => `Fixed: ended ${r.ended} fault(s)`)}
                className="rounded-md bg-charge px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">Fix everything</button>
        <button disabled={busy} onClick={() => run("check", undefined, (r) =>
                  `Checked: ${r.new_readings} new readings; new: ${(r.new as string[] | undefined)?.join(", ") || "none"}; cleared: ${(r.resolved as string[] | undefined)?.join(", ") || "none"}`)}
                className="rounded-md bg-ink px-3 py-1.5 text-sm font-medium text-sky disabled:opacity-50">
          {busy ? "Working…" : "Check now"}
        </button>
      </div>
      <p className="mt-2 text-xs text-muted">A fault starts with the next 5-minute reading. &ldquo;Check now&rdquo; runs the readings and the detectors straight away instead of waiting for the schedule.</p>
      {log.length > 0 && <ul className="mt-3 space-y-1 text-sm">{log.map((l) => <li key={l}>{l}</li>)}</ul>}
    </Section>
  );
}

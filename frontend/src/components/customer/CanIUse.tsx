"use client";
// "Can I use…?" One tap per big appliance, answered from live data (same check as the chat).
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { applianceLabel } from "@/lib/labels";
import type { Appliance, CanIRun } from "@/lib/types";
import { Section } from "../Section";

const BIG = /iron|pump|microwave|\bac\b|washing|kettle|steriliz|borehole|computer lab/;

const VERDICT = {
  yes: { text: "Yes", cls: "bg-charge text-white" },
  yes_but: { text: "Yes, but…", cls: "bg-warn text-white" },
  no: { text: "Not now", cls: "bg-alarm text-white" },
} as const;

export function CanIUse({ code, appliances }: { code: string; appliances: Appliance[] }) {
  const options = appliances.filter((a) => BIG.test(a.name) || a.watts >= 700).slice(0, 6);
  const [busy, setBusy] = useState<string | null>(null);
  const [answer, setAnswer] = useState<{ name: string; r: CanIRun } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function check(a: Appliance) {
    setBusy(a.name);
    setError(null);
    try {
      const q = new URLSearchParams({ appliance: a.name, watts: String(a.watts) });
      setAnswer({ name: a.name, r: await api<CanIRun>(`/api/sites/${code}/tools/can_i_run?${q}`) });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't check that");
    } finally {
      setBusy(null);
    }
  }

  const v = answer && answer.r.verdict in VERDICT ? VERDICT[answer.r.verdict as keyof typeof VERDICT] : null;
  return (
    <Section title="Can I use…?" aside="tap to check right now">
      <div className="flex flex-wrap gap-2">
        {options.map((a) => (
          <button key={a.name} onClick={() => check(a)} disabled={busy !== null}
                  className={`rounded-full border px-3.5 py-1.5 text-sm transition-colors first-letter:uppercase ${
                    answer?.name === a.name ? "border-ink bg-ink text-sky" : "border-line bg-sky hover:border-ink"}`}>
            {busy === a.name ? "Checking…" : applianceLabel(a.name)}
          </button>
        ))}
      </div>
      {error && <p className="mt-3 text-sm text-alarm">{error}</p>}
      {answer && v && (
        <div className="mt-4 flex gap-3" aria-live="polite">
          <span className={`h-fit shrink-0 rounded-md px-2.5 py-1 text-sm font-semibold ${v.cls}`}>{v.text}</span>
          <div className="text-sm">
            <p className="first-letter:uppercase">{answer.r.reasons?.join("; ")}.</p>
            {answer.r.battery_percent_after !== undefined && answer.r.powered_by !== "nepa" && (
              <p className="text-muted">Battery after: about {answer.r.battery_percent_after}%</p>
            )}
            {answer.r.tips?.map((t) => <p key={t} className="mt-1 text-muted first-letter:uppercase">Tip: {t}.</p>)}
          </div>
        </div>
      )}
    </Section>
  );
}

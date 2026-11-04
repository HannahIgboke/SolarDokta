"use client";
// Problems SolarDokta has found, worst first, in plain words with what to do.
import type { Problems as ProblemsData } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Failed, Loading, Section } from "../Section";

const TONE = {
  critical: { bar: "bg-alarm", label: "Urgent", text: "text-alarm" },
  warning: { bar: "bg-warn", label: "Needs attention", text: "text-warn" },
  info: { bar: "bg-muted", label: "Good to know", text: "text-muted" },
};

export function Problems({ code }: { code: string }) {
  const { data, error, loading } = useApi<ProblemsData>(`/api/sites/${code}/tools/open_problems`, 5 * 60_000);
  const recent = (data?.["events_last_7_days"] as ProblemsData["open_problems"] | undefined) ?? [];
  return (
    <Section title="Problems">
      {loading && <Loading what="problems" />}
      {error && <Failed message={error} />}
      {data?.all_clear && (
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-full bg-charge/15 text-charge">✓</span>
          <p>All clear. SolarDokta checks your system every five minutes and will tell you if anything goes wrong.</p>
        </div>
      )}
      <ul className="space-y-3">
        {data?.open_problems.map((p) => {
          const t = TONE[p.urgency];
          return (
            <li key={`${p.problem}-${p.since}`} className="flex gap-3">
              <span className={`w-1 shrink-0 rounded-full ${t.bar}`} />
              <div>
                <p className={`text-xs font-semibold ${t.text}`}>{t.label}{p.panel_string ? `: ${p.panel_string}` : ""}</p>
                <p className="font-medium first-letter:uppercase">{p.problem}</p>
                <p className="text-sm text-muted first-letter:uppercase">{p.what_to_do}. Since {p.since}.</p>
              </div>
            </li>
          );
        })}
      </ul>
      {recent.length > 0 && (
        <p className="mt-4 border-t border-line pt-3 text-sm text-muted">
          This week: {recent.length} short event{recent.length > 1 ? "s" : ""} ({recent[0].problem}).
        </p>
      )}
    </Section>
  );
}

"use client";
// Every problem SolarDokta has found across the installer's sites, worst first, with actions.
import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Failed, Loading } from "../Section";

const SEV = {
  critical: { label: "Urgent", cls: "bg-alarm/10 text-alarm" },
  warning: { label: "Warning", cls: "bg-warn/10 text-warn" },
  info: { label: "Info", cls: "bg-nepa/10 text-nepa" },
};

function detailLine(f: Finding): string | null {
  const d = f.details as Record<string, unknown>;
  const bits = [];
  if (d.target && d.target !== "all") bits.push(`string ${String(d.target).slice(-1)}`);
  if (typeof d.summary === "string") bits.push(`“${d.summary}”`);
  if (typeof d.blackout_minutes === "number") bits.push(`${d.blackout_minutes} min without power`);
  if (typeof d.fade_per_year === "number") bits.push(`losing ${(d.fade_per_year * 100).toFixed(1)}%/year`);
  if (typeof d.high_c === "number") bits.push(`${d.high_c}°C forecast`);
  if (f.score !== null) bits.push(`anomaly score ${f.score.toFixed(2)}`);
  return bits.length ? bits.join(" · ") : null;
}

function Row({ f, onChange, showSite }: { f: Finding; onChange: () => void; showSite: boolean }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function set(status: Finding["status"]) {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/findings/${f.id}`, { method: "POST", body: JSON.stringify({ status, note }) });
      onChange();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't update");
    } finally {
      setBusy(false);
    }
  }
  const s = SEV[f.severity];
  return (
    <li className="rounded-xl border border-line bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <span className={`rounded px-2 py-0.5 text-xs font-semibold ${s.cls}`}>{s.label}</span>
            {showSite && <Link href={`/staff/sites/${f.site}`} className="font-medium hover:underline">{f.site_name}</Link>}
            <span className="text-muted">{f.kind.replaceAll("_", " ")}</span>
          </p>
          <p className="mt-1 font-medium first-letter:uppercase">{f.problem}</p>
          {detailLine(f) && <p className="text-sm text-muted">{detailLine(f)}</p>}
          <p className="text-xs text-muted">
            Since {new Date(f.ts_start).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}
            {f.status !== "open" && f.ts_end && ` · ${f.status} ${new Date(f.ts_end).toLocaleDateString("en-NG", { day: "numeric", month: "short" })}`}
            {f.note && ` · note: ${f.note}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {f.status === "open" ? (
            <>
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" maxLength={500}
                     className="w-44 rounded-md border border-line px-2 py-1.5 text-sm" aria-label="Note" />
              <button disabled={busy} onClick={() => set("resolved")} className="rounded-md bg-charge px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">Resolve</button>
              <button disabled={busy} onClick={() => set("dismissed")} className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-50">Dismiss</button>
            </>
          ) : (
            <button disabled={busy} onClick={() => set("open")} className="rounded-md border border-line px-3 py-1.5 text-sm">Reopen</button>
          )}
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-alarm">{error}</p>}
    </li>
  );
}

export function ProblemsInbox({ site }: { site?: string }) {
  const [status, setStatus] = useState<"open" | "resolved" | "dismissed" | "all">("open");
  const [severity, setSeverity] = useState<"all" | Finding["severity"]>("all");
  const q = new URLSearchParams({ status, ...(site ? { site } : {}) });
  const { data, error, loading, reload } = useApi<{ findings: Finding[] }>(`/api/findings?${q}`, 60_000);
  const rows = (data?.findings ?? []).filter((f) => severity === "all" || f.severity === severity);
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2 text-sm">
        <select value={status} onChange={(e) => setStatus(e.target.value as typeof status)} aria-label="Status"
                className="rounded-md border border-line bg-card px-2 py-1.5">
          <option value="open">Open</option><option value="resolved">Resolved</option>
          <option value="dismissed">Dismissed</option><option value="all">All</option>
        </select>
        <select value={severity} onChange={(e) => setSeverity(e.target.value as typeof severity)} aria-label="Urgency"
                className="rounded-md border border-line bg-card px-2 py-1.5">
          <option value="all">Any urgency</option><option value="critical">Urgent</option>
          <option value="warning">Warning</option><option value="info">Info</option>
        </select>
        <span className="self-center text-muted">{rows.length} shown</span>
      </div>
      {loading && !data && <Loading what="problems" />}
      {error && <Failed message={error} />}
      {data && rows.length === 0 && <p className="text-sm text-muted">Nothing here. {status === "open" ? "Every site is clear." : ""}</p>}
      <ul className="space-y-3">{rows.map((f) => <Row key={f.id} f={f} onChange={reload} showSite={!site} />)}</ul>
    </div>
  );
}

"use client";
// What the customer can tell SolarDokta: receipts (real NEPA and fuel prices), voice notes,
// photos of their equipment, and the appliances they own. Gemini reads files on the server.
import { useEffect, useRef, useState } from "react";
import { api, apiUpload, ApiError } from "@/lib/api";
import type { ApplianceRow, Upload } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useLang } from "@/lib/i18n";

type Tab = "receipt" | "fuel" | "voice" | "photo" | "appliances";
const TABS: { id: Tab; label: [string, string, string]; what: [string, string, string]; icon: string }[] = [
  { id: "receipt", icon: "🧾", label: ["Token or fuel receipt", "Token or fuel receipt", "Akwụkwọ ụgwọ token ma ọ bụ mmanụ"],
    what: ["Your real NEPA and fuel prices", "Your real NEPA and fuel price", "Ezigbo ọnụ ahịa NEPA na mmanụ gị"] },
  { id: "fuel", icon: "⛽", label: ["Fuel price", "Fuel price", "Ọnụ ahịa mmanụ"],
    what: ["What you paid at the filling station", "Wetin you pay for filling station", "Ihe ị kwụrụ n'ọdụ mmanụ"] },
  { id: "voice", icon: "🎙", label: ["Voice note", "Voice note", "Ozi olu"],
    what: ["Report a problem by talking", "Talk wetin dey happen", "Kọọ nsogbu site n'ikwu okwu"] },
  { id: "photo", icon: "📷", label: ["Photo", "Photo", "Foto"],
    what: ["Your inverter, battery or panels", "Your inverter, battery or panels", "Inverter, batrị ma ọ bụ panel gị"] },
  { id: "appliances", icon: "🔌", label: ["My appliances", "My appliances", "Ngwa m"],
    what: ["What you really own", "Wetin you really get", "Ihe ị nwere n'ezie"] },
];
const LI = { en: 0, pcm: 1, ig: 2 } as const;
const KIND_LABEL: Record<Upload["kind"], string> = {
  token_receipt: "NEPA token receipt", fuel_receipt: "Fuel receipt", voice_note: "Voice note", photo: "Photo",
};
const input = "rounded-md border border-line bg-card px-3 py-2 text-sm";
const button = "rounded-md bg-ink px-4 py-2 text-sm font-medium text-sky disabled:opacity-50";

function summary(u: Upload): string {
  const e = u.extracted as Record<string, string | number | boolean | null>;
  if (u.status === "failed") return u.error ?? "Couldn't read this file";
  if (u.status === "pending") return "Reading…";
  if (e.applied) return String(e.applied);
  if (u.kind === "voice_note") return `“${e.summary ?? e.transcript ?? ""}”`;
  if (u.kind === "photo") return [e.shows, e.brand, e.model, e.rating_text].filter(Boolean).join(" · ") || "Saved";
  if (e.readable === false) return "Couldn't read it clearly. Try a sharper photo.";
  return "Saved";
}

export function YourInputs({ code, onSaved }: { code: string; onSaved?: () => void }) {
  const list = useApi<{ uploads: Upload[] }>(`/api/sites/${code}/uploads`);
  const { t, lang } = useLang();
  const [active, setTab] = useState<Tab>("receipt");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function send(kind: Upload["kind"], file: Blob, name: string, component?: string) {
    setBusy(true);
    setMessage(null);
    const form = new FormData();
    form.append("kind", kind);
    if (component) form.append("component", component);
    form.append("file", file, name);
    try {
      const u = await apiUpload<Upload>(`/api/sites/${code}/uploads`, form);
      setMessage({ ok: u.status === "read", text: summary(u) });
      list.reload();
      onSaved?.();
    } catch (e) {
      setMessage({ ok: false, text: e instanceof ApiError ? e.message : "Upload failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-3xl font-semibold">{t("tell.title")}</h2>
        <p className="mt-1 max-w-2xl text-muted">{t("tell.intro")}</p>
      </div>
      <div role="tablist" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {TABS.map((tab) => (
          <button key={tab.id} role="tab" aria-selected={active === tab.id} onClick={() => { setTab(tab.id); setMessage(null); }}
                  className={`rounded-3xl p-4 text-left transition-colors ${active === tab.id ? "bg-ink text-sky" : "bg-white hover:bg-[#f7f9fb]"}`}>
            <span className="text-2xl" aria-hidden="true">{tab.icon}</span>
            <span className="mt-2 block font-semibold">{tab.label[LI[lang]]}</span>
            <span className={`block text-sm ${active === tab.id ? "text-sky/75" : "text-muted"}`}>{tab.what[LI[lang]]}</span>
          </button>
        ))}
      </div>
      <div className="rounded-3xl bg-white p-5 sm:p-6">
        {active === "receipt" && <ReceiptForm busy={busy} send={send} />}
        {active === "fuel" && <FuelForm code={code} onDone={(text, ok) => { setMessage({ ok, text }); onSaved?.(); }} />}
        {active === "voice" && <VoiceForm busy={busy} send={send} />}
        {active === "photo" && <PhotoForm busy={busy} send={send} />}
        {active === "appliances" && <ApplianceEditor code={code} onDone={(text, ok) => { setMessage({ ok, text }); onSaved?.(); }} />}
        {busy && <p className="mt-3 text-sm text-muted">Uploading and reading it…</p>}
        {message && <p role="status" className={`mt-3 text-sm ${message.ok ? "text-charge" : "text-warn"}`}>{message.text}</p>}
      </div>
      {(list.data?.uploads.length ?? 0) > 0 && (
        <div className="rounded-3xl bg-white p-5 sm:p-6">
          <h3 className="font-display text-lg font-semibold">Added so far</h3>
          <ul className="mt-2 space-y-3">
            {list.data!.uploads.slice(0, 8).map((u) => (
              <li key={u.id} className="flex gap-3 text-sm">
                {u.kind === "photo" && u.url
                  // eslint-disable-next-line @next/next/no-img-element -- signed Supabase links, not optimisable
                  ? <img src={u.url} alt={u.component ?? "photo"} className="h-14 w-14 shrink-0 rounded-md object-cover" />
                  : <span className="grid h-14 w-14 shrink-0 place-items-center rounded-md bg-sky text-xs text-muted">{u.kind === "voice_note" ? "audio" : "receipt"}</span>}
                <div className="min-w-0">
                  <p className="font-medium">{KIND_LABEL[u.kind]}{u.component ? `: ${u.component}` : ""}
                    <span className="ml-2 font-normal text-muted">{new Date(u.created_at).toLocaleDateString("en-NG", { day: "numeric", month: "short" })}</span>
                  </p>
                  <p className={u.status === "failed" ? "text-warn" : "text-muted"}>{summary(u)}</p>
                  {typeof u.extracted.warning === "string" && <p className="text-warn">{u.extracted.warning}</p>}
                  {u.kind === "voice_note" && u.url && <audio controls src={u.url} className="mt-1 h-8 w-full max-w-xs" />}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

type Send = (kind: Upload["kind"], file: Blob, name: string, component?: string) => Promise<void>;

function ReceiptForm({ busy, send }: { busy: boolean; send: Send }) {
  const [kind, setKind] = useState<"token_receipt" | "fuel_receipt">("token_receipt");
  const [file, setFile] = useState<File | null>(null);
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (file) send(kind, file, file.name); }}>
      <p className="text-sm text-muted">A photo or PDF of a prepaid token receipt or SMS gives your real NEPA price. A fuel receipt gives your real petrol or diesel price.</p>
      <div className="flex flex-wrap gap-2">
        <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} className={input} aria-label="Receipt type">
          <option value="token_receipt">NEPA token receipt</option>
          <option value="fuel_receipt">Fuel receipt</option>
        </select>
        <input type="file" accept="image/*,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" aria-label="Receipt file" />
      </div>
      <button className={button} disabled={busy || !file}>Read receipt</button>
    </form>
  );
}

function FuelForm({ code, onDone }: { code: string; onDone: (text: string, ok: boolean) => void }) {
  const [fuel, setFuel] = useState("petrol");
  const [litres, setLitres] = useState("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api<{ price_per_litre: number }>(`/api/sites/${code}/fuel`, {
        method: "POST", body: JSON.stringify({ fuel, litres: Number(litres), amount_ngn: Number(amount) }) });
      onDone(`Saved: ₦${r.price_per_litre.toLocaleString()} per litre of ${fuel}. Your money view now uses it.`, true);
    } catch (err) {
      onDone(err instanceof ApiError ? err.message : "Couldn't save that", false);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={save}>
      <label className="text-sm">Fuel<br />
        <select value={fuel} onChange={(e) => setFuel(e.target.value)} className={input}><option>petrol</option><option>diesel</option></select>
      </label>
      <label className="text-sm">Litres<br /><input required type="number" min="1" step="0.1" value={litres} onChange={(e) => setLitres(e.target.value)} className={`${input} w-24`} /></label>
      <label className="text-sm">Paid (₦)<br /><input required type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} className={`${input} w-32`} /></label>
      <button className={button} disabled={busy}>Save fuel price</button>
    </form>
  );
}

function VoiceForm({ busy, send }: { busy: boolean; send: Send }) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!recording) return;
    const id = setInterval(() => setSeconds((s) => (s >= 119 ? (rec.current?.stop(), s) : s + 1)), 1000);
    return () => clearInterval(id);
  }, [recording]);

  async function start() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const type = ["audio/ogg;codecs=opus", "audio/webm;codecs=opus", "audio/mp4"].find((t) => MediaRecorder.isTypeSupported(t));
      const r = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      chunks.current = [];
      r.ondataavailable = (e) => chunks.current.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        const mime = (r.mimeType || "audio/webm").split(";")[0];
        send("voice_note", new Blob(chunks.current, { type: mime }), `voice.${mime.split("/")[1]}`);
      };
      rec.current = r;
      r.start();
      setSeconds(0);
      setRecording(true);
    } catch {
      setError("Couldn't use the microphone. Allow microphone access, or choose an audio file instead.");
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">Talk in English or Pidgin, for example &ldquo;My inverter dey beep since morning&rdquo; or &ldquo;We bought a new freezer&rdquo;. Problems go straight to your technician.</p>
      <div className="flex flex-wrap items-center gap-3">
        {recording
          ? <button onClick={() => rec.current?.stop()} className="rounded-full bg-alarm px-4 py-2 text-sm font-medium text-white">Stop and send ({seconds}s)</button>
          : <button onClick={start} disabled={busy} className={`${button} rounded-full`}>Record a voice note</button>}
        <label className="text-sm text-muted">or choose a file{" "}
          <input type="file" accept="audio/*" disabled={busy || recording} className="text-sm"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) send("voice_note", f, f.name); }} />
        </label>
      </div>
      {error && <p className="text-sm text-warn">{error}</p>}
    </div>
  );
}

function PhotoForm({ busy, send }: { busy: boolean; send: Send }) {
  const [component, setComponent] = useState("inverter");
  const [file, setFile] = useState<File | null>(null);
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (file) send("photo", file, file.name, component); }}>
      <p className="text-sm text-muted">Photos of your inverter, battery or panels show up in the live picture. If a label is readable, SolarDokta checks it against your system&apos;s recorded size.</p>
      <div className="flex flex-wrap gap-2">
        <select value={component} onChange={(e) => setComponent(e.target.value)} className={input} aria-label="What the photo shows">
          <option value="inverter">Inverter</option><option value="battery">Battery</option><option value="panels">Panels</option>
          <option value="distribution_board">Distribution board</option><option value="appliance">Appliance</option><option value="other">Other</option>
        </select>
        <input type="file" accept="image/*" capture="environment" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" aria-label="Photo" />
      </div>
      <button className={button} disabled={busy || !file}>Upload photo</button>
    </form>
  );
}

function ApplianceEditor({ code, onDone }: { code: string; onDone: (text: string, ok: boolean) => void }) {
  const { data } = useApi<{ appliances: ApplianceRow[]; source: string }>(`/api/sites/${code}/appliances`);
  const [rows, setRows] = useState<ApplianceRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const list = rows ?? data?.appliances ?? [];
  const set = (i: number, patch: Partial<ApplianceRow>) => setRows(list.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  async function save() {
    setBusy(true);
    try {
      const clean = list.filter((r) => r.name.trim() && r.watts > 0);
      await api(`/api/sites/${code}/appliances`, { method: "PUT", body: JSON.stringify(clean) });
      onDone(`Saved ${clean.length} appliances. "Can I use…?" and the live picture now use your list.`, true);
    } catch (e) {
      onDone(e instanceof ApiError ? e.message : "Couldn't save", false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="mb-3 text-sm text-muted">
        {data?.source === "yours" ? "Your appliance list." : "A typical list for a home like yours. Change it to match what you really have."} Watts are on the appliance&apos;s label.
      </p>
      <div className="space-y-2">
        {list.map((r, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <input value={r.name} onChange={(e) => set(i, { name: e.target.value })} className={`${input} min-w-0 flex-1`} aria-label="Appliance" />
            <input type="number" min="1" value={r.watts} onChange={(e) => set(i, { watts: Number(e.target.value) })} className={`${input} w-24`} aria-label="Watts" />
            <span className="text-xs text-muted">W ×</span>
            <input type="number" min="1" value={r.qty} onChange={(e) => set(i, { qty: Number(e.target.value) })} className={`${input} w-16`} aria-label="How many" />
            <button onClick={() => setRows(list.filter((_, j) => j !== i))} className="px-2 text-sm text-muted hover:text-alarm" aria-label={`Remove ${r.name}`}>Remove</button>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <button onClick={() => setRows([...list, { name: "", watts: 100, qty: 1 }])} className="rounded-md border border-line px-3 py-2 text-sm">Add appliance</button>
        <button onClick={save} disabled={busy} className={button}>Save my appliances</button>
      </div>
    </div>
  );
}

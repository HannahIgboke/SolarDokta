"use client";
// Ask Dokta: chat with SolarDokta by typing or by voice, answered in the chosen language
// (English, Pidgin or Igbo). The same brain as WhatsApp. Technicians get a different set of
// suggested questions and more technical answers.
import { useEffect, useRef, useState } from "react";
import { api, apiUpload, ApiError } from "@/lib/api";
import { LangSwitch, useLang } from "@/lib/i18n";

type Turn = { role: "user" | "model"; text: string; voice?: boolean };
type Reply = { reply: string; transcript?: string };

const STAFF_SUGGESTIONS = [
  "Why did this site's battery run out last week?",
  "Is string 2 underperforming compared with string 1?",
  "How much extra battery wear is the heat causing here?",
  "What should I check on my next visit?",
];

export function AskDokta({ code, staff = false, compact = false }: { code: string; staff?: boolean; compact?: boolean }) {
  const { t, lang, suggestions } = useLang();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [secs, setSecs] = useState(0);
  const [micError, setMicError] = useState(false);
  const chunks = useRef<Blob[]>([]);
  const end = useRef<HTMLDivElement>(null);
  const language = staff ? "en" : lang;

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [turns, busy]);
  useEffect(() => {
    if (!rec) return;
    const id = setInterval(() => setSecs((s) => { if (s >= 59) rec.stop(); return s + 1; }), 1000);
    return () => clearInterval(id);
  }, [rec]);

  const history = () => turns.slice(-10).map(({ role, text }) => ({ role, text }));
  const fail = (e: unknown) => setTurns((x) => [...x, { role: "model", text: e instanceof ApiError ? e.message : "Couldn't reach SolarDokta." }]);

  async function send(message: string) {
    const m = message.trim();
    if (!m || busy) return;
    const past = history();
    setTurns((x) => [...x, { role: "user", text: m }]);
    setText("");
    setBusy(true);
    try {
      const r = await api<Reply>(`/api/sites/${code}/chat`, { method: "POST", body: JSON.stringify({ message: m, history: past, language }) });
      setTurns((x) => [...x, { role: "model", text: r.reply }]);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function sendVoice(blob: Blob, mime: string) {
    const form = new FormData();
    form.append("audio", blob, `question.${mime.split("/")[1] || "webm"}`);
    form.append("language", language);
    form.append("history", JSON.stringify(history()));
    setBusy(true);
    try {
      const r = await apiUpload<Reply>(`/api/sites/${code}/chat/voice`, form);
      setTurns((x) => [...x, { role: "user", text: r.transcript ?? "", voice: true }, { role: "model", text: r.reply }]);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function startVoice() {
    setMicError(false);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const type = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported(m));
      const r = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      chunks.current = [];
      r.ondataavailable = (e) => chunks.current.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((tr) => tr.stop());
        setRec(null);
        const mime = (r.mimeType || "audio/webm").split(";")[0];
        sendVoice(new Blob(chunks.current, { type: mime }), mime);
      };
      r.start();
      setSecs(0);
      setRec(r);
    } catch {
      setMicError(true);
    }
  }

  const list = staff ? STAFF_SUGGESTIONS : suggestions;
  return (
    <div className={`flex flex-col overflow-hidden rounded-3xl bg-white ${compact ? "h-[560px]" : "h-[min(720px,calc(100vh-180px))] min-h-[480px]"}`}>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 className="font-display text-xl font-semibold">{staff ? "Ask Dokta (technician)" : t("ask.title")}</h2>
          <p className="text-sm text-muted">{staff ? "Technical answers about this site: findings, string performance, battery wear." : t("ask.intro")}</p>
        </div>
        {!staff && <div className="flex items-center gap-2 text-xs text-muted">{t("ask.answersIn")} <LangSwitch /></div>}
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto bg-[#f4f7fa] p-4 sm:p-5" aria-live="polite">
        {turns.length === 0 && (
          <div>
            <p className="mb-2 text-sm text-muted">{staff ? "Try one of these" : t("ask.try")}</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {list.map((s) => (
                <button key={s} onClick={() => send(s)} className="rounded-2xl border border-line bg-white px-4 py-3 text-left text-sm hover:border-ink">{s}</button>
              ))}
            </div>
          </div>
        )}
        {turns.map((m, k) => (
          <div key={k} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 whitespace-pre-line ${m.role === "user" ? "rounded-br-sm bg-ink text-sky" : "rounded-bl-sm bg-white shadow-[0_1px_0_#d5dde6]"}`}>
              {m.voice && <p className="mb-0.5 text-xs text-sky/70">🎙 {t("ask.heard")}</p>}
              {m.text}
            </div>
          </div>
        ))}
        {busy && <p className="animate-pulse text-sm text-muted">{t("ask.thinking")}</p>}
        <div ref={end} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex items-center gap-2 border-t border-line p-3">
        {rec ? (
          <button type="button" onClick={() => rec.stop()} className="flex flex-1 items-center justify-center gap-2 rounded-full bg-alarm px-4 py-3 font-semibold text-white">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-white" /> {t("ask.listening", { s: secs })} · {t("ask.stop")}
          </button>
        ) : (
          <>
            <button type="button" onClick={startVoice} disabled={busy} aria-label={t("ask.talk")} title={t("ask.talk")}
                    className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-sun text-ink disabled:opacity-50">
              <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" fill="currentColor" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
            </button>
            <input value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} placeholder={t("ask.placeholder")} aria-label={t("ask.placeholder")}
                   className="min-w-0 flex-1 rounded-full border border-line bg-sky px-4 py-3" />
            <button type="submit" disabled={busy || !text.trim()} className="rounded-full bg-ink px-5 py-3 font-semibold text-sky disabled:opacity-50">{t("ask.send")}</button>
          </>
        )}
      </form>
      {micError && <p className="px-4 pb-3 text-sm text-warn">{t("ask.mic")}</p>}
    </div>
  );
}

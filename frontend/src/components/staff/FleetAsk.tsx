"use client";
// Ask Dokta for technicians: questions about every site at once ("which batteries are suffering
// most from the heat?"). Answered from the live fleet data, in technical language.
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Turn = { role: "user" | "model"; text: string };
const SUGGESTIONS = [
  "Which sites should I visit first today, and why?",
  "Which batteries are suffering most from the El Niño heat?",
  "Which customers ran out of power most this week?",
  "Where would a bigger battery help most?",
];

export function FleetAsk() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [turns, busy]);

  async function send(message: string) {
    const m = message.trim();
    if (!m || busy) return;
    const history = turns.slice(-10);
    setTurns((x) => [...x, { role: "user", text: m }]);
    setText("");
    setBusy(true);
    try {
      const r = await api<{ reply: string }>("/api/fleet/chat", { method: "POST", body: JSON.stringify({ message: m, history }) });
      setTurns((x) => [...x, { role: "model", text: r.reply }]);
    } catch (e) {
      setTurns((x) => [...x, { role: "model", text: e instanceof ApiError ? e.message : "Couldn't reach SolarDokta." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="overflow-hidden rounded-3xl bg-ink text-sky">
      <div className="grid lg:grid-cols-[1fr_1.4fr]">
        <div className="p-6">
          <h2 className="font-display text-2xl font-semibold">Ask Dokta about all your sites</h2>
          <p className="mt-2 text-sky/75">For technicians: answers use the live readings, problems, battery heat and NEPA hours of every site you manage.</p>
          <div className="mt-5 space-y-2">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => send(s)} disabled={busy}
                      className="block w-full rounded-2xl bg-white/10 px-4 py-3 text-left text-sm hover:bg-white/15 disabled:opacity-60">{s}</button>
            ))}
          </div>
        </div>
        <div className="flex min-h-[360px] flex-col bg-[#1c2c4d]">
          <div className="flex-1 space-y-3 overflow-y-auto p-5" aria-live="polite">
            {turns.length === 0 && <p className="text-sky/60">Pick a question or type your own.</p>}
            {turns.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <p className={`max-w-[88%] rounded-2xl px-4 py-2.5 whitespace-pre-line ${m.role === "user" ? "rounded-br-sm bg-sun text-ink" : "rounded-bl-sm bg-white text-ink"}`}>{m.text}</p>
              </div>
            ))}
            {busy && <p className="animate-pulse text-sm text-sky/70">Looking across your sites…</p>}
            <div ref={end} />
          </div>
          <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex gap-2 border-t border-white/10 p-3">
            <input value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} placeholder="Ask about your sites…" aria-label="Your question"
                   className="min-w-0 flex-1 rounded-full bg-white/10 px-4 py-3 text-sky placeholder:text-sky/50" />
            <button type="submit" disabled={busy || !text.trim()} className="rounded-full bg-sun px-5 py-3 font-semibold text-ink disabled:opacity-50">Ask</button>
          </form>
        </div>
      </div>
    </section>
  );
}

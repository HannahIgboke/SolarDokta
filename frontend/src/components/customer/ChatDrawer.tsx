"use client";
// "Ask SolarDokta": the same assistant as WhatsApp, in a side panel. English or Pidgin.
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Turn = { role: "user" | "model"; text: string };
const SUGGESTIONS = ["Can I use my pressing iron now?", "How my battery dey?", "How will tomorrow be?", "How much have I saved?"];

export function ChatDrawer({ code }: { code: string }) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" }); // braces: newer browsers return a Promise here
  }, [turns, busy]);
  useEffect(() => {
    if (open) input.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open]);

  async function send(message: string) {
    const m = message.trim();
    if (!m || busy) return;
    const history = turns.slice(-10);
    setTurns((t) => [...t, { role: "user", text: m }]);
    setText("");
    setBusy(true);
    try {
      const r = await api<{ reply: string }>(`/api/sites/${code}/chat`, {
        method: "POST", body: JSON.stringify({ message: m, history }),
      });
      setTurns((t) => [...t, { role: "model", text: r.reply }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "model", text: e instanceof ApiError ? e.message : "Couldn't reach SolarDokta." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button onClick={() => setOpen(true)} aria-expanded={open}
              className="fixed right-4 bottom-4 z-30 flex items-center gap-2 rounded-full bg-ink px-5 py-3 font-medium text-sky shadow-lg shadow-ink/30">
        <span className="h-2.5 w-2.5 rounded-full bg-sun" /> Ask SolarDokta
      </button>
      {open && (
        <div className="fixed inset-0 z-40 flex justify-end bg-ink/30" onClick={() => setOpen(false)}>
          <aside role="dialog" aria-label="Ask SolarDokta" onClick={(e) => e.stopPropagation()}
                 className="flex h-full w-full max-w-md flex-col bg-sky shadow-2xl">
            <header className="flex items-center justify-between bg-ink px-4 py-3 text-sky">
              <div>
                <p className="font-display font-semibold">Ask SolarDokta</p>
                <p className="text-xs text-sky/70">English or Pidgin. Same answers as on WhatsApp.</p>
              </div>
              <button onClick={() => setOpen(false)} className="rounded px-2 py-1 hover:bg-white/10" aria-label="Close">✕</button>
            </header>
            <div className="flex-1 space-y-3 overflow-y-auto p-4">
              {turns.length === 0 && (
                <div className="space-y-2">
                  <p className="text-sm text-muted">Try one of these:</p>
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)}
                            className="block w-full rounded-lg border border-line bg-card px-3 py-2 text-left text-sm hover:border-ink">
                      {s}
                    </button>
                  ))}
                </div>
              )}
              {turns.map((t, i) => (
                <div key={i} className={`flex ${t.role === "user" ? "justify-end" : "justify-start"}`}>
                  <p className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm whitespace-pre-line ${
                    t.role === "user" ? "rounded-br-sm bg-ink text-sky" : "rounded-bl-sm border border-line bg-card"}`}>
                    {t.text}
                  </p>
                </div>
              ))}
              {busy && <p className="text-sm text-muted">SolarDokta is checking your system…</p>}
              <div ref={end} />
            </div>
            <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex gap-2 border-t border-line bg-card p-3">
              <input ref={input} value={text} onChange={(e) => setText(e.target.value)} maxLength={1000}
                     placeholder="Type a question…" aria-label="Your question"
                     className="flex-1 rounded-full border border-line bg-sky px-4 py-2 text-sm" />
              <button type="submit" disabled={busy || !text.trim()}
                      className="rounded-full bg-ink px-4 py-2 text-sm font-medium text-sky disabled:opacity-50">
                Send
              </button>
            </form>
          </aside>
        </div>
      )}
    </>
  );
}

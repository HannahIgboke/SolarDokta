"use client";
// What people actually ask, in English, Pidgin and Igbo, with the kind of answer SolarDokta gives.
import { useState } from "react";

type QA = { q: string; a: string };
const LANGS: { id: string; label: string; items: QA[] }[] = [
  { id: "en", label: "English", items: [
    { q: "Can I use my pressing iron now?",
      a: "Yes. The sun is strong and your battery is 78%. Iron before 2 pm so the battery is full again by evening." },
    { q: "Will my battery last till morning?",
      a: "Only just. You need about 6 kWh until sunrise and you have 6.4. Switch the AC off by 11 pm to be safe." },
    { q: "Why did my power go off yesterday?",
      a: "The battery ran out at 3:30 am after NEPA was off for 11 hours. Nothing is broken. Use less power after midnight on long outage nights." },
  ] },
  { id: "pcm", label: "Pidgin", items: [
    { q: "I fit put AC tonight?",
      a: "No o. If you put AC, battery go finish around 2am. Use fan instead, or off the AC by 11pm." },
    { q: "Wetin dey do my solar?",
      a: "One side of your panels no dey produce since 10:40 this morning. We don tell your installer. No touch am yourself." },
    { q: "How much I don save this month?",
      a: "About N38,000 for fuel and NEPA wey you no buy, because of your solar." },
  ] },
  { id: "ig", label: "Igbo", items: [
    { q: "Enwere m ike ịgba ígwè ugbu a?",
      a: "Ee. Anyanwụ na-acha nke ọma, batrị gị dị na 78%. Gbaa ya tupu elekere abụọ." },
    { q: "Batrị m ọ ga-eru ụtụtụ?",
      a: "Ee, ma gbanyụọ AC tupu elekere iri na otu abalị." },
    { q: "Ọ̀ dị ihe mebiri emebi?",
      a: "Otu akụkụ panel gị anaghị arụ ọrụ kemgbe ụtụtụ. Anyị agwala onye rụnyere ya." },
  ] },
];

export function AskExamples() {
  const [lang, setLang] = useState(0);
  const [pick, setPick] = useState(0);
  const items = LANGS[lang].items;
  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_1.1fr] lg:items-start">
      <div>
        <div role="tablist" aria-label="Language" className="inline-flex rounded-full bg-white p-1 shadow-[0_1px_0_#d5dde6]">
          {LANGS.map((l, i) => (
            <button key={l.id} role="tab" aria-selected={lang === i} onClick={() => { setLang(i); setPick(0); }}
                    className={`rounded-full px-4 py-1.5 text-sm font-medium ${lang === i ? "bg-ink text-sky" : "text-muted hover:text-ink"}`}>
              {l.label}
            </button>
          ))}
        </div>
        <ul className="mt-5 space-y-2">
          {items.map((it, i) => (
            <li key={it.q}>
              <button onClick={() => setPick(i)} aria-pressed={pick === i}
                      className={`w-full rounded-2xl border px-4 py-3 text-left font-medium ${pick === i ? "border-ink bg-white" : "border-line hover:border-muted"}`}>
                {it.q}
              </button>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-sm text-muted">Type it or say it. Voice notes work too.</p>
      </div>

      <div className="rounded-[28px] bg-[#0b5d4a] p-5 sm:p-7" aria-live="polite">
        <div className="ml-auto max-w-[85%] rounded-2xl rounded-tr-sm bg-[#d9fdd3] px-4 py-3 text-ink">{items[pick].q}</div>
        <div key={`${lang}-${pick}`} className="msg-in mt-3 max-w-[90%] rounded-2xl rounded-tl-sm bg-white px-4 py-3 text-ink">
          <p className="mb-1 text-xs font-semibold text-[#0b5d4a]">SolarDokta</p>
          {items[pick].a}
        </div>
        <p className="mt-5 text-xs text-white/70">Every number comes from your own system&apos;s readings and tomorrow&apos;s weather, not a guess.</p>
      </div>
    </div>
  );
}

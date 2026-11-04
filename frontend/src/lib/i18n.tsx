"use client";
// The app's language: English, Nigerian Pidgin or Igbo. The choice is remembered in this browser.
// t("key") gives the words for the current language; {name} parts are filled from `vars`.
// The Igbo text should be checked by a fluent speaker before it goes to real customers.
import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Lang = "en" | "pcm" | "ig";
export const LANGS: { id: Lang; label: string; short: string }[] = [
  { id: "en", label: "English", short: "EN" },
  { id: "pcm", label: "Pidgin", short: "PCM" },
  { id: "ig", label: "Igbo", short: "IG" },
];

type Words = Record<string, [string, string, string]>;   // [English, Pidgin, Igbo]

const WORDS: Words = {
  "nav.home": ["Home", "Home", "Ụlọ"],
  "nav.usage": ["My usage", "My usage", "Ojiji m"],
  "nav.learn": ["Learn", "Learn am", "Mụta"],
  "nav.tell": ["Tell us", "Tell us", "Gwa anyị"],
  "nav.ask": ["Ask Dokta", "Ask Dokta", "Jụọ Dokta"],

  "greet.morning": ["Good morning", "Good morning", "Ụtụtụ ọma"],
  "greet.afternoon": ["Good afternoon", "Good afternoon", "Ehihie ọma"],
  "greet.evening": ["Good evening", "Good evening", "Mgbede ọma"],
  "stat.battery": ["Battery", "Battery", "Batrị"],
  "stat.solar": ["Solar now", "Solar now", "Anyanwụ ugbu a"],
  "stat.using": ["Home using", "House dey use", "Ụlọ na-eji"],
  "stat.nepa": ["NEPA", "NEPA", "NEPA"],
  "on": ["On", "Dey", "Nọ"],
  "off": ["Off", "No dey", "Anọghị"],

  "device.connected": ["SolarDokta Link connected", "SolarDokta Link dey connected", "SolarDokta Link jikọrọ"],
  "device.offline": ["SolarDokta Link not sending", "SolarDokta Link no dey send", "SolarDokta Link anaghị ezite"],
  "device.seen": ["Last reading {n} min ago", "Last reading na {n} min ago", "Ozi ikpeazụ: nkeji {n} gara aga"],
  "device.readings": ["{n} readings today", "{n} readings today", "Ozi {n} taa"],
  "device.via": ["via {how}", "through {how}", "site na {how}"],
  "device.simulated": ["simulated for the demo", "na simulation for demo", "e mere ya maka ngosi"],
  "device.what": ["What is this?", "Wetin be this?", "Gịnị bụ nke a?"],

  "elnino.title": ["Super El Niño season", "Super El Niño season", "Oge El Niño siri ike"],
  "elnino.body": [
    "Nigeria will stay hotter than usual until early 2027. Heat wears batteries out faster and panels make a little less.",
    "Nigeria go dey hot pass normal until early 2027. Heat dey spoil battery quick, and panel go produce small less.",
    "Naịjirịa ga-adị ọkụ karịa ka ọ na-adị ruo mmalite 2027. Okpomọkụ na-eme ka batrị mebie ngwa ngwa, panel anaghịkwa arụpụta nke ọma.",
  ],
  "elnino.link": ["See what the heat is doing to your battery", "See wetin heat dey do your battery", "Hụ ihe okpomọkụ na-eme batrị gị"],

  "home.learnLink": ["New to these words? Learn them with pictures", "You no sabi these words? Learn dem with pictures", "Ị maghị okwu ndị a? Mụta ha site na foto"],
  "home.tonight": ["Tonight and tomorrow", "Tonight and tomorrow", "Abalị a na echi"],

  "usage.title": ["Your power, day by day", "Your power, day by day", "Ọkụ gị, kwa ụbọchị"],
  "usage.pick": ["Pick the days you want to see", "Pick the days you wan see", "Họrọ ụbọchị ị chọrọ ịhụ"],
  "usage.hint": ["One day shows hour by hour. Several days show day by day.", "One day go show hour by hour. Many days go show day by day.", "Otu ụbọchị na-egosi elekere n'elekere. Ọtụtụ ụbọchị na-egosi ụbọchị n'ụbọchị."],
  "usage.today": ["Today", "Today", "Taa"],
  "usage.yesterday": ["Yesterday", "Yesterday", "Ụnyaahụ"],
  "usage.week": ["Last 7 days", "Last 7 days", "Ụbọchị 7 gara aga"],
  "usage.month": ["Last 30 days", "Last 30 days", "Ụbọchị 30 gara aga"],
  "usage.from": ["From", "From", "Site"],
  "usage.to": ["To", "Reach", "Ruo"],
  "usage.inShort": ["In short", "For short", "Na nkenke"],
  "usage.energy": ["Solar made vs home used", "Wetin solar make vs wetin house use", "Ihe anyanwụ mere na ihe ụlọ jiri"],
  "usage.energyHow": [
    "Yellow bars: what your panels made. Dark bars: what your home used. Where the dark bar is taller, the battery or NEPA made up the difference.",
    "Yellow bar: wetin your panels make. Dark bar: wetin your house use. Where dark bar tall pass, na battery or NEPA cover the rest.",
    "Ogwe odo: ihe panel gị mere. Ogwe gbara ọchịchịrị: ihe ụlọ gị jiri. Ebe ogwe ọchịchịrị dị ogologo, batrị ma ọ bụ NEPA kwụrụ ụgwọ ya.",
  ],
  "usage.battery": ["How full the battery was", "How full battery be", "Otú batrị si jupụta"],
  "usage.batteryHow": [
    "The green band shows the lowest and highest battery level. Below 20% means your home was close to a blackout.",
    "Green band show the lowest and highest battery level. Below 20% mean say light almost go for your house.",
    "Akụkụ akwụkwọ ndụ na-egosi ọkwa batrị kacha ala na nke kacha elu. N'okpuru 20% pụtara na ọkụ fọrọ obere ka ọ pụọ.",
  ],
  "usage.light": ["Hours of NEPA light", "Hours of NEPA light", "Awa ọkụ NEPA"],
  "usage.lightHow": ["Each bar is how long NEPA was on.", "Each bar na how long NEPA stay.", "Ogwe ọ bụla bụ ogologo oge NEPA nọrọ."],
  "usage.solar": ["Solar made", "Solar make", "Anyanwụ mere"],
  "usage.used": ["Home used", "House use", "Ụlọ jiri"],
  "usage.fromNepa": ["From NEPA", "From NEPA", "Site na NEPA"],
  "usage.saved": ["Saved by solar", "Solar save", "Anyanwụ chekwara"],
  "usage.light.total": ["NEPA light", "NEPA light", "Ọkụ NEPA"],
  "usage.none": ["No readings for these dates.", "No readings for these days.", "Enweghị ozi maka ụbọchị ndị a."],

  "learn.title": ["Learn your solar system", "Learn your solar system", "Mụta usoro anyanwụ gị"],
  "learn.intro": ["Tap a word to see what it means, what it looks like, and how yours is doing right now.",
                  "Tap any word to see wetin e mean, how e be, and how your own dey now.",
                  "Pịa okwu ka ịhụ ihe ọ pụtara, otu o si dị, na otu nke gị si dị ugbu a."],
  "learn.yours": ["Yours right now", "Your own now", "Nke gị ugbu a"],
  "learn.try": ["Try it", "Try am", "Nwaa ya"],

  "tell.title": ["Tell SolarDokta about your home", "Tell SolarDokta about your house", "Gwa SolarDokta maka ụlọ gị"],
  "tell.intro": ["The more you share, the more your numbers are about your home and not an average one.",
                 "As you share more, your numbers go be about your own house, no be average.",
                 "Ka ị na-ekerịta karịa, ka ọnụọgụ gị na-adabara ụlọ gị."],

  "ask.title": ["Ask Dokta", "Ask Dokta", "Jụọ Dokta"],
  "ask.intro": ["Ask anything about your power. Type it or tap the microphone and talk.",
                "Ask anything about your light. Type am or tap the microphone talk.",
                "Jụọ ihe ọ bụla gbasara ọkụ gị. Dee ya ma ọ bụ pịa igwe okwu ma kwuo."],
  "ask.placeholder": ["Type a question…", "Type your question…", "Dee ajụjụ…"],
  "ask.send": ["Send", "Send", "Ziga"],
  "ask.talk": ["Ask by voice", "Talk am", "Jụọ n'olu"],
  "ask.stop": ["Stop and send", "Stop make e send", "Kwụsị ma ziga"],
  "ask.listening": ["Listening… {s}s", "I dey listen… {s}s", "Ana m ege ntị… {s}s"],
  "ask.thinking": ["Checking your system…", "I dey check your system…", "Ana m enyocha usoro gị…"],
  "ask.heard": ["You said", "You talk", "Ị sịrị"],
  "ask.try": ["Try one of these", "Try one of these", "Nwaa otu n'ime ndị a"],
  "ask.mic": ["Couldn't use the microphone. Allow microphone access, or type your question.",
              "Microphone no work. Allow microphone, or type your question.",
              "Enweghị ike iji igwe okwu. Kwe ka o rụọ ọrụ, ma ọ bụ dee ajụjụ gị."],
  "ask.answersIn": ["Answers in", "Answer for", "Azịza na"],
};

const SUGGESTIONS: Record<Lang, string[]> = {
  en: ["Can I use my pressing iron now?", "Will my battery last till morning?", "How many hours of light did we get this week?", "What is the heat doing to my battery?"],
  pcm: ["I fit iron now?", "Battery go reach morning?", "How light take dey this week?", "Wetin this heat dey do my battery?"],
  ig: ["Enwere m ike ịgba ígwè ugbu a?", "Batrị m ọ ga-eru ụtụtụ?", "Awa ole ka NEPA nyere anyị n'izu a?", "Gịnị ka okpomọkụ na-eme batrị m?"],
};

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (key: string, vars?: Record<string, string | number>) => string; suggestions: string[] };
const LangContext = createContext<Ctx | null>(null);
const KEY = "solardokta-lang";
const IDX: Record<Lang, number> = { en: 0, pcm: 1, ig: 2 };

export function LangProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => {
    try {
      const v = localStorage.getItem(KEY);
      if (v === "en" || v === "pcm" || v === "ig") setLangState(v);
    } catch { /* storage blocked: stay on English */ }
  }, []);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try { localStorage.setItem(KEY, l); } catch { /* not remembered, still works */ }
  }, []);
  const t = useCallback((key: string, vars?: Record<string, string | number>) => {
    let s = WORDS[key]?.[IDX[lang]] ?? WORDS[key]?.[0] ?? key;
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
    return s;
  }, [lang]);
  return <LangContext.Provider value={{ lang, setLang, t, suggestions: SUGGESTIONS[lang] }}>{children}</LangContext.Provider>;
}

export function useLang(): Ctx {
  const c = useContext(LangContext);
  if (!c) throw new Error("useLang must be used inside <LangProvider>");
  return c;
}

export function LangSwitch({ dark = false }: { dark?: boolean }) {
  const { lang, setLang } = useLang();
  return (
    <div role="radiogroup" aria-label="Language" className={`inline-flex rounded-full p-0.5 ${dark ? "bg-white/10" : "bg-sky"}`}>
      {LANGS.map((l) => (
        <button key={l.id} role="radio" aria-checked={lang === l.id} onClick={() => setLang(l.id)} title={l.label}
                className={`rounded-full px-2.5 py-1 text-xs font-semibold ${lang === l.id
                  ? (dark ? "bg-sun text-ink" : "bg-ink text-sky") : (dark ? "text-sky/80 hover:text-sky" : "text-muted hover:text-ink")}`}>
          <span className="sm:hidden">{l.short}</span><span className="hidden sm:inline">{l.label}</span>
        </button>
      ))}
    </div>
  );
}

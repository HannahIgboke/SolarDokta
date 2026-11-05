"use client";
// "Get alerts on this phone": install SolarDokta on the home screen and turn on notifications.
// Replaces WhatsApp alerts: the same problem alerts pop up on the phone, even when the app is closed.
import { useEffect, useState } from "react";
import { useLang } from "@/lib/i18n";
import { isIos, isStandalone, pushState, sendTest, turnOff, turnOn, type PushState } from "@/lib/push";

type InstallPrompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

const T = {
  title: ["Get alerts on this phone", "Make alerts enter your phone", "Nweta ozi na ekwentị a"],
  why: {
    customer: ["We'll tell you when something goes wrong, before the light goes off: dust, a dead panel group, a hot battery, a heatwave tomorrow. Plus a short note at 7 pm about tonight.",
               "We go tell you when something no correct before light go off: dust, panel wey die, battery wey hot, heatwave tomorrow. Plus small message by 7 pm about tonight.",
               "Anyị ga-agwa gị mgbe ihe adịghị mma tupu ọkụ anyụọ: ájá, panel nwụrụ anwụ, batrị na-ekpo ọkụ, okpomọkụ echi. Na obere ozi n'elekere 7 nke abalị."],
    staff: ["Critical faults and customer reports pop up on your phone the moment they're found, with the site and what to bring.",
            "Critical faults and customer reports go show for your phone as dem find am, with the site and wetin to carry.",
            "Critical faults and customer reports pop up on your phone the moment they're found, with the site and what to bring."],
  },
  on: ["Turn on alerts", "Turn on alerts", "Gbanye ozi"],
  isOn: ["Alerts are on for this phone.", "Alerts don on for this phone.", "Ozi agbanyela na ekwentị a."],
  test: ["Send me a test alert", "Send me test alert", "Zitere m ozi ule"],
  sent: ["Sent. It should pop up in a few seconds.", "E don go. E go show in few seconds.", "Ezitela ya. Ọ ga-apụta n'ime sekọnd ole na ole."],
  off: ["Turn off", "Off am", "Gbanyụọ"],
  install: ["Install SolarDokta on this phone", "Put SolarDokta for your phone", "Tinye SolarDokta na ekwentị a"],
  ios: ["On iPhone: tap the Share button, choose 'Add to Home Screen', then open SolarDokta from your home screen and turn on alerts here.",
        "For iPhone: tap Share, choose 'Add to Home Screen', open SolarDokta from your home screen, then on alerts for here.",
        "Na iPhone: pịa Share, họrọ 'Add to Home Screen', mepee SolarDokta site na home screen gị, wee gbanye ozi ebe a."],
  blocked: ["Alerts are blocked for this site in your browser settings. Allow notifications for SolarDokta there, then come back.",
            "Your browser don block alerts for this site. Allow notifications for SolarDokta for browser settings, then come back.",
            "Ihe nchọgharị gị egbochila ozi maka saịtị a. Kwe ka SolarDokta zitere gị ozi na settings, wee lọghachi."],
  unsupported: ["This browser can't show alerts. Try Chrome on Android, or install SolarDokta on an iPhone.",
                "This browser no fit show alerts. Try Chrome for Android, or install SolarDokta for iPhone.",
                "Ihe nchọgharị a enweghị ike igosi ozi. Nwalee Chrome na Android."],
};

export function PhoneAlerts({ role = "customer" }: { role?: "customer" | "staff" }) {
  const { lang } = useLang();
  const i = lang === "pcm" ? 1 : lang === "ig" ? 2 : 0;
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [install, setInstall] = useState<InstallPrompt | null>(null);

  useEffect(() => {
    pushState().then(setState).catch(() => setState("unsupported"));
    const keep = (e: Event) => { e.preventDefault(); setInstall(e as InstallPrompt); };
    window.addEventListener("beforeinstallprompt", keep);
    return () => window.removeEventListener("beforeinstallprompt", keep);
  }, []);

  if (state === null) return null;

  const run = async (fn: () => Promise<PushState | void>, done?: string) => {
    setBusy(true); setNote(null);
    try {
      const next = await fn();
      if (next) setState(next);
      if (done) setNote(done);
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-2xl border border-line bg-white p-5" aria-labelledby="alerts-title">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-sun/20 text-ink" aria-hidden="true">
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0" />
          </svg>
        </span>
        <div className="min-w-0 flex-1">
          <h2 id="alerts-title" className="font-display text-lg font-semibold">{T.title[i]}</h2>
          <p className="mt-1 text-sm text-muted">{T.why[role][i]}</p>

          {state === "ios-install" && <p className="mt-3 rounded-xl bg-sky px-3 py-2 text-sm">{T.ios[i]}</p>}
          {state === "blocked" && <p className="mt-3 rounded-xl bg-sky px-3 py-2 text-sm">{T.blocked[i]}</p>}
          {state === "unsupported" && <p className="mt-3 rounded-xl bg-sky px-3 py-2 text-sm">{T.unsupported[i]}</p>}

          <div className="mt-3 flex flex-wrap gap-2">
            {state === "off" && (
              <button disabled={busy} onClick={() => run(() => turnOn(lang))}
                      className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-sky disabled:opacity-60">{busy ? "…" : T.on[i]}</button>
            )}
            {state === "on" && (
              <>
                <span className="flex items-center gap-1.5 py-2 text-sm font-medium text-charge">
                  <span className="h-2 w-2 rounded-full bg-charge" />{T.isOn[i]}
                </span>
                <button disabled={busy} onClick={() => run(sendTest, T.sent[i])}
                        className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-sky disabled:opacity-60">{T.test[i]}</button>
                <button disabled={busy} onClick={() => run(turnOff)}
                        className="rounded-full border border-line px-4 py-2 text-sm font-medium">{T.off[i]}</button>
              </>
            )}
            {install && !isStandalone() && !isIos() && (
              <button onClick={async () => { await install.prompt(); setInstall(null); }}
                      className="rounded-full border border-ink px-4 py-2 text-sm font-semibold">{T.install[i]}</button>
            )}
          </div>
          {note && <p role="status" className="mt-2 text-sm text-muted">{note}</p>}
        </div>
      </div>
    </section>
  );
}

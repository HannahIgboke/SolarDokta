"use client";
// The public front page: what SolarDokta does, why it matters right now (bad NEPA, El Niño heat),
// and a way in for everyone: try the demo without an account, or sign in.
import Link from "next/link";
import { Logo } from "../Logo";
import { AskExamples } from "./AskExamples";
import { HeatSlider } from "./HeatSlider";
import { HeroScene } from "./HeroScene";
import { HowItWorks } from "./HowItWorks";
import { TechPreview } from "./TechPreview";

const PROBLEMS = [
  { icon: "bulb", title: "Light is worse than it has been in years",
    body: "Since mid-October many homes in Lagos and Port Harcourt get only a few hours of NEPA a day. Batteries are working harder than they were sized for." },
  { icon: "panel", title: "Half your panels can stop and you won't notice",
    body: "The lights still come on, just for fewer hours. Most people find out months later, after paying for fuel the whole time." },
  { icon: "heat", title: "Heat is quietly ageing batteries",
    body: "This El Niño season is hotter than usual. A battery in a hot room can wear out years early, and a new one costs hundreds of thousands of naira." },
  { icon: "fuel", title: "Every weak day ends at the generator",
    body: "When solar underperforms, the difference comes from petrol or diesel. Nobody tells you it's happening, so nobody fixes it." },
];

const FOR_YOU = [
  { title: "“Can I use it now?”", body: "Iron, pumping machine, AC, freezer: a yes or no, with the reason." },
  { title: "Tonight, in plain words", body: "Whether your battery will last until morning, and what to switch off if not." },
  { title: "Problems explained with pictures", body: "What a panel group, inverter or battery is, and what went wrong, without jargon." },
  { title: "What you've saved", body: "Naira not spent on fuel and NEPA, from your own receipts." },
  { title: "A battery health report", body: "Printable proof of your battery's condition for a warranty claim or when you sell." },
  { title: "English, Pidgin or Igbo", body: "Type or send a voice note, on the web or WhatsApp." },
];

function Icon({ name }: { name: string }) {
  const p = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" className="h-7 w-7" aria-hidden="true">
      {name === "bulb" && <><path {...p} d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3Z" /><path {...p} d="m4 4 16 16" /></>}
      {name === "panel" && <><path {...p} d="M3 18 6 6h15l-3 12Z" /><path {...p} d="M4.5 12h15M10.5 6l-2 12M15.5 6l-2 12" /></>}
      {name === "heat" && <><path {...p} d="M10 14.5V5a2 2 0 1 1 4 0v9.5a4 4 0 1 1-4 0Z" /><path {...p} d="M12 9v7" /></>}
      {name === "fuel" && <><path {...p} d="M4 21V5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v16M3 21h13M15 9h2a2 2 0 0 1 2 2v6a1.5 1.5 0 0 0 3 0V8l-3-3" /><path {...p} d="M7 8h5" /></>}
    </svg>
  );
}

function DemoButtons({ dark = false }: { dark?: boolean }) {
  return (
    <div className="flex flex-wrap gap-3">
      <Link href="/demo/customer"
            className="rounded-full bg-sun px-6 py-3 font-semibold text-ink shadow-[0_6px_0_#b88a00] transition-transform hover:-translate-y-0.5 active:translate-y-0.5 active:shadow-[0_3px_0_#b88a00]">
        See a customer&apos;s view
      </Link>
      <Link href="/demo/technician"
            className={`rounded-full border-2 px-6 py-3 font-semibold ${dark ? "border-white/40 text-white hover:bg-white/10" : "border-ink text-ink hover:bg-ink hover:text-sky"}`}>
        See a technician&apos;s view
      </Link>
    </div>
  );
}

export function Landing() {
  return (
    <div className="bg-sky">
      {/* hero */}
      <div className="bg-[#0d1830] text-white">
        <header className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-5 sm:px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <Logo className="h-9 w-9" />
            <span className="font-display text-xl font-semibold">SolarDokta</span>
          </Link>
          <nav className="flex items-center gap-1 text-sm sm:gap-2">
            <a href="#how" className="hidden rounded-full px-3 py-2 hover:bg-white/10 md:block">How it works</a>
            <a href="#el-nino" className="hidden rounded-full px-3 py-2 hover:bg-white/10 md:block">El Niño</a>
            <a href="#installers" className="hidden rounded-full px-3 py-2 hover:bg-white/10 md:block">For installers</a>
            <Link href="/login" className="rounded-full border border-white/30 px-4 py-2 font-medium hover:bg-white/10">Sign in</Link>
          </nav>
        </header>

        <section className="mx-auto max-w-6xl px-4 pt-8 pb-14 sm:px-6 sm:pt-14">
          <h1 className="max-w-4xl font-display text-[2.6rem] leading-[1.02] font-bold tracking-[-0.02em] sm:text-6xl lg:text-[5.2rem]">
            Your solar system,<br />finally talking to you.
          </h1>
          <p className="mt-6 max-w-2xl text-lg text-white/80 sm:text-xl">
            SolarDokta watches your panels, battery and inverter every 5 minutes, warns you before
            something breaks, and tells you in plain words whether you can run the iron tonight.
          </p>
          <div className="mt-8"><DemoButtons dark /></div>
          <p className="mt-3 text-sm text-white/60">No account needed. The demo is a simulated home in Lagos, updating live.</p>
          <div className="mt-12"><HeroScene /></div>
        </section>
      </div>

      {/* the problem */}
      <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <h2 className="max-w-3xl font-display text-4xl leading-tight font-bold sm:text-5xl">
          In Nigeria, solar doesn&apos;t fail loudly. It fails quietly.
        </h2>
        <div className="mt-12 grid gap-x-12 gap-y-10 md:grid-cols-2">
          {PROBLEMS.map((p) => (
            <div key={p.title} className="flex gap-4">
              <span className="mt-1 text-warn"><Icon name={p.icon} /></span>
              <div>
                <h3 className="font-display text-xl font-semibold">{p.title}</h3>
                <p className="mt-2 max-w-md text-muted">{p.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* how it works */}
      <section id="how" className="scroll-mt-6 bg-[#e3e9ef] py-20">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <h2 className="max-w-3xl font-display text-4xl leading-tight font-bold sm:text-5xl">How it works</h2>
          <p className="mt-4 max-w-2xl text-lg text-muted">One small box on the inverter. Everything else happens on your phone.</p>
          <div className="mt-12"><HowItWorks /></div>
        </div>
      </section>

      {/* ask in your language */}
      <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <h2 className="max-w-3xl font-display text-4xl leading-tight font-bold sm:text-5xl">Ask it anything about your power. In your language.</h2>
        <p className="mt-4 max-w-2xl text-lg text-muted">Pick a question to see the kind of answer you get.</p>
        <div className="mt-10"><AskExamples /></div>
        <div className="mt-16 grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
          {FOR_YOU.map((f) => (
            <div key={f.title} className="border-t-2 border-ink pt-4">
              <h3 className="font-display text-lg font-semibold">{f.title}</h3>
              <p className="mt-1 text-muted">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* El Niño */}
      <section id="el-nino" className="scroll-mt-6 bg-gradient-to-br from-[#b4400f] via-[#8a2f12] to-[#2a1430] py-20 text-white">
        <div className="mx-auto grid max-w-6xl gap-12 px-4 sm:px-6 lg:grid-cols-[1fr_1.15fr] lg:items-center">
          <div>
            <h2 className="font-display text-4xl leading-tight font-bold sm:text-5xl">This is a super El Niño season. Your battery feels it.</h2>
            <p className="mt-5 text-lg text-white/85">
              Weather agencies (WMO and NiMet) expect a strong El Niño to keep Nigeria hotter than usual until early 2027.
              Heat makes batteries age faster and panels produce less, exactly when NEPA is at its worst.
            </p>
            <p className="mt-4 text-lg text-white/85">
              SolarDokta measures your battery&apos;s temperature every 5 minutes, warns you the day before a heatwave,
              and shows how much extra wear the heat is costing you.
            </p>
          </div>
          <HeatSlider />
        </div>
      </section>

      {/* installers */}
      <section id="installers" className="scroll-mt-6 mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <div className="grid gap-12 lg:grid-cols-[1fr_1fr] lg:items-center">
          <div>
            <h2 className="font-display text-4xl leading-tight font-bold sm:text-5xl">For installers: every site you look after, on one screen.</h2>
            <ul className="mt-8 space-y-5 text-lg">
              <li><strong>Worst first.</strong> <span className="text-muted">A map and a list of your sites, sorted by what needs a visit today.</span></li>
              <li><strong>The exact fault.</strong> <span className="text-muted">Which panel group died, whose battery is fading, which room is too hot, before the customer calls.</span></li>
              <li><strong>What-if tests.</strong> <span className="text-muted">See how a site would cope with 2 hours of NEPA, a 38°C week or a new freezer, without touching it.</span></li>
              <li><strong>Proof for warranty.</strong> <span className="text-muted">Battery health measured from real readings, not guesses.</span></li>
            </ul>
            <div className="mt-8">
              <Link href="/demo/technician" className="inline-block rounded-full bg-ink px-6 py-3 font-semibold text-sky hover:bg-[#22355c]">
                See a technician&apos;s view
              </Link>
            </div>
          </div>
          <TechPreview />
        </div>
      </section>

      {/* final call */}
      <section className="bg-[#0d1830] py-20 text-white">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <h2 className="max-w-3xl font-display text-4xl leading-tight font-bold sm:text-5xl">See it working on a real day in Lagos.</h2>
          <p className="mt-4 max-w-2xl text-lg text-white/80">
            The demo home has bad NEPA, a dead panel group and a hot battery room, just like many homes this season.
          </p>
          <div className="mt-8"><DemoButtons dark /></div>
        </div>
      </section>

      <footer className="bg-[#0a1326] py-8 text-sm text-white/60">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 sm:px-6">
          <span className="flex items-center gap-2"><Logo className="h-6 w-6" /> SolarDokta, Lagos 2026</span>
          <Link href="/login" className="underline">Customer or installer? Sign in</Link>
        </div>
      </footer>
    </div>
  );
}

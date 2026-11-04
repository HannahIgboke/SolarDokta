"use client";
// The bar at the top of every signed-in (or demo) page: logo on the left, one round button with
// the person's initials on the right. Language, their name and role, and sign-out live in the
// menu that button opens, so the bar stays clean.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Logo } from "./Logo";
import { LANGS, useLang } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import type { Me } from "@/lib/api";

function DemoBar({ me }: { me: Me }) {
  const { exitDemo } = useSession();
  const router = useRouter();
  const other = me.role === "staff" ? { href: "/demo/customer", label: "See the customer's view" }
    : { href: "/demo/technician", label: "See the technician's view" };
  return (
    <div className="bg-sun text-ink">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-2 text-sm">
        <p><strong>Demo:</strong> a simulated {me.role === "staff" ? "installer's sites" : "home in Lagos"}, live every 5 minutes. Look around freely; nothing can be changed.</p>
        <div className="flex gap-3">
          <Link href={other.href} className="font-semibold underline">{other.label}</Link>
          <button onClick={() => { exitDemo(); router.push("/"); }} className="font-semibold underline">Leave demo</button>
        </div>
      </div>
    </div>
  );
}

function UserMenu({ me }: { me: Me }) {
  const { signOut, exitDemo } = useSession();
  const { lang, setLang } = useLang();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const name = me.full_name ?? (me.role === "staff" ? "Technician" : "Customer");
  const initials = name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);

  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="menu" aria-label={`Account menu for ${name}`}
              className="flex items-center gap-2 rounded-full py-1 pr-2 pl-1 hover:bg-white/10">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-sun font-display text-sm font-bold text-ink">{initials}</span>
        {me.role === "customer" && <span className="hidden rounded-full bg-white/10 px-2 py-0.5 text-xs font-semibold sm:inline">{LANGS.find((l) => l.id === lang)?.short}</span>}
        <svg viewBox="0 0 12 12" className="h-3 w-3 text-sky/70" aria-hidden="true"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.8" /></svg>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-50 mt-2 w-64 overflow-hidden rounded-2xl bg-white text-ink shadow-xl ring-1 ring-line">
          <div className="border-b border-line px-4 py-3">
            <p className="font-semibold">{name}</p>
            <p className="text-sm text-muted">{me.role === "staff" ? "Technician" : "Customer"}{me.demo ? " (demo)" : ""}</p>
          </div>
          {me.role === "customer" && (
            <div className="border-b border-line px-4 py-3">
              <p className="mb-2 text-xs font-semibold text-muted">Language</p>
              <div className="grid grid-cols-3 gap-1">
                {LANGS.map((l) => (
                  <button key={l.id} role="menuitemradio" aria-checked={lang === l.id} onClick={() => setLang(l.id)}
                          className={`rounded-lg px-2 py-1.5 text-sm font-medium ${lang === l.id ? "bg-ink text-sky" : "bg-sky hover:bg-line"}`}>{l.label}</button>
                ))}
              </div>
            </div>
          )}
          <button role="menuitem" onClick={() => { setOpen(false); if (me.demo) { exitDemo(); router.push("/"); } else signOut(); }}
                  className="block w-full px-4 py-3 text-left text-sm font-medium hover:bg-sky">
            {me.demo ? "Leave the demo" : "Sign out"}
          </button>
        </div>
      )}
    </div>
  );
}

export function AppShell({ me, children, wide = false }: { me: Me; children: React.ReactNode; wide?: boolean }) {
  const width = wide ? "max-w-7xl" : "max-w-6xl";
  return (
    <div className="min-h-screen">
      {me.demo && <DemoBar me={me} />}
      <header className="bg-ink text-sky">
        <div className={`mx-auto flex ${width} items-center justify-between gap-4 px-4 py-2.5`}>
          <Link href={me.role === "staff" ? "/staff" : "/my"} className="flex items-center gap-2">
            <Logo className="h-7 w-7" />
            <span className="font-display text-lg font-semibold">SolarDokta</span>
            {me.role === "staff" && <span className="ml-1 hidden rounded-full bg-white/10 px-2 py-0.5 text-xs sm:inline">for installers</span>}
          </Link>
          <UserMenu me={me} />
        </div>
      </header>
      <main className={`mx-auto ${width} px-4 py-6`}>{children}</main>
    </div>
  );
}

"use client";
// Sign in for customers and technicians who have an account. Everyone else can try the demo.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { homeFor } from "@/components/Guard";
import { Logo } from "@/components/Logo";
import { useSession } from "@/lib/session";
import { supabase } from "@/lib/supabase";

export default function LoginPage() {
  const { me, session, error: accountError } = useSession();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (me && session) router.replace(homeFor(me));
  }, [me, session, router]);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) setError(error.message === "Invalid login credentials" ? "Wrong email or password." : error.message);
    setBusy(false);
  }

  return (
    <div className="grid min-h-screen place-items-center bg-[#0d1830] px-4 py-10">
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2.5 text-white">
          <Logo className="h-10 w-10" />
          <span className="font-display text-2xl font-semibold">SolarDokta</span>
        </Link>
        <form onSubmit={signIn} className="rounded-3xl bg-white p-7 shadow-xl">
          <h1 className="font-display text-2xl font-semibold">Sign in</h1>
          <p className="mt-1 text-sm text-muted">For customers and installers with a SolarDokta account.</p>
          <label className="mt-6 block text-sm font-medium" htmlFor="email">Email</label>
          <input id="email" type="email" required autoComplete="email" value={email}
                 onChange={(e) => setEmail(e.target.value)}
                 className="mt-1 w-full rounded-xl border border-line bg-sky/50 px-3 py-2.5" />
          <label className="mt-4 block text-sm font-medium" htmlFor="password">Password</label>
          <input id="password" type="password" required autoComplete="current-password" value={password}
                 onChange={(e) => setPassword(e.target.value)}
                 className="mt-1 w-full rounded-xl border border-line bg-sky/50 px-3 py-2.5" />
          {(error || accountError) && (
            <p role="alert" className="mt-4 text-sm text-alarm">{error ?? accountError}</p>
          )}
          <button type="submit" disabled={busy}
                  className="mt-6 w-full rounded-xl bg-ink px-4 py-3 font-semibold text-sky disabled:opacity-60">
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-white/70">
          No account? <Link href="/demo/customer" className="font-semibold text-sun underline">Try the demo</Link>
          {" "}or <Link href="/" className="underline">see what SolarDokta does</Link>.
        </p>
      </div>
    </div>
  );
}

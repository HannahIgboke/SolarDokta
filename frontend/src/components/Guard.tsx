"use client";
// Shows a page only to signed-in people (or demo visitors) with the right role; sends everyone
// else where they belong.
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useSession } from "@/lib/session";
import type { Me } from "@/lib/api";

export function homeFor(me: Me | null): string {
  if (!me) return "/login";
  return me.role === "staff" ? "/staff" : "/my";
}

export function Guard({ role, children }: { role: Me["role"]; children: (me: Me) => React.ReactNode }) {
  const { loading, session, demo, me, error, signOut } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!session && !demo) router.replace("/");
    else if (me && me.role !== role) router.replace(homeFor(me));
  }, [loading, session, demo, me, role, router]);

  if (error) {
    return (
      <div className="mx-auto max-w-md p-8">
        <p className="font-medium text-alarm">{error}</p>
        <button onClick={signOut} className="mt-4 rounded-md border border-line bg-card px-4 py-2">
          {demo ? "Leave the demo" : "Sign out"}
        </button>
      </div>
    );
  }
  if (loading || !me || me.role !== role) {
    return <p className="p-8 text-muted">Loading…</p>;
  }
  return <>{children(me)}</>;
}

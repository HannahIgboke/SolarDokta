"use client";
// The front door. Signed-in customers and technicians go straight to their own dashboard;
// everyone else sees what SolarDokta is, and can try the demo without an account.
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { homeFor } from "@/components/Guard";
import { Landing } from "@/components/landing/Landing";
import { useSession } from "@/lib/session";

export default function Home() {
  const { loading, session, me } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (!loading && session && me) router.replace(homeFor(me));
  }, [loading, session, me, router]);
  return <Landing />;
}

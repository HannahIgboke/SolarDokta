"use client";
// /demo/customer and /demo/technician: open the demo site without logging in.
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useSession } from "@/lib/session";

export default function DemoPage() {
  const { role } = useParams<{ role: string }>();
  const { startDemo } = useSession();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const r = role === "technician" || role === "staff" ? "staff" : "customer";
    startDemo(r).then((me) => {
      if (me) router.replace(r === "staff" ? "/staff" : "/my");
      else setError("The demo couldn't open. Is the SolarDokta server running?");
    });
  }, [role, startDemo, router]);

  return (
    <div className="grid min-h-screen place-items-center bg-ink text-sky">
      <p className={error ? "text-[#ffb4a8]" : "animate-pulse"}>{error ?? "Opening the demo…"}</p>
    </div>
  );
}

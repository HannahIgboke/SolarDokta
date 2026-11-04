"use client";
// Everything a customer sees about one solar system.
import Link from "next/link";
import type { Me } from "@/lib/api";
import type { Live } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Failed, Loading } from "../Section";
import { BatteryHealth } from "./BatteryHealth";
import { CanIUse } from "./CanIUse";
import { ChatDrawer } from "./ChatDrawer";
import { HeatWatch } from "./HeatWatch";
import { LightTracker } from "./LightTracker";
import { LiveSystem } from "./LiveSystem";
import { Money } from "./Money";
import { Problems } from "./Problems";
import { StatusHeader } from "./StatusHeader";
import { TodayChart } from "./TodayChart";
import { TonightTomorrow } from "./TonightTomorrow";
import { YourInputs } from "./YourInputs";

export function CustomerDashboard({ me, code }: { me: Me; code: string }) {
  const { data: live, error, loading, reload } = useApi<Live>(`/api/sites/${code}/views/live`, 60_000);

  if (loading && !live) return <Loading what="your system" />;
  if (error && !live) return <Failed message={error} />;
  if (!live || live.error) return <Failed message={live?.error ?? "No data from this system yet."} />;

  return (
    <div className="space-y-5 pb-20">
      <StatusHeader name={me.full_name} live={live} />

      <div className="grid gap-5 lg:grid-cols-[1.65fr_1fr]">
        <LiveSystem code={code} live={live} />
        <div className="space-y-5">
          <CanIUse code={code} appliances={live.appliances} />
          <Problems code={code} />
        </div>
      </div>

      <TodayChart code={code} />

      <div className="grid gap-5 lg:grid-cols-2">
        <LightTracker code={code} />
        <HeatWatch code={code} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <TonightTomorrow code={code} />
        <Money code={code} />
        <div className="space-y-2">
          <BatteryHealth code={code} />
          <Link href={`/report/${code}`} className="inline-block text-sm font-medium underline">
            Print a battery health report (for warranty or resale)
          </Link>
        </div>
      </div>

      <YourInputs code={code} onSaved={reload} />

      <ChatDrawer code={code} />
    </div>
  );
}

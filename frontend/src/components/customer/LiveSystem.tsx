"use client";
// The live picture plus the details of whichever part was tapped (with the customer's own photo
// of that part, if they uploaded one).
import { useState } from "react";
import type { Live, Upload } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Twin, type Part } from "../twin/Twin";
import { PartDetails } from "./PartDetails";

const PHOTO_FOR: Record<string, string> = {
  battery: "battery", inverter: "inverter", "string-1": "panels", "string-2": "panels", home: "appliance",
};

export function LiveSystem({ code, live }: { code: string; live: Live }) {
  const [part, setPart] = useState<Part | null>(null);
  const { data } = useApi<{ uploads: Upload[] }>(`/api/sites/${code}/uploads`);
  const photo = part && data?.uploads.find((u) => u.kind === "photo" && u.url && u.component === PHOTO_FOR[part])?.url;
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-card">
      <div className="overflow-x-auto">
        <div className="min-w-[600px]">
          <Twin live={live} selected={part} onSelect={(p) => setPart(p === part ? null : p)} />
        </div>
      </div>
      <div className="border-t border-line p-4">
        {part ? (
          <div className="flex flex-col gap-4 sm:flex-row">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {photo && <img src={photo} alt={`Your ${PHOTO_FOR[part]}`} className="h-36 w-full rounded-lg object-cover sm:w-48" />}
            <div className="flex-1"><PartDetails part={part} live={live} /></div>
          </div>
        ) : (
          <p className="text-sm text-muted">
            Tap any part of the picture (panels, battery, inverter, NEPA or the appliances) to see its details.
            {live.appliances_source === "yours" ? " The appliances are from your own list." : ""}
            <span className="sm:hidden"> Swipe sideways to see all of it.</span>
          </p>
        )}
      </div>
    </div>
  );
}

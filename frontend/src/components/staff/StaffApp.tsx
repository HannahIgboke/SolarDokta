"use client";
// The technician's app, in tabs: Overview, Map, Sites, Problems, What-if lab, Ask Dokta.
import { useEffect, useState } from "react";
import type { Me } from "@/lib/api";
import type { Fleet } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { TabBar, useHashTab } from "../TabBar";
import { Failed, Loading } from "../Section";
import { FleetAsk } from "./FleetAsk";
import { FleetMapTab, FleetOverview, FleetTable, urgency } from "./Fleet";
import type { MapLayer } from "./fleetColours";
import { ProblemsInbox } from "./ProblemsInbox";
import { WhatIf } from "./WhatIf";

const IDS = ["overview", "map", "sites", "problems", "whatif", "ask"];

export function StaffApp({ me }: { me: Me }) {
  const { data, error, loading } = useApi<Fleet>("/api/fleet", 60_000);
  const { tab, extra, setTab } = useHashTab(IDS, "overview");
  const [layer, setLayer] = useState<MapLayer>("problems");
  const [whatSite, setWhatSite] = useState<string | null>(null);
  useEffect(() => {
    if (tab === "map" && extra && ["problems", "heat", "light"].includes(extra)) setLayer(extra as MapLayer);
  }, [tab, extra]);

  if (loading && !data) return <Loading what="your sites" />;
  if (error && !data) return <Failed message={error} />;
  if (!data) return null;
  const open = data.totals.critical + data.totals.warning;
  const site = whatSite ?? [...data.sites].sort((a, b) => urgency(a) - urgency(b))[0]?.code;

  return (
    <div className="pb-10">
      <TabBar label="Technician sections" active={tab} onChange={setTab} tabs={[
        { id: "overview", label: "Overview" }, { id: "map", label: "Map" }, { id: "sites", label: "Sites" },
        { id: "problems", label: "Problems", badge: open }, { id: "whatif", label: "What-if lab" }, { id: "ask", label: "Ask Dokta" },
      ]} />
      {tab === "overview" && <FleetOverview data={data} name={me.full_name} onTab={setTab} />}
      {tab === "map" && <FleetMapTab data={data} layer={layer} setLayer={setLayer} />}
      {tab === "sites" && <FleetTable data={data} />}
      {tab === "problems" && (
        <div>
          <h1 className="mb-1 font-display text-3xl font-semibold">Problems inbox</h1>
          <p className="mb-4 text-muted">Every finding across your sites, worst first. Resolve or dismiss with a note so the customer&apos;s view updates.</p>
          <ProblemsInbox />
        </div>
      )}
      {tab === "whatif" && site && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="font-display text-3xl font-semibold">What-if lab</h1>
              <p className="text-muted">Stress-test a site against NEPA collapse, El Niño heat, dust, a dead string or new loads. Simulation only.</p>
            </div>
            <label className="text-sm">Site<br />
              <select value={site} onChange={(e) => setWhatSite(e.target.value)} className="mt-1 rounded-full border border-line bg-white px-4 py-2">
                {data.sites.map((s) => <option key={s.code} value={s.code}>{s.name} ({s.code})</option>)}
              </select>
            </label>
          </div>
          <WhatIf key={site} code={site} />
        </div>
      )}
      {tab === "ask" && <FleetAsk />}
    </div>
  );
}

"use client";
// Map of every site. The technician picks what the pins show: problems, battery heat
// (El Niño risk) or hours of NEPA. Urgent sites pulse. Tiles: OpenStreetMap (free, no key),
// softened with CSS so the coloured pins stand out. Sites very close together are fanned out.
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import Link from "next/link";
import { useEffect } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import type { FleetSite } from "@/lib/types";
import { pinColour, type MapLayer } from "./fleetColours";

function pinLabel(s: FleetSite, layer: MapLayer): string {
  if (layer === "heat") return s.heat.battery_avg_c !== null ? `${Math.round(s.heat.battery_avg_c)}°` : "–";
  if (layer === "light") return s.light_hours_7d !== null ? `${s.light_hours_7d}h` : "–";
  return s.battery !== undefined ? `${s.battery}%` : "off";
}

function icon(s: FleetSite, layer: MapLayer) {
  const urgent = s.online && ((layer === "problems" && s.worst === "critical") || (layer === "heat" && s.heat.risk === "high"));
  const c = pinColour(s, layer);
  return L.divIcon({
    className: "",
    iconSize: [54, 54],
    iconAnchor: [27, 27],
    html: `<div class="sd-pin ${urgent ? "sd-pin-urgent" : ""}" style="--c:${c}"><span>${pinLabel(s, layer)}</span></div>`,
  });
}

// Pins for sites closer than ~1.5 km would sit on top of each other: spread them in a small circle.
function spread(sites: FleetSite[]): Record<string, [number, number]> {
  const out: Record<string, [number, number]> = {};
  const groups: FleetSite[][] = [];
  for (const s of sites) {
    const g = groups.find((x) => Math.abs(x[0].latitude - s.latitude) < 0.015 && Math.abs(x[0].longitude - s.longitude) < 0.015);
    if (g) g.push(s); else groups.push([s]);
  }
  for (const g of groups) {
    g.forEach((s, i) => {
      if (g.length === 1) { out[s.code] = [s.latitude, s.longitude]; return; }
      const a = (2 * Math.PI * i) / g.length;
      out[s.code] = [g[0].latitude + 0.012 * Math.sin(a), g[0].longitude + 0.012 * Math.cos(a)];
    });
  }
  return out;
}

function Fit({ sites }: { sites: FleetSite[] }) {
  const map = useMap();
  useEffect(() => {
    if (sites.length > 1) map.fitBounds(sites.map((s) => [s.latitude, s.longitude]) as [number, number][], { padding: [60, 60], maxZoom: 12 });
    else if (sites.length === 1) map.setView([sites[0].latitude, sites[0].longitude], 11);
  }, [sites, map]);
  return null;
}

export default function FleetMap({ sites, layer }: { sites: FleetSite[]; layer: MapLayer }) {
  const pos = spread(sites);
  return (
    <MapContainer center={[6.0, 5.0]} zoom={6} scrollWheelZoom={false} className="h-full min-h-[380px] w-full" aria-label="Map of sites">
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                 url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" className="sd-tiles" />
      <Fit sites={sites} />
      {sites.map((s) => (
        <Marker key={s.code} position={pos[s.code]} icon={icon(s, layer)} title={s.name}>
          <Popup>
            <div className="min-w-[200px] font-sans">
              <p className="font-display text-base font-semibold">{s.name}</p>
              <p className="text-xs text-muted">{s.code}, {s.city}</p>
              <ul className="mt-2 space-y-0.5 text-sm">
                <li>{s.online ? `Battery ${s.battery}%, solar ${((s.solar_w ?? 0) / 1000).toFixed(1)} kW` : "Device offline"}</li>
                <li>{s.problems.length ? s.problems.map((p) => p.replaceAll("_", " ")).join(", ") : "No open problems"}</li>
                <li>Battery room avg {s.heat.battery_avg_c ?? "–"}°C, ageing {s.heat.ageing_speed ?? "–"}×</li>
                <li>NEPA {s.light_hours_7d ?? "–"} h/day, {s.blackouts_7d.hours} h blackout this week</li>
              </ul>
              <Link href={`/staff/sites/${s.code}`} className="mt-2 inline-block font-semibold">Open site</Link>
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}

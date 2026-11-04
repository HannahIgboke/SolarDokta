// What colour a site gets on the map and in the lists, for each map layer.
import type { FleetSite } from "@/lib/types";

export type MapLayer = "problems" | "heat" | "light";

export function pinColour(s: FleetSite, layer: MapLayer): string {
  if (!s.online) return "#8a96a8";
  if (layer === "heat") return s.heat.risk === "high" ? "#d9480f" : s.heat.risk === "medium" ? "#f59f00" : "#1e9e6a";
  if (layer === "light") {
    const h = s.light_hours_7d ?? 24;
    return h < 4 ? "#c93636" : h < 8 ? "#f59f00" : "#4c6ef5";
  }
  return s.worst === "critical" ? "#c93636" : s.worst === "warning" ? "#e8890c" : s.worst === "info" ? "#4c6ef5" : "#1e9e6a";
}


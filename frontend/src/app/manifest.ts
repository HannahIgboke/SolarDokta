import type { MetadataRoute } from "next";

// Lets people install SolarDokta on their phone's home screen, where it opens like an app.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "SolarDokta",
    short_name: "SolarDokta",
    description: "Your solar system, finally talking to you: live status, alerts and advice.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0d1830",
    theme_color: "#0d1830",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}

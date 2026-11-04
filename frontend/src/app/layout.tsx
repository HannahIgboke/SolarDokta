import type { Metadata, Viewport } from "next";
// Fonts are installed with npm and served by our own app (no request to Google Fonts).
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/instrument-sans";
import { LangProvider } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";
import "./globals.css";

export const metadata: Metadata = {
  title: "SolarDokta",
  description: "Health checks, alerts and advice for solar systems in Lagos and Port Harcourt",
};

export const viewport: Viewport = {
  themeColor: "#0d1830",            // the phone's browser bar matches the app's dark blue
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <SessionProvider><LangProvider>{children}</LangProvider></SessionProvider>
      </body>
    </html>
  );
}

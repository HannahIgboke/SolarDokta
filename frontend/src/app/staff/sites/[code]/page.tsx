"use client";
// One site, technician view.
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Guard } from "@/components/Guard";
import { SiteDetail } from "@/components/staff/SiteDetail";

export default function SitePage() {
  const { code } = useParams<{ code: string }>();
  return (
    <Guard role="staff">
      {(me) => {
        const site = me.sites.find((s) => s.code === code);
        return (
          <AppShell me={me} wide>
            {site ? <SiteDetail key={code} code={code} name={site.name} />
              : <p className="text-muted">No site called {code} in your organisation.</p>}
          </AppShell>
        );
      }}
    </Guard>
  );
}

"use client";
// Customer dashboard. A customer with more than one system can switch between them.
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { CustomerApp } from "@/components/customer/CustomerApp";
import { Guard } from "@/components/Guard";

export default function MyPage() {
  const [chosen, setChosen] = useState<string | null>(null);
  return (
    <Guard role="customer">
      {(me) => {
        const code = chosen ?? me.sites[0]?.code;
        return (
          <AppShell me={me}>
            {me.sites.length > 1 && (
              <label className="mb-4 flex items-center gap-2 text-sm">
                System
                <select value={code} onChange={(e) => setChosen(e.target.value)}
                        className="rounded-md border border-line bg-card px-2 py-1">
                  {me.sites.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                </select>
              </label>
            )}
            {code ? <CustomerApp key={code} me={me} code={code} />
              : <p className="text-muted">No system is linked to your account yet. Ask your installer to link it.</p>}
          </AppShell>
        );
      }}
    </Guard>
  );
}

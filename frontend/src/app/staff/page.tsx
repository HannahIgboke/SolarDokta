"use client";
// Technician home: the fleet in tabs.
import { AppShell } from "@/components/AppShell";
import { Guard } from "@/components/Guard";
import { StaffApp } from "@/components/staff/StaffApp";

export default function StaffPage() {
  return (
    <Guard role="staff">
      {(me) => (
        <AppShell me={me} wide>
          <StaffApp me={me} />
        </AppShell>
      )}
    </Guard>
  );
}

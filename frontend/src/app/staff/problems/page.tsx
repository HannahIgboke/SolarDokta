"use client";
// Old address for the problems inbox: it is now a tab on the technician home.
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function ProblemsPage() {
  const router = useRouter();
  useEffect(() => { router.replace("/staff#problems"); }, [router]);
  return <p className="p-8 text-muted">Opening the problems inbox…</p>;
}

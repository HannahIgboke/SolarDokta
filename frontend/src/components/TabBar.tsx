"use client";
// A row of tabs that sticks under the top bar; scrolls sideways on a phone if there are many.
// The chosen tab is kept in the address (#tab) so Back and refresh keep your place.
import { useCallback, useEffect, useState } from "react";

export type TabDef = { id: string; label: string; icon?: React.ReactNode; badge?: number };

export function useHashTab(ids: string[], first: string) {
  const [tab, setTabState] = useState(first);
  const [extra, setExtra] = useState<string | undefined>();
  useEffect(() => {
    const [h, x] = window.location.hash.slice(1).split(":");
    if (ids.includes(h)) { setTabState(h); setExtra(x); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const setTab = useCallback((value: string) => {
    const [id, x] = value.split(":");
    setTabState(id);
    setExtra(x);
    history.replaceState(null, "", `#${id}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);
  return { tab, extra, setTab };
}

export function TabBar({ tabs, active, onChange, label }: { tabs: TabDef[]; active: string; onChange: (id: string) => void; label: string }) {
  return (
    <nav aria-label={label} className="sticky top-0 z-20 -mx-4 mb-6 overflow-x-auto bg-sky/90 px-4 py-3 backdrop-blur">
      <div className="flex w-max gap-1.5">
        {tabs.map((t) => (
          <button key={t.id} onClick={() => onChange(t.id)} aria-current={active === t.id ? "page" : undefined}
                  className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold whitespace-nowrap ${active === t.id ? "bg-ink text-sky" : "text-muted hover:bg-white hover:text-ink"}`}>
            {t.icon}{t.label}
            {t.badge ? <span className={`rounded-full px-1.5 text-xs ${active === t.id ? "bg-sun text-ink" : "bg-alarm text-white"}`}>{t.badge}</span> : null}
          </button>
        ))}
      </div>
    </nav>
  );
}

"use client";
// Who is using SolarDokta, shared by every page: the Supabase session plus the SolarDokta profile
// (role and sites) from the backend's /api/me. Visitors on the public demo have no session:
// `demo` says which view they chose, and the backend gives them the demo site read-only.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { api, ApiError, demoRole, setDemoRole, type DemoRole, type Me } from "./api";
import { supabase } from "./supabase";

type SessionState = {
  loading: boolean;
  session: Session | null;
  demo: DemoRole | null;
  me: Me | null;
  error: string | null;
  signOut: () => Promise<void>;
  startDemo: (role: DemoRole) => Promise<Me | null>;
  exitDemo: () => void;
};

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [demo, setDemo] = useState<DemoRole | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMe = useCallback(async (s: Session | null, d: DemoRole | null): Promise<Me | null> => {
    setSession(s);
    setDemo(d);
    setError(null);
    if (!s && !d) {
      setMe(null);
      setLoading(false);
      return null;
    }
    try {
      const m = await api<Me>("/api/me");
      setMe(m);
      return m;
    } catch (e) {
      setMe(null);
      setError(e instanceof ApiError ? e.message : "Couldn't load your account");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) setDemoRole(null);               // a real login always wins over the demo
      loadMe(data.session, data.session ? null : demoRole());
    });
    const { data } = supabase.auth.onAuthStateChange((event, s) => {
      if (event === "SIGNED_IN") {
        setDemoRole(null);
        loadMe(s, null);
      } else if (event === "SIGNED_OUT") loadMe(null, demoRole());
      else setSession(s); // token refreshed: keep the profile we already have
    });
    return () => data.subscription.unsubscribe();
  }, [loadMe]);

  const startDemo = useCallback(async (role: DemoRole) => {
    setDemoRole(role);
    setLoading(true);
    return loadMe(null, role);
  }, [loadMe]);

  const exitDemo = useCallback(() => {
    setDemoRole(null);
    setDemo(null);
    setMe(null);
  }, []);

  const signOut = useCallback(async () => {
    if (demo) exitDemo();
    else await supabase.auth.signOut();
  }, [demo, exitDemo]);

  return (
    <SessionContext.Provider value={{ loading, session, demo, me, error, signOut, startDemo, exitDemo }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}

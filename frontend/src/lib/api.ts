// Calls to the SolarDokta backend (FastAPI). Every call carries the person's login token,
// so the backend knows who is asking and which sites they may open.
import { supabase } from "./supabase";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Site = { code: string; name: string; city: string };
export type Me = {
  id: string;
  role: "staff" | "customer";
  full_name: string | null;
  preferred_language: "en" | "pcm" | "ig";
  sites: Site[];
  demo?: boolean;
};

// Public demo (no login): the backend accepts these two tokens read-only for the demo site.
export type DemoRole = "customer" | "staff";
const DEMO_KEY = "solardokta-demo";

export function demoRole(): DemoRole | null {
  try {
    const v = sessionStorage.getItem(DEMO_KEY);
    return v === "customer" || v === "staff" ? v : null;
  } catch {
    return null;
  }
}

export function setDemoRole(role: DemoRole | null) {
  try {
    if (role) sessionStorage.setItem(DEMO_KEY, role);
    else sessionStorage.removeItem(DEMO_KEY);
  } catch {
    /* private window: the demo just won't survive a reload */
  }
}

async function token(): Promise<string> {
  const demo = demoRole();
  if (demo) return `demo-${demo}`;
  const { data } = await supabase.auth.getSession();
  const t = data.session?.access_token;
  if (!t) throw new ApiError(401, "Log in first");
  return t;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const bearer = await token();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${bearer}`, "Content-Type": "application/json" },
    });
  } catch {
    throw new ApiError(0, `Can't reach the SolarDokta server at ${API_URL}. Is it running?`);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

// Send a file (multipart form). The browser sets the Content-Type with the form boundary itself.
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const bearer = await token();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { method: "POST", body: form, headers: { Authorization: `Bearer ${bearer}` } });
  } catch {
    throw new ApiError(0, `Can't reach the SolarDokta server at ${API_URL}. Is it running?`);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : `Upload failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

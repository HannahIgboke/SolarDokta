// The browser's connection to Supabase. It uses the public "anon" key: safe to ship to the
// browser because Row Level Security decides what each logged-in person may read.
// Never put the service role key in the frontend.
import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  throw new Error("Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local");
}

export const supabase = createClient(url, anonKey);

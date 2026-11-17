"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/env";

let client: SupabaseClient | null = null;

export function supabaseConfigured(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY);
}

/** Browser client used only for sign-in and session refresh; all data goes through FastAPI. */
export function getSupabaseBrowserClient(): SupabaseClient {
  if (!supabaseConfigured()) {
    throw new Error("Supabase auth is enabled but NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY are not set.");
  }
  client ??= createBrowserClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);
  return client;
}

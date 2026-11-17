// The ONLY environment values the browser may read. Next.js inlines NEXT_PUBLIC_* at build time;
// direct property access is required for that, so don't refactor these into a dynamic lookup.
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");

export type AuthMode = "dev" | "supabase";
export const AUTH_MODE: AuthMode = process.env.NEXT_PUBLIC_AUTH_MODE === "supabase" ? "supabase" : "dev";

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";

export const DEFAULT_TIMEZONE = "Asia/Kolkata";

import { createServerClient } from "@supabase/ssr";
import type { EmailOtpType } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
import { AUTH_MODE, SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/env";

function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

/** Supabase magic-link landing: exchanges the PKCE code (or verifies the token hash) and stores the session cookie. */
export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const next = safeNext(url.searchParams.get("next"));
  const fail = (message: string) => NextResponse.redirect(new URL(`/login?error=${encodeURIComponent(message)}`, url.origin));

  if (AUTH_MODE !== "supabase" || !SUPABASE_URL || !SUPABASE_PUBLISHABLE_KEY) {
    return NextResponse.redirect(new URL("/login", url.origin));
  }

  const cookieStore = await cookies();
  const supabase = createServerClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (list) => {
        for (const { name, value, options } of list) cookieStore.set(name, value, options);
      },
    },
  });

  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");
  const type = url.searchParams.get("type") as EmailOtpType | null;

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) return fail(error.message);
  } else if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
    if (error) return fail(error.message);
  } else {
    return fail(url.searchParams.get("error_description") ?? "missing code");
  }
  return NextResponse.redirect(new URL(next, url.origin));
}

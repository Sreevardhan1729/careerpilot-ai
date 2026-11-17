"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { configureApi, isAccountDeleted } from "@/lib/api";
import { AUTH_MODE } from "@/lib/env";
import { clearDevToken, readDevToken, writeDevToken } from "./dev-token";
import { getSupabaseBrowserClient, supabaseConfigured } from "./supabase";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export type SignOutReason = "expired" | "deleted" | "forbidden" | "manual" | null;

/** Where to send a signed-out user. Manual sign-out goes to a clean login page; others keep the page to return to. */
export function loginUrl(reason: SignOutReason, next: string | null): string {
  if (reason === "manual") return "/login";
  if (reason === "deleted" || reason === "forbidden") return `/login?reason=${reason}`;
  const p = new URLSearchParams();
  if (reason === "expired") p.set("reason", "expired");
  if (next && next.startsWith("/") && !next.startsWith("//") && next !== "/login") p.set("next", next);
  const qs = p.toString();
  return qs ? `/login?${qs}` : "/login";
}

interface AuthContextValue {
  status: AuthStatus;
  /** Why the user was last signed out (drives the login-page notice). */
  signOutReason: SignOutReason;
  mode: typeof AUTH_MODE;
  /** Store a dev-mode token after POST /dev/login. */
  signInWithDevToken: (token: string) => void;
  signOut: (reason?: "expired" | "deleted" | "forbidden") => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function currentToken(): Promise<string | null> {
  if (AUTH_MODE === "dev") return readDevToken();
  if (!supabaseConfigured()) return null;
  const { data } = await getSupabaseBrowserClient().auth.getSession();
  return data.session?.access_token ?? null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [signOutReason, setSignOutReason] = useState<SignOutReason>(null);
  const queryClient = useQueryClient();
  const signingOut = useRef(false);

  const signOut = useCallback(
    async (reason?: "expired" | "deleted" | "forbidden") => {
      if (signingOut.current) return;
      signingOut.current = true;
      try {
        if (AUTH_MODE === "dev") clearDevToken();
        else if (supabaseConfigured()) await getSupabaseBrowserClient().auth.signOut();
      } finally {
        queryClient.clear();
        // The app shell sees "unauthenticated" and redirects using this reason (single redirect, no race).
        setSignOutReason(reason ?? "manual");
        setStatus("unauthenticated");
        signingOut.current = false;
      }
    },
    [queryClient],
  );

  // The API client asks for a fresh token per request; a 401 anywhere signs out.
  useEffect(() => {
    configureApi({
      getToken: currentToken,
      onUnauthorized: () => {
        void signOut("expired");
      },
      onForbidden: (error) => {
        void signOut(isAccountDeleted(error) ? "deleted" : "forbidden");
      },
    });
  }, [signOut]);

  useEffect(() => {
    let cancelled = false;
    if (AUTH_MODE === "dev") {
      // Reading localStorage must happen after hydration.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStatus(readDevToken() ? "authenticated" : "unauthenticated");
      return;
    }
    if (!supabaseConfigured()) {
      setStatus("unauthenticated");
      return;
    }
    const supabase = getSupabaseBrowserClient();
    supabase.auth.getSession().then(({ data }) => {
      if (!cancelled) setStatus(data.session ? "authenticated" : "unauthenticated");
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      setStatus(session ? "authenticated" : "unauthenticated");
    });
    return () => {
      cancelled = true;
      sub.subscription.unsubscribe();
    };
  }, []);

  const signInWithDevToken = useCallback((token: string) => {
    writeDevToken(token);
    setSignOutReason(null);
    setStatus("authenticated");
  }, []);

  const value = useMemo(
    () => ({ status, signOutReason, mode: AUTH_MODE, signInWithDevToken, signOut }),
    [status, signOutReason, signInWithDevToken, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

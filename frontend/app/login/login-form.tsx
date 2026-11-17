"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2Icon, MailCheckIcon } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth/auth-context";
import { getSupabaseBrowserClient, supabaseConfigured } from "@/lib/auth/supabase";
import { api } from "@/lib/endpoints";

function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

export function LoginForm() {
  const { mode, status, signInWithDevToken } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const reason = params.get("reason");
  const callbackError = params.get("error");
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);

  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, router, next]);

  const devLogin = useMutation({
    mutationFn: (value: string) => api.devLogin(value),
    onSuccess: (res) => {
      signInWithDevToken(res.access_token);
      router.replace(next);
    },
  });

  const magicLink = useMutation({
    mutationFn: async (value: string) => {
      const supabase = getSupabaseBrowserClient();
      const redirect = new URL("/auth/callback", window.location.origin);
      redirect.searchParams.set("next", next);
      const { error } = await supabase.auth.signInWithOtp({ email: value, options: { emailRedirectTo: redirect.toString() } });
      if (error) throw new Error(error.message);
      return value;
    },
    onSuccess: (value) => setSentTo(value),
  });

  const pending = devLogin.isPending || magicLink.isPending;
  const error = devLogin.error ?? magicLink.error;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const value = email.trim();
    if (!value) return;
    if (mode === "dev") devLogin.mutate(value);
    else magicLink.mutate(value);
  }

  const misconfigured = mode === "supabase" && !supabaseConfigured();

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <h1 className="text-xl font-semibold leading-tight">Sign in to CareerPilot AI</h1>
        <CardDescription>
          {mode === "dev"
            ? "Local development sign-in. Enter any email allowed by the backend."
            : "We'll email you a magic link. No password needed."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {reason === "expired" && (
          <Alert variant="warning">
            <AlertDescription>Your session ended. Sign in again to continue.</AlertDescription>
          </Alert>
        )}
        {reason === "deleted" && (
          <Alert variant="info">
            <AlertDescription>This account was deleted. Sign in with another email to start fresh.</AlertDescription>
          </Alert>
        )}
        {reason === "forbidden" && (
          <Alert variant="destructive">
            <AlertDescription>This account isn&apos;t allowed to use this deployment.</AlertDescription>
          </Alert>
        )}
        {callbackError && (
          <Alert variant="destructive">
            <AlertDescription>Sign-in link failed: {callbackError}. Request a new link.</AlertDescription>
          </Alert>
        )}
        {misconfigured && (
          <Alert variant="destructive">
            <AlertDescription>
              Supabase auth is enabled, but NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY are not set.
            </AlertDescription>
          </Alert>
        )}
        {sentTo ? (
          <Alert variant="success">
            <MailCheckIcon aria-hidden="true" />
            <AlertDescription>
              Check <strong>{sentTo}</strong> for a sign-in link. You can close this tab.
            </AlertDescription>
          </Alert>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <Field id="email" label="Email" required>
              <Input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                disabled={pending || misconfigured}
              />
            </Field>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{errorMessage(error)}</AlertDescription>
              </Alert>
            )}
            <Button type="submit" className="w-full" disabled={pending || misconfigured || !email.trim()}>
              {pending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              {mode === "dev" ? "Sign in" : "Email me a sign-in link"}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

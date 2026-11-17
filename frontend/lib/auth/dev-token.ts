/** Dev-mode bearer token storage (NEXT_PUBLIC_AUTH_MODE=dev only). */
const KEY = "careerpilot.devAccessToken";

export function readDevToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function writeDevToken(token: string): void {
  window.localStorage.setItem(KEY, token);
}

export function clearDevToken(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // storage unavailable — nothing to clear
  }
}

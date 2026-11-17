"use client";

import {
  BriefcaseIcon,
  FileTextIcon,
  KanbanSquareIcon,
  LayoutDashboardIcon,
  Loader2Icon,
  LogOutIcon,
  MailIcon,
  MenuIcon,
  SettingsIcon,
  UsersIcon,
  XIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { NotificationsBell } from "@/components/notifications-bell";
import { Button } from "@/components/ui/button";
import { useMe } from "@/hooks/use-me";
import { loginUrl, useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard", Icon: LayoutDashboardIcon },
  { href: "/jobs", label: "Job Search", Icon: BriefcaseIcon },
  { href: "/resumes", label: "Resume Library", Icon: FileTextIcon },
  { href: "/people", label: "People", Icon: UsersIcon },
  { href: "/outreach", label: "Outreach", Icon: MailIcon },
  { href: "/applications", label: "Applications", Icon: KanbanSquareIcon },
  { href: "/settings", label: "Settings", Icon: SettingsIcon },
] as const;

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <ul className="space-y-1">
      {NAV.map(({ href, label, Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <li key={href}>
            <Link
              href={href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-ring",
                active ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-accent",
              )}
            >
              <Icon className="size-4" aria-hidden="true" />
              {label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/** Authenticated chrome: sidebar navigation, notifications, sign-out, and the auth redirect guard. */
export function AppShell({ children }: { children: ReactNode }) {
  const { status, signOut, signOutReason } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const me = useMe();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (status === "unauthenticated") router.replace(loginUrl(signOutReason, pathname));
  }, [status, router, pathname, signOutReason]);

  if (status !== "authenticated") {
    return (
      <div role="status" className="flex min-h-screen items-center justify-center gap-2 text-muted-foreground">
        <Loader2Icon className="size-5 animate-spin" aria-hidden="true" />
        {status === "loading" ? "Checking your session…" : "Redirecting to sign in…"}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-muted/30">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b bg-background px-4">
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={mobileOpen}
          aria-controls="mobile-nav"
          onClick={() => setMobileOpen((o) => !o)}
        >
          {mobileOpen ? <XIcon aria-hidden="true" /> : <MenuIcon aria-hidden="true" />}
        </Button>
        <Link href="/dashboard" className="font-semibold tracking-tight">
          CareerPilot <span className="text-primary">AI</span>
        </Link>
        <div className="ml-auto flex items-center gap-2">
          <NotificationsBell />
          <span className="hidden text-sm text-muted-foreground sm:inline" aria-label="Signed in as">
            {me.data?.email}
          </span>
          <Button variant="ghost" size="sm" onClick={() => void signOut()}>
            <LogOutIcon aria-hidden="true" />
            Sign out
          </Button>
        </div>
      </header>
      <div className="flex">
        <nav aria-label="Main" className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-56 shrink-0 border-r bg-background p-3 md:block">
          <NavLinks />
        </nav>
        {mobileOpen && (
          <nav id="mobile-nav" aria-label="Main" className="fixed inset-x-0 top-14 z-30 border-b bg-background p-3 shadow-md md:hidden">
            <NavLinks onNavigate={() => setMobileOpen(false)} />
          </nav>
        )}
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 p-4 md:p-8">
          <div className="mx-auto max-w-7xl">{children}</div>
        </main>
      </div>
    </div>
  );
}

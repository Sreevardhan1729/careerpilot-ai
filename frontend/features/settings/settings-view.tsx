"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTab } from "./data-tab";
import { FactsTab } from "./facts-tab";
import { GeneralTab } from "./general-tab";
import { IntegrationsTab } from "./integrations-tab";
import { ProfileTab } from "./profile-tab";
import { SchedulerTab } from "./scheduler-tab";
import { SearchConfigsTab } from "./search-configs-tab";
import { SourcesTab } from "./sources-tab";

const TABS = [
  { id: "profile", label: "Profile", Component: ProfileTab },
  { id: "facts", label: "Profile facts", Component: FactsTab },
  { id: "search", label: "Search preferences", Component: SearchConfigsTab },
  { id: "sources", label: "Sources", Component: SourcesTab },
  { id: "scheduler", label: "Scheduler & discovery", Component: SchedulerTab },
  { id: "integrations", label: "Integrations", Component: IntegrationsTab },
  { id: "general", label: "General", Component: GeneralTab },
  { id: "data", label: "Data", Component: DataTab },
] as const;

export function SettingsView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const requested = params.get("tab");
  const tab = TABS.some((t) => t.id === requested) ? (requested as string) : "profile";
  return (
    <>
      <PageHeader title="Settings" description="Your profile, search preferences, sources, integrations and data." />
      <Tabs
        value={tab}
        onValueChange={(v) => router.replace(v === "profile" ? pathname : `${pathname}?tab=${v}`, { scroll: false })}
      >
        <TabsList aria-label="Settings sections" className="h-auto">
          {TABS.map((t) => (
            <TabsTrigger key={t.id} value={t.id}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map(({ id, Component }) => (
          <TabsContent key={id} value={id}>
            <Component />
          </TabsContent>
        ))}
      </Tabs>
    </>
  );
}

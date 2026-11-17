"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ExternalLink } from "@/components/external-link";
import { PageHeader } from "@/components/page-header";
import { EmptyState, NotAvailable, QueryView } from "@/components/query-state";
import { Time } from "@/components/time";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { hasEndpoint } from "@/lib/capabilities";
import { api, itemsOf } from "@/lib/endpoints";
import { titleCase } from "@/lib/utils";
import { AddPersonDialog, AssociationBadge, CONTACT_STATUSES, ContactStatusSelect } from "./people-common";

export function PeopleView() {
  const [contactStatus, setContactStatus] = useState("");
  const enabled = hasEndpoint("GET", "/people");
  const query = useQuery({
    queryKey: ["people", "list", contactStatus],
    queryFn: () => api.people.list({ contact_status: contactStatus || undefined, limit: 100 }),
    enabled,
  });

  return (
    <>
      <PageHeader
        title="People"
        description={
          <>
            Contacts discovered from public evidence across your jobs. Per-job ranking lives on each job&apos;s{" "}
            <Link href="/jobs" className="text-primary underline-offset-2 hover:underline">
              People tab
            </Link>
            .
          </>
        }
        actions={enabled ? <AddPersonDialog /> : null}
      />
      {!enabled ? (
        <NotAvailable feature="People" endpoint="GET /people" />
      ) : (
        <>
          <div className="mb-4 max-w-xs">
            <Field id="people-status" label="Contact status">
              <NativeSelect value={contactStatus} onChange={(e) => setContactStatus(e.target.value)}>
                <option value="">All</option>
                {CONTACT_STATUSES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          </div>
          <QueryView query={query} loadingLabel="Loading people…" errorTitle="Couldn't load people">
            {(data) => {
              const people = itemsOf(data);
              if (!people.length)
                return (
                  <EmptyState
                    title="No people yet"
                    description="Open a job and use Find people, or add someone you know."
                  />
                );
              return (
                <Card>
                  <Table aria-label="People">
                    <TableHeader>
                      <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Company</TableHead>
                        <TableHead>Association</TableHead>
                        <TableHead>Contact</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Added</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {people.map((p) => (
                        <TableRow key={p.id}>
                          <TableCell className="min-w-48">
                            <p className="font-medium">{p.name}</p>
                            <p className="text-muted-foreground">{[p.designation, p.department].filter(Boolean).join(" · ") || "—"}</p>
                            {p.notes && <p className="mt-1 whitespace-pre-wrap text-xs text-muted-foreground">{p.notes}</p>}
                          </TableCell>
                          <TableCell>{p.company?.name ?? "—"}</TableCell>
                          <TableCell>
                            <AssociationBadge status={p.association_status} />
                          </TableCell>
                          <TableCell className="space-y-1">
                            {p.linkedin_url && (
                              <div>
                                <ExternalLink href={p.linkedin_url}>Profile</ExternalLink>
                              </div>
                            )}
                            {p.public_email && <div className="text-sm">{p.public_email}</div>}
                            {!p.linkedin_url && !p.public_email && <span className="text-muted-foreground">—</span>}
                          </TableCell>
                          <TableCell>
                            <ContactStatusSelect personId={p.id} value={p.contact_status} name={p.name} />
                          </TableCell>
                          <TableCell className="text-sm">
                            <Time value={p.first_discovered_at} dateOnly />
                            <div className="text-xs text-muted-foreground">{titleCase(p.added_by)}</div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Card>
              );
            }}
          </QueryView>
        </>
      )}
    </>
  );
}

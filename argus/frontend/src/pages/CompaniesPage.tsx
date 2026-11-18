import { Plus, Search, Trash2 } from "lucide-react";
import { useDeferredValue, useState, type FormEvent } from "react";

import type { Schemas } from "@/api/client";
import { useCompanies, useCompanyMutations } from "@/api/queries";
import { Checkbox, Field, Input } from "@/components/ui/form";
import { Badge, Button, Card, EmptyState, ErrorBanner, PageHeader, Spinner } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { timeAgo } from "@/lib/format";

function AddCompany() {
  const { create, detect } = useCompanyMutations();
  const toast = useToast();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [detected, setDetected] = useState<Schemas["AtsDetectResponse"] | null>(null);

  const check = () => {
    if (!url.startsWith("http")) return setDetected(null);
    detect.mutate(url, { onSuccess: setDetected, onError: () => setDetected(null) });
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(
      { name, careers_url: url || null },
      {
        onSuccess: (c) => {
          toast.success(c.ats_kind ? `Added ${c.name} (${c.ats_kind} board "${c.ats_token}")` : `Added ${c.name} (no supported job board detected)`);
          setName(""); setUrl(""); setDetected(null);
        },
        onError: toast.error,
      },
    );
  };

  return (
    <Card title="Watch a company" description="Paste its careers page. Greenhouse, Lever, Ashby and SmartRecruiters boards are detected automatically.">
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-[1fr_2fr_auto] md:items-end">
        <Field label="Company name"><Input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Stripe" /></Field>
        <Field
          label="Careers page URL"
          hint={detected ? (detected.detected ? <span className="text-emerald-700 dark:text-emerald-400">Detected {detected.ats_kind} board “{detected.ats_token}”</span> : "No supported job board detected — you can still add it.") : "e.g. https://job-boards.greenhouse.io/stripe"}
        >
          <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} onBlur={check} placeholder="https://jobs.lever.co/…" />
        </Field>
        <Button type="submit" variant="primary" icon={<Plus className="size-4" />} loading={create.isPending}>Add</Button>
      </form>
    </Card>
  );
}

export function CompaniesPage() {
  const [q, setQ] = useState("");
  const deferred = useDeferredValue(q.trim());
  const companies = useCompanies(deferred);
  const { toggle, remove } = useCompanyMutations();
  const toast = useToast();
  const rows = companies.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <PageHeader title="Companies" description="The job boards ARGUS watches. Automatic discovery from these boards arrives in the next milestone." />
      <div className="space-y-6">
        <AddCompany />
        <Card
          title="Watched companies"
          actions={
            <div className="relative">
              <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-slate-400" />
              <Input className="w-56 pl-8" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          }
        >
          <ErrorBanner error={companies.error} />
          {companies.isLoading ? <Spinner /> : rows.length === 0 ? <EmptyState title="No companies yet" /> : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {rows.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                  <div>
                    <p className="font-medium">{c.name}</p>
                    <p className="text-xs text-slate-500">
                      {c.ats_kind ? <Badge tone="blue">{c.ats_kind}: {c.ats_token}</Badge> : <Badge>manual</Badge>}{" "}
                      {c.last_discovered_at ? `crawled ${timeAgo(c.last_discovered_at)}` : "never crawled"}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Checkbox label="Enabled" checked={c.enabled} onChange={(enabled) => toggle.mutate({ id: c.id, enabled }, { onError: toast.error })} />
                    <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} aria-label={`Delete ${c.name}`} onClick={() => remove.mutate(c.id, { onError: toast.error })} />
                  </div>
                </li>
              ))}
            </ul>
          )}
          {companies.hasNextPage && (
            <div className="mt-4 text-center"><Button onClick={() => companies.fetchNextPage()} loading={companies.isFetchingNextPage}>Load more</Button></div>
          )}
        </Card>
      </div>
    </>
  );
}

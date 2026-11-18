import { clsx } from "clsx";
import { Plus, Search } from "lucide-react";
import { useDeferredValue, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import type { Schemas } from "@/api/client";
import { useCreateJob, useJobAction, useJobs, useShortlist, type JobFilters } from "@/api/queries";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form";
import { Badge, Button, Card, EmptyState, ErrorBanner, PageHeader, ScoreBadge, Spinner } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { formatDate, titleCase } from "@/lib/format";

type Row = Schemas["JobSummary"] & { hard_fail_reasons?: string[] };

function JobTable({ rows }: { rows: Row[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-500 uppercase">
          <tr>
            <th className="py-2 pr-3 font-medium">Score</th>
            <th className="py-2 pr-3 font-medium">Role</th>
            <th className="py-2 pr-3 font-medium">Location</th>
            <th className="py-2 pr-3 font-medium">Mode</th>
            <th className="py-2 font-medium">Seen</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {rows.map((job) => (
            <tr key={job.id} className="align-top">
              <td className="py-2.5 pr-3">
                <ScoreBadge score={job.score} failed={job.passed_hard_filters === false} />
              </td>
              <td className="py-2.5 pr-3">
                <Link to={`/jobs/${job.id}`} className="font-medium hover:text-brand-600">{job.title}</Link>
                <p className="text-xs text-slate-500">
                  {job.company_name} · <span className="uppercase">{job.source}</span>
                </p>
                {job.hard_fail_reasons?.length ? <p className="mt-0.5 text-xs text-red-600">{job.hard_fail_reasons.join("; ")}</p> : null}
              </td>
              <td className="max-w-56 py-2.5 pr-3 text-slate-600 dark:text-slate-300">{job.location_text ?? "—"}</td>
              <td className="py-2.5 pr-3"><Badge>{job.work_mode}</Badge></td>
              <td className="py-2.5 text-xs whitespace-nowrap text-slate-500">{formatDate(job.first_seen_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AddJobForm({ onDone }: { onDone: () => void }) {
  const create = useCreateJob();
  const extract = useJobAction("extract");
  const toast = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState<Schemas["ManualJobCreate"]>({
    company_name: "", title: "", url: "", location: "", work_mode: "unknown", description: "",
  });
  const set = (k: keyof Schemas["ManualJobCreate"]) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({ ...form, location: form.location || null }, {
      onSuccess: (job) => {
        extract.mutate(job.id); // the worker extracts + scores it
        toast.success("Job added — extracting requirements with the local LLM");
        onDone();
        navigate(`/jobs/${job.id}`);
      },
      onError: toast.error,
    });
  };

  return (
    <Card title="Add a job manually" description="For postings from portals ARGUS must not automate (e.g. LinkedIn, Naukri).">
      <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
        <Field label="Company"><Input required value={form.company_name} onChange={(e) => set("company_name")(e.target.value)} /></Field>
        <Field label="Job title"><Input required value={form.title} onChange={(e) => set("title")(e.target.value)} /></Field>
        <Field label="Posting URL"><Input required type="url" placeholder="https://…" value={form.url} onChange={(e) => set("url")(e.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Location"><Input value={form.location ?? ""} onChange={(e) => set("location")(e.target.value)} /></Field>
          <Field label="Work mode">
            <Select value={form.work_mode} onChange={(e) => set("work_mode")(e.target.value)}>
              {["unknown", "remote", "hybrid", "onsite"].map((m) => <option key={m} value={m}>{titleCase(m)}</option>)}
            </Select>
          </Field>
        </div>
        <div className="md:col-span-2">
          <Field label="Job description" hint="Paste the full text. It's treated as untrusted data by the LLM.">
            <Textarea required className="min-h-48" value={form.description} onChange={(e) => set("description")(e.target.value)} />
          </Field>
        </div>
        <div className="flex gap-2 md:col-span-2">
          <Button type="submit" variant="primary" loading={create.isPending}>Add job</Button>
          <Button variant="ghost" onClick={onDone}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}

export function JobsPage() {
  const [tab, setTab] = useState<"best" | "all">("best");
  const [includeFailed, setIncludeFailed] = useState(false);
  const [adding, setAdding] = useState(false);
  const [q, setQ] = useState("");
  const [workMode, setWorkMode] = useState<JobFilters["work_mode"] | "">("");
  const deferredQ = useDeferredValue(q.trim().length >= 2 ? q.trim() : "");

  const shortlist = useShortlist(includeFailed);
  const jobs = useJobs({ q: deferredQ, work_mode: workMode || undefined, status: "active" });
  const active = tab === "best" ? shortlist : jobs;
  const rows: Row[] = active.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <PageHeader
        title="Jobs"
        description="Best matches use your profile + preferences. Scores explain themselves on each job's page."
        actions={<Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setAdding((a) => !a)}>Add job</Button>}
      />
      {adding && <div className="mb-6"><AddJobForm onDone={() => setAdding(false)} /></div>}

      <Card>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-lg border border-slate-200 p-0.5 dark:border-slate-700" role="tablist">
            {(["best", "all"] as const).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={clsx("rounded-md px-3 py-1.5 text-sm font-medium", tab === t ? "bg-brand-600 text-white" : "text-slate-600 dark:text-slate-300")}
              >
                {t === "best" ? "Best matches" : "All jobs"}
              </button>
            ))}
          </div>
          {tab === "best" ? (
            <Checkbox label="Include jobs that fail hard filters" checked={includeFailed} onChange={setIncludeFailed} />
          ) : (
            <>
              <div className="relative">
                <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-slate-400" />
                <Input className="w-64 pl-8" placeholder='Search: python -senior "new grad"' value={q} onChange={(e) => setQ(e.target.value)} />
              </div>
              <Select className="w-40" value={workMode ?? ""} onChange={(e) => setWorkMode(e.target.value as JobFilters["work_mode"] | "")}>
                <option value="">Any work mode</option>
                {["remote", "hybrid", "onsite", "unknown"].map((m) => <option key={m} value={m}>{titleCase(m)}</option>)}
              </Select>
            </>
          )}
        </div>

        <ErrorBanner error={active.error} />
        {active.isLoading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <EmptyState title={tab === "best" ? "No scored jobs yet" : "No jobs found"}>
            {tab === "best" ? "Jobs are scored automatically after the LLM extracts their requirements." : "Try a different search."}
          </EmptyState>
        ) : (
          <JobTable rows={rows} />
        )}
        {active.hasNextPage && (
          <div className="mt-4 text-center">
            <Button onClick={() => active.fetchNextPage()} loading={active.isFetchingNextPage}>Load more</Button>
          </div>
        )}
      </Card>
    </>
  );
}

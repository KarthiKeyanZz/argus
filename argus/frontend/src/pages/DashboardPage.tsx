import { Flame, RefreshCw, Upload } from "lucide-react";
import { Link } from "react-router";

import {
  useEnqueueTask,
  useExperience,
  useHealth,
  usePreferences,
  useProfile,
  useRunMatching,
  useShortlist,
  useSkills,
  useTasks,
} from "@/api/queries";
import { Badge, Button, Card, EmptyState, PageHeader, ScoreBadge, Spinner } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { timeAgo } from "@/lib/format";

const TASK_TONE = { succeeded: "green", failed: "red", running: "blue", queued: "neutral", cancelled: "amber" } as const;

function Checklist() {
  const profile = useProfile();
  const skills = useSkills();
  const experience = useExperience();
  const prefs = usePreferences();
  const steps = [
    { done: Boolean(profile.data?.full_name), label: "Import your resume", to: "/profile" },
    { done: (skills.data?.length ?? 0) >= 5, label: "Review your skills (5+)", to: "/profile" },
    { done: (experience.data?.length ?? 0) > 0, label: "Add experience or internships", to: "/profile" },
    { done: Boolean(prefs.data?.updated_at), label: "Set job preferences", to: "/preferences" },
  ];
  const done = steps.filter((s) => s.done).length;
  return (
    <Card title="Getting started" description={`${done} of ${steps.length} done`}>
      <ul className="space-y-2">
        {steps.map((s) => (
          <li key={s.label} className="flex items-center justify-between text-sm">
            <span className={s.done ? "text-slate-400 line-through" : ""}>{s.label}</span>
            {s.done ? <Badge tone="green">done</Badge> : <Link className="text-brand-600 hover:underline" to={s.to}>Open →</Link>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function DashboardPage() {
  const health = useHealth();
  const shortlist = useShortlist(false);
  const tasks = useTasks();
  const runMatching = useRunMatching();
  const enqueue = useEnqueueTask();
  const toast = useToast();
  const top = shortlist.data?.pages[0]?.items.slice(0, 6) ?? [];

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Your best-matching jobs and what ARGUS is doing right now."
        actions={
          <>
            <Button
              icon={<Flame className="size-4" />}
              loading={enqueue.isPending}
              onClick={() => enqueue.mutate("llm.warmup", { onSuccess: () => toast.info("Loading the model into GPU memory…"), onError: toast.error })}
              title="Loads the 16 GB model so the next LLM call is fast"
            >
              Warm up LLM
            </Button>
            <Button
              variant="primary"
              icon={<RefreshCw className="size-4" />}
              loading={runMatching.isPending}
              onClick={() => runMatching.mutate(undefined, { onSuccess: () => toast.info("Re-scoring all jobs in the background"), onError: toast.error })}
            >
              Re-score jobs
            </Button>
          </>
        }
      />

      {health.data && !health.data.llm.ok && (
        <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Local LLM unavailable: {health.data.llm.detail}. Start it with <code>systemctl --user start ollama</code>.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          className="lg:col-span-2"
          title="Top matches"
          description="Ranked by fit score; only jobs that pass your hard filters."
          actions={<Link to="/jobs" className="text-sm text-brand-600 hover:underline">All jobs →</Link>}
        >
          {shortlist.isLoading ? (
            <Spinner />
          ) : top.length === 0 ? (
            <EmptyState title="No scored jobs yet">
              Add companies or jobs, then press <b>Re-score jobs</b>.
            </EmptyState>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {top.map((job) => (
                <li key={job.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0">
                    <Link to={`/jobs/${job.id}`} className="block truncate font-medium hover:text-brand-600">
                      {job.title}
                    </Link>
                    <p className="truncate text-xs text-slate-500">
                      {job.company_name} · {job.location_text ?? "location n/a"}
                    </p>
                  </div>
                  <ScoreBadge score={job.score} failed={!job.passed_hard_filters} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Checklist />

        <Card
          className="lg:col-span-3"
          title="Background activity"
          actions={<Link to="/activity" className="text-sm text-brand-600 hover:underline">Details →</Link>}
        >
          {tasks.isLoading ? (
            <Spinner />
          ) : (tasks.data?.items.length ?? 0) === 0 ? (
            <EmptyState title="Nothing has run yet" />
          ) : (
            <ul className="grid gap-2 text-sm sm:grid-cols-2">
              {tasks.data!.items.slice(0, 8).map((t) => (
                <li key={t.id} className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 dark:border-slate-800">
                  <span className="font-mono text-xs">{t.kind}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">{timeAgo(t.created_at)}</span>
                    <Badge tone={TASK_TONE[t.status]}>{t.status}</Badge>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <p className="mt-6 flex items-center gap-2 text-xs text-slate-500">
        <Upload className="size-3.5" /> Tip: start by importing your resume on the Profile page.
      </p>
    </>
  );
}

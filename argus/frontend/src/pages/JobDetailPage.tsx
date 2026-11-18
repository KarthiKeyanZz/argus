import { ArrowLeft, ExternalLink, RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";

import type { Schemas } from "@/api/client";
import { keys, useJob, useJobAction, useTask } from "@/api/queries";
import { Badge, Button, Card, EmptyState, ErrorBanner, Meter, ScoreBadge, Spinner, type Tone } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { formatDate, titleCase } from "@/lib/format";

interface SkillRow {
  skill: string;
  status: "exact" | "similar" | "related" | "missing";
  matched_with: string | null;
  similarity: number | null;
}
interface Breakdown {
  components: Record<string, number>;
  weights: Record<string, number>;
  unknown_components: string[];
  title_similarity: number | null;
  experience_note: string;
  location_note: string;
  skills: { required: SkillRow[]; preferred: SkillRow[]; threshold: number };
}

const STATUS_TONE: Record<SkillRow["status"], Tone> = { exact: "green", similar: "teal", related: "amber", missing: "neutral" };
const STATUS_HELP: Record<SkillRow["status"], string> = {
  exact: "You list this skill (after synonym mapping)",
  similar: "Close match by meaning (embedding similarity ≥ threshold) — counts as partial credit",
  related: "Related but not equivalent — shown for context, earns no credit",
  missing: "Not in your profile",
};
const COMPONENT_LABEL: Record<string, string> = {
  title: "Title vs your target roles",
  required_skills: "Required skills",
  preferred_skills: "Preferred skills",
  experience: "Experience fit",
  location: "Location / work mode",
  freshness: "Freshness",
};

function SkillChips({ rows }: { rows: SkillRow[] }) {
  if (!rows.length) return <p className="text-sm text-slate-500">None listed in the posting.</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {rows.map((s) => (
        <Badge key={s.skill} tone={STATUS_TONE[s.status]} title={STATUS_HELP[s.status]}>
          {s.skill}
          {(s.status === "similar" || s.status === "related") && s.matched_with && (
            <span className="opacity-75">≈ {s.matched_with} ({s.similarity?.toFixed(2)})</span>
          )}
        </Badge>
      ))}
    </div>
  );
}

function MatchPanel({ match }: { match: Schemas["MatchOut"] }) {
  const b = match.breakdown as unknown as Breakdown;
  return (
    <Card title="Why this score" description={`Computed ${formatDate(match.computed_at)} · a ranking aid, not a probability of being hired`}>
      <div className="mb-5 flex items-center gap-4">
        <div className="text-4xl font-bold tabular-nums">{Number(match.score).toFixed(0)}</div>
        <div>
          <ScoreBadge score={match.score} failed={!match.passed_hard_filters} />
          {match.passed_hard_filters ? (
            <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-400">Passes all your hard filters</p>
          ) : (
            <ul className="mt-1 list-inside list-disc text-sm text-red-700 dark:text-red-400">
              {match.hard_fail_reasons.map((r) => <li key={r}>{r}</li>)}
            </ul>
          )}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {Object.entries(b.components).map(([key, value]) => (
          <Meter
            key={key}
            label={`${COMPONENT_LABEL[key] ?? key}${b.unknown_components.includes(key) ? " (unknown → neutral)" : ""}`}
            value={value}
            hint={`${Math.round(value * 100)}% · weight ${Math.round((b.weights[key] ?? 0) * 100)}%`}
          />
        ))}
      </div>

      <div className="mt-5 space-y-1 text-sm text-slate-600 dark:text-slate-300">
        <p><b>Experience:</b> {b.experience_note}</p>
        <p><b>Location:</b> {b.location_note}</p>
        {b.title_similarity !== null && <p><b>Title similarity:</b> {b.title_similarity.toFixed(2)} (embedding cosine)</p>}
      </div>

      <div className="mt-5 space-y-3">
        <div>
          <h3 className="mb-1.5 text-sm font-semibold">Required skills</h3>
          <SkillChips rows={b.skills.required} />
        </div>
        <div>
          <h3 className="mb-1.5 text-sm font-semibold">Preferred skills</h3>
          <SkillChips rows={b.skills.preferred} />
        </div>
        <p className="text-xs text-slate-500">
          <Badge tone="green">exact</Badge> <Badge tone="teal">similar ≥ {b.skills.threshold}</Badge>{" "}
          <Badge tone="amber">related</Badge> <Badge>missing</Badge> — hover a chip for details.
        </p>
      </div>
    </Card>
  );
}

function ExtractionPanel({ ex }: { ex: Schemas["JobExtractionOut"] }) {
  const years = ex.min_years_experience === null ? "not stated" : `${Number(ex.min_years_experience)}${ex.max_years_experience ? `–${Number(ex.max_years_experience)}` : "+"} years`;
  return (
    <Card title="What the LLM read from the posting" description={`${ex.model ?? ex.method} · prompt v${ex.extractor_version} · ${((ex.duration_ms ?? 0) / 1000).toFixed(1)} s`}>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <dt className="text-slate-500">Seniority</dt><dd>{titleCase(ex.seniority)}</dd>
        <dt className="text-slate-500">Experience</dt><dd>{years}</dd>
        <dt className="text-slate-500">Fresher-friendly</dt><dd>{ex.entry_level_friendly ? "Yes" : "No"}</dd>
        <dt className="text-slate-500">Education</dt><dd>{titleCase(ex.education_level)} {ex.education_fields?.length ? `(${ex.education_fields.join(", ")})` : ""}</dd>
        <dt className="text-slate-500">Type / mode</dt><dd>{titleCase(ex.employment_type)} · {titleCase(ex.work_mode)}</dd>
      </dl>
      {ex.summary && <p className="mt-3 text-sm italic text-slate-600 dark:text-slate-300">“{ex.summary}”</p>}
    </Card>
  );
}

export function JobDetailPage() {
  const jobId = Number(useParams().jobId);
  const job = useJob(jobId);
  const qc = useQueryClient();
  const toast = useToast();
  const extract = useJobAction("extract");
  const rescore = useJobAction("match");
  const [taskId, setTaskId] = useState<number | null>(null);

  const task = useTask(taskId, (t) => {
    if (t.status === "succeeded") toast.success(t.kind === "job.extract" ? "Extraction done — scoring now" : "Score updated");
    else toast.error(`${t.kind} ${t.status}: ${t.last_error ?? ""}`);
    if (t.kind === "job.extract" && t.status === "succeeded") window.setTimeout(() => qc.invalidateQueries({ queryKey: keys.job(jobId) }), 1500);
    qc.invalidateQueries({ queryKey: keys.job(jobId) });
    setTaskId(null);
  });
  const busy = taskId !== null;

  if (job.isLoading) return <Spinner />;
  if (job.error) return <ErrorBanner error={job.error} />;
  const j = job.data!;

  return (
    <>
      <Link to="/jobs" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-brand-600">
        <ArrowLeft className="size-4" /> Jobs
      </Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{j.title}</h1>
          <p className="mt-1 text-slate-600 dark:text-slate-300">
            {j.company_name} · {j.location_text ?? "location not stated"} · <Badge>{j.work_mode}</Badge>{" "}
            <Badge tone={j.status === "active" ? "green" : "neutral"}>{j.status}</Badge>
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Source: {j.source.toUpperCase()} · first seen {formatDate(j.first_seen_at)}
            {j.duplicate_of ? ` · possible duplicate of #${j.duplicate_of}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a href={j.canonical_url} target="_blank" rel="noopener noreferrer nofollow">
            <Button icon={<ExternalLink className="size-4" />}>Original posting</Button>
          </a>
          <Button
            icon={<Sparkles className="size-4" />}
            loading={extract.isPending || (busy && task.data?.kind === "job.extract")}
            disabled={busy}
            onClick={() => extract.mutate(jobId, { onSuccess: (r) => setTaskId(r.task.id), onError: toast.error })}
            title="Read the posting with the local LLM"
          >
            {j.extraction ? "Re-extract" : "Extract with LLM"}
          </Button>
          <Button
            variant="primary"
            icon={<RefreshCw className="size-4" />}
            loading={rescore.isPending || (busy && task.data?.kind === "match.job")}
            disabled={busy || !j.extraction}
            onClick={() => rescore.mutate(jobId, { onSuccess: (r) => setTaskId(r.task.id), onError: toast.error })}
          >
            Re-score
          </Button>
        </div>
      </div>

      {busy && (
        <p className="mb-4 text-sm text-slate-500" role="status">
          Worker: {task.data?.kind ?? "task"} is {task.data?.status ?? "queued"}… (make sure <code>make worker</code> is running)
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          {j.match ? <MatchPanel match={j.match} /> : (
            <Card title="Why this score">
              <EmptyState title="Not scored yet">Extract the posting first; scoring runs automatically afterwards.</EmptyState>
            </Card>
          )}
          <Card title="Job description">
            <div className="max-h-[32rem] overflow-y-auto text-sm leading-relaxed whitespace-pre-wrap text-slate-700 dark:text-slate-300">
              {j.description_text}
            </div>
          </Card>
        </div>
        <div className="space-y-6 lg:col-span-2">
          {j.extraction ? <ExtractionPanel ex={j.extraction} /> : (
            <Card title="Extraction"><EmptyState title="Not extracted yet" /></Card>
          )}
        </div>
      </div>
    </>
  );
}

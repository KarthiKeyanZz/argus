import { useState } from "react";

import type { Schemas } from "@/api/client";
import { usePreferences, useRunMatching, useSavePreferences } from "@/api/queries";
import { Checkbox, Field, Input, Slider, TagInput } from "@/components/ui/form";
import { Button, Card, ErrorBanner, PageHeader, Spinner } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { normalizeWeights, titleCase } from "@/lib/format";

type Prefs = Schemas["PreferencesUpdate"];
type Weights = Schemas["ScoringWeights"];
type Hard = Schemas["HardFilters"];

const LEVELS = ["fresher", "internship", "entry", "junior", "associate"] as const;
const MODES = ["remote", "hybrid", "onsite"] as const;
const TYPES = ["full_time", "internship", "part_time", "contract"] as const;
const WEIGHT_HELP: Record<keyof Weights, string> = {
  title: "How close the job title is to your target roles (embedding similarity)",
  required_skills: "Share of must-have skills you have (exact or similar)",
  preferred_skills: "Share of nice-to-have skills you have",
  experience: "Whether the years required fit your range",
  location: "Work mode and location match",
  freshness: "Newer postings rank higher",
};

function toggle<T>(list: T[] | undefined, item: T, on: boolean): T[] {
  const set = new Set(list ?? []);
  if (on) set.add(item);
  else set.delete(item);
  return [...set];
}

function Editor({ initial }: { initial: Prefs }) {
  const [p, setP] = useState<Prefs>(initial);
  const save = useSavePreferences();
  const rescore = useRunMatching();
  const toast = useToast();
  const weights = (p.scoring_weights ?? {}) as Weights;
  const hard = (p.hard_filters ?? {}) as Hard;
  const shares = normalizeWeights(weights as unknown as Record<string, number>);
  const set = <K extends keyof Prefs>(k: K, v: Prefs[K]) => setP((x) => ({ ...x, [k]: v }));

  const submit = () =>
    save.mutate(p, {
      onSuccess: () => {
        toast.success("Preferences saved — re-scoring jobs");
        rescore.mutate();
      },
      onError: toast.error,
    });

  return (
    <div className="space-y-6">
      <Card title="What you're looking for">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Target job titles" hint="Used for title similarity. Press Enter after each.">
            <TagInput value={p.target_titles ?? []} onChange={(v) => set("target_titles", v)} placeholder="Software Engineer, Backend Developer" />
          </Field>
          <Field label="Locations" hint="Cities or regions. Remote jobs always match.">
            <TagInput value={p.locations ?? []} onChange={(v) => set("locations", v)} placeholder="Chennai, Bengaluru" />
          </Field>
          <Field label="Countries"><TagInput value={p.countries ?? []} onChange={(v) => set("countries", v)} placeholder="India" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Min years (yours)"><Input type="number" min={0} step={0.5} value={p.min_years_experience ?? ""} onChange={(e) => set("min_years_experience", e.target.value === "" ? null : e.target.value)} /></Field>
            <Field label="Max years (yours)"><Input type="number" min={0} step={0.5} value={p.max_years_experience ?? ""} onChange={(e) => set("max_years_experience", e.target.value === "" ? null : e.target.value)} /></Field>
          </div>
          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-sm font-medium">Experience levels</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {LEVELS.map((l) => <Checkbox key={l} label={titleCase(l)} checked={(p.experience_levels ?? []).includes(l)} onChange={(on) => set("experience_levels", toggle(p.experience_levels, l, on))} />)}
            </div>
          </fieldset>
          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-sm font-medium">Work modes</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {MODES.map((m) => <Checkbox key={m} label={titleCase(m)} checked={(p.work_modes ?? []).includes(m)} onChange={(on) => set("work_modes", toggle(p.work_modes, m, on))} />)}
            </div>
          </fieldset>
          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-sm font-medium">Employment types</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {TYPES.map((t) => <Checkbox key={t} label={titleCase(t)} checked={(p.employment_types ?? []).includes(t)} onChange={(on) => set("employment_types", toggle(p.employment_types, t, on))} />)}
            </div>
          </fieldset>
          <Checkbox label="Willing to relocate" checked={Boolean(p.willing_to_relocate)} onChange={(v) => set("willing_to_relocate", v)} />
        </div>
      </Card>

      <Card title="Exclusions">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Excluded companies"><TagInput value={p.excluded_companies ?? []} onChange={(v) => set("excluded_companies", v)} /></Field>
          <Field label="Excluded title keywords" hint="Whole words, e.g. senior, staff, principal">
            <TagInput value={p.excluded_keywords ?? []} onChange={(v) => set("excluded_keywords", v)} />
          </Field>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Score weights" description="Relative importance; normalized to 100% when scoring.">
          <div className="space-y-4">
            {(Object.keys(WEIGHT_HELP) as Array<keyof Weights>).map((k) => (
              <Slider
                key={k}
                label={titleCase(k)}
                min={0}
                max={1}
                step={0.05}
                value={weights[k] ?? 0}
                onChange={(v) => set("scoring_weights", { ...weights, [k]: v })}
                format={() => `${Math.round((shares[k] ?? 0) * 100)}%`}
                hint={WEIGHT_HELP[k]}
              />
            ))}
          </div>
        </Card>
        <Card title="Hard filters" description="A job failing any of these is never auto-applied to, however high it scores.">
          <div className="space-y-3">
            <Field label="Max years of experience a job may require">
              <Input type="number" min={0} step={0.5} value={hard.max_required_years ?? ""} onChange={(e) => set("hard_filters", { ...hard, max_required_years: e.target.value === "" ? null : Number(e.target.value) })} />
            </Field>
            <Checkbox label="Only jobs explicitly open to freshers" checked={Boolean(hard.require_entry_level_friendly)} onChange={(v) => set("hard_filters", { ...hard, require_entry_level_friendly: v })} />
            <Checkbox label="Enforce work modes" checked={hard.enforce_work_modes ?? true} onChange={(v) => set("hard_filters", { ...hard, enforce_work_modes: v })} />
            <Checkbox label="Enforce locations" checked={Boolean(hard.enforce_locations)} onChange={(v) => set("hard_filters", { ...hard, enforce_locations: v })} />
            <Checkbox label="Enforce excluded companies" checked={hard.enforce_excluded_companies ?? true} onChange={(v) => set("hard_filters", { ...hard, enforce_excluded_companies: v })} />
            <Checkbox label="Enforce excluded keywords" checked={hard.enforce_excluded_keywords ?? true} onChange={(v) => set("hard_filters", { ...hard, enforce_excluded_keywords: v })} />
          </div>
        </Card>
      </div>

      <ErrorBanner error={save.error} />
      <div className="sticky bottom-4 flex justify-end">
        <Button variant="primary" loading={save.isPending} onClick={submit} className="shadow-lg">Save & re-score jobs</Button>
      </div>
    </div>
  );
}

export function PreferencesPage() {
  const prefs = usePreferences();
  return (
    <>
      <PageHeader title="Preferences" description="What you want, how jobs are scored, and what is never acceptable." />
      {prefs.isLoading ? <Spinner /> : prefs.error ? <ErrorBanner error={prefs.error} /> : <Editor initial={prefs.data as Prefs} />}
    </>
  );
}

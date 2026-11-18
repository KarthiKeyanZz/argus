import { CheckCircle2, Circle, Plus, Trash2, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { Schemas } from "@/api/client";
import {
  useEducation,
  useExperience,
  useProfile,
  useProjects,
  useSaveProfile,
  useSectionMutations,
  useSkillMutations,
  useSkills,
} from "@/api/queries";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Badge, Button, Card, EmptyState, Spinner } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { monthYear, titleCase } from "@/lib/format";

// ----------------------------------------------------------------------------- basics

const BASIC_FIELDS: Array<[keyof Schemas["ProfileUpdate"], string, string?]> = [
  ["full_name", "Full name"], ["email", "Email", "email"], ["phone", "Phone"], ["location", "Location"],
  ["headline", "Headline"], ["linkedin_url", "LinkedIn URL", "url"], ["github_url", "GitHub URL", "url"],
  ["portfolio_url", "Portfolio URL", "url"], ["notice_period", "Notice period"],
  ["work_authorization", "Work authorization (optional)"],
];

export function BasicsCard() {
  const profile = useProfile();
  const save = useSaveProfile();
  const toast = useToast();
  const [draft, setDraft] = useState<Record<string, string> | null>(null);

  if (profile.isLoading) return <Card title="Basics"><Spinner /></Card>;
  const current = Object.fromEntries(BASIC_FIELDS.map(([k]) => [k, (profile.data?.[k] as string | null) ?? ""]));
  const values = draft ?? current;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const body = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v.trim() || null])) as Schemas["ProfileUpdate"];
    save.mutate({ ...body, summary: profile.data?.summary ?? null }, {
      onSuccess: () => { toast.success("Profile saved"); setDraft(null); },
      onError: toast.error,
    });
  };

  return (
    <Card title="Basics" description="Used to fill application forms. Leave anything you don't want to share empty.">
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-2">
        {BASIC_FIELDS.map(([key, label, type]) => (
          <Field key={key} label={label}>
            <Input type={type ?? "text"} value={values[key] ?? ""} onChange={(e) => setDraft({ ...values, [key]: e.target.value })} />
          </Field>
        ))}
        <div className="md:col-span-2">
          <Button type="submit" variant="primary" loading={save.isPending} disabled={!draft}>Save basics</Button>
        </div>
      </form>
    </Card>
  );
}

// ----------------------------------------------------------------------------- skills

export function SkillsCard() {
  const skills = useSkills();
  const { add, verify, remove } = useSkillMutations();
  const toast = useToast();
  const [name, setName] = useState("");
  const list = skills.data ?? [];
  const unverified = list.filter((s) => !s.verified).length;

  return (
    <Card
      title={`Skills (${list.length})`}
      description={unverified ? `${unverified} unverified — click a skill's circle to confirm you really have it.` : "All skills verified."}
    >
      <form
        className="mb-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) add.mutate(name.trim(), { onSuccess: () => setName(""), onError: toast.error });
        }}
      >
        <Input placeholder="Add a skill, e.g. FastAPI" value={name} onChange={(e) => setName(e.target.value)} />
        <Button type="submit" icon={<Plus className="size-4" />} loading={add.isPending}>Add</Button>
      </form>
      {skills.isLoading ? <Spinner /> : list.length === 0 ? <EmptyState title="No skills yet">Import a resume or add them here.</EmptyState> : (
        <div className="flex flex-wrap gap-1.5">
          {list.map((s) => (
            <span key={s.id} className="inline-flex items-center gap-1 rounded-md border border-slate-200 py-0.5 pr-1 pl-1.5 text-sm dark:border-slate-700" title={`${s.source}${s.name !== s.normalized_name ? ` · from "${s.name}"` : ""}`}>
              <button aria-label={s.verified ? "Mark unverified" : "Mark verified"} onClick={() => verify.mutate({ id: s.id, verified: !s.verified })}>
                {s.verified ? <CheckCircle2 className="size-3.5 text-emerald-600" /> : <Circle className="size-3.5 text-slate-400" />}
              </button>
              {s.normalized_name}
              <button aria-label={`Remove ${s.normalized_name}`} className="text-slate-400 hover:text-red-600" onClick={() => remove.mutate(s.id)}>
                <X className="size-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}

// ----------------------------------------------------------------------------- experience / education / projects

function SourceBadge({ source, verified }: { source: string; verified: boolean }) {
  return <Badge tone={verified ? "green" : "amber"}>{source}{verified ? " · verified" : ""}</Badge>;
}

export function ExperienceCard() {
  const rows = useExperience();
  const { addExperience, remove } = useSectionMutations();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", company: "", employment_type: "internship", start_date: "", end_date: "", description: "" });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    addExperience.mutate(
      { ...form, employment_type: form.employment_type as Schemas["ExperienceIn"]["employment_type"], start_date: form.start_date || null, end_date: form.end_date || null, description: form.description || null },
      { onSuccess: () => { setOpen(false); toast.success("Experience added"); }, onError: toast.error },
    );
  };

  return (
    <Card title="Experience & internships" actions={<Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => setOpen((o) => !o)}>Add</Button>}>
      {open && (
        <form onSubmit={submit} className="mb-4 grid gap-3 rounded-lg bg-slate-50 p-3 md:grid-cols-3 dark:bg-slate-800/50">
          <Field label="Title"><Input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="Company"><Input required value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} /></Field>
          <Field label="Type">
            <Select value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value })}>
              {["internship", "full_time", "part_time", "contract", "freelance", "apprenticeship"].map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}
            </Select>
          </Field>
          <Field label="Start"><Input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
          <Field label="End"><Input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
          <div className="md:col-span-3"><Field label="Description"><Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field></div>
          <div><Button type="submit" variant="primary" loading={addExperience.isPending}>Save</Button></div>
        </form>
      )}
      {rows.isLoading ? <Spinner /> : !rows.data?.length ? <EmptyState title="No experience yet" /> : (
        <ul className="space-y-4">
          {rows.data.map((x) => (
            <li key={x.id} className="flex justify-between gap-3">
              <div>
                <p className="font-medium">{x.title} <span className="font-normal text-slate-500">@ {x.company}</span></p>
                <p className="text-xs text-slate-500">
                  {titleCase(x.employment_type)} · {monthYear(x.start_date)} – {x.is_current ? "Present" : monthYear(x.end_date)} <SourceBadge source={x.source} verified={x.verified} />
                </p>
                {x.highlights.length > 0 && (
                  <ul className="mt-1.5 list-inside list-disc text-sm text-slate-600 dark:text-slate-300">
                    {x.highlights.map((h) => <li key={h}>{h}</li>)}
                  </ul>
                )}
              </div>
              <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} aria-label="Delete" onClick={() => remove.mutate({ section: "experience", id: x.id })} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function EducationCard() {
  const rows = useEducation();
  const { addEducation, remove } = useSectionMutations();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ institution: "", degree: "", field_of_study: "", grade: "", end_date: "" });

  return (
    <Card title="Education" actions={<Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => setOpen((o) => !o)}>Add</Button>}>
      {open && (
        <form
          className="mb-4 grid gap-3 rounded-lg bg-slate-50 p-3 md:grid-cols-2 dark:bg-slate-800/50"
          onSubmit={(e) => {
            e.preventDefault();
            addEducation.mutate(
              { institution: form.institution, degree: form.degree || null, field_of_study: form.field_of_study || null, grade: form.grade || null, end_date: form.end_date || null },
              { onSuccess: () => setOpen(false), onError: toast.error },
            );
          }}
        >
          <Field label="Institution"><Input required value={form.institution} onChange={(e) => setForm({ ...form, institution: e.target.value })} /></Field>
          <Field label="Degree"><Input value={form.degree} onChange={(e) => setForm({ ...form, degree: e.target.value })} /></Field>
          <Field label="Field of study"><Input value={form.field_of_study} onChange={(e) => setForm({ ...form, field_of_study: e.target.value })} /></Field>
          <Field label="Grade"><Input value={form.grade} onChange={(e) => setForm({ ...form, grade: e.target.value })} /></Field>
          <Field label="Graduation"><Input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
          <div className="self-end"><Button type="submit" variant="primary" loading={addEducation.isPending}>Save</Button></div>
        </form>
      )}
      {rows.isLoading ? <Spinner /> : !rows.data?.length ? <EmptyState title="No education yet" /> : (
        <ul className="space-y-3">
          {rows.data.map((e) => (
            <li key={e.id} className="flex justify-between gap-3">
              <div>
                <p className="font-medium">{e.degree} {e.field_of_study ? `· ${e.field_of_study}` : ""}</p>
                <p className="text-xs text-slate-500">{e.institution} · {monthYear(e.start_date)} – {monthYear(e.end_date)} {e.grade ? `· ${e.grade}` : ""} <SourceBadge source={e.source} verified={e.verified} /></p>
              </div>
              <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} aria-label="Delete" onClick={() => remove.mutate({ section: "education", id: e.id })} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function ProjectsCard() {
  const rows = useProjects();
  const { addProject, remove } = useSectionMutations();
  const toast = useToast();
  const [name, setName] = useState("");
  const [tech, setTech] = useState("");

  return (
    <Card title="Projects">
      <form
        className="mb-4 flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          addProject.mutate(
            { name, tech: tech.split(",").map((t) => t.trim()).filter(Boolean) },
            { onSuccess: () => { setName(""); setTech(""); }, onError: toast.error },
          );
        }}
      >
        <Input className="max-w-56" required placeholder="Project name" value={name} onChange={(e) => setName(e.target.value)} />
        <Input className="flex-1" placeholder="Tech, comma separated" value={tech} onChange={(e) => setTech(e.target.value)} />
        <Button type="submit" icon={<Plus className="size-4" />} loading={addProject.isPending}>Add</Button>
      </form>
      {rows.isLoading ? <Spinner /> : !rows.data?.length ? <EmptyState title="No projects yet" /> : (
        <ul className="space-y-2">
          {rows.data.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3">
              <div>
                <span className="font-medium">{p.name}</span>{" "}
                {p.tech.map((t) => <Badge key={t}>{t}</Badge>)}
              </div>
              <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} aria-label="Delete" onClick={() => remove.mutate({ section: "projects", id: p.id })} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

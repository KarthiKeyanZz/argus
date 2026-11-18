import { FileText, Sparkles, Trash2, Upload } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import type { Schemas } from "@/api/client";
import { useResumeMutations, useResumes } from "@/api/queries";
import { Checkbox, Field, Input, Select, TagInput, Textarea } from "@/components/ui/form";
import { Badge, Button, Card, ErrorBanner } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { bytes, timeAgo } from "@/lib/format";

type Facts = Schemas["ResumeFacts"];
type Parse = Schemas["ResumeParseResponse"];
const DATE_HINT = "Format: “Jun 2025”, “2025” or “Present”";

/** Editable review of what the LLM read. Nothing is saved until "Import". */
function ReviewForm({ parse, onDone }: { parse: Parse; onDone: () => void }) {
  const [facts, setFacts] = useState<Facts>(parse.facts);
  const [replace, setReplace] = useState(true);
  const { importFacts } = useResumeMutations();
  const toast = useToast();

  const set = <K extends keyof Facts>(key: K, value: Facts[K]) => setFacts((f) => ({ ...f, [key]: value }));
  const setItem = <K extends "experience" | "education" | "projects">(key: K, index: number, patch: Partial<NonNullable<Facts[K]>[number]>) =>
    setFacts((f) => ({ ...f, [key]: (f[key] ?? []).map((item, i) => (i === index ? { ...item, ...patch } : item)) }));
  const removeItem = (key: "experience" | "education" | "projects", index: number) =>
    setFacts((f) => ({ ...f, [key]: (f[key] ?? []).filter((_, i) => i !== index) }));

  const submit = () =>
    importFacts.mutate(
      { id: parse.resume_id, body: { facts, replace_existing: replace, mark_verified: true } },
      {
        onSuccess: (r) => {
          toast.success(`Imported: ${r.experience} roles, ${r.education} education, ${r.projects} projects, ${r.skills_created} new skills`);
          onDone();
        },
        onError: toast.error,
      },
    );

  const m = parse.metrics;
  return (
    <Card
      title="Review what the LLM extracted"
      description={`${parse.model} read your resume in ${(m.total_ms / 1000).toFixed(1)} s (${m.output_tokens} tokens at ${m.output_tokens_per_s ?? "?"} tok/s). Fix anything wrong before importing — only verified facts are used in applications.`}
    >
      <div className="space-y-6">
        <section className="grid gap-3 md:grid-cols-3">
          <Field label="Full name"><Input value={facts.full_name ?? ""} onChange={(e) => set("full_name", e.target.value || null)} /></Field>
          <Field label="Email"><Input value={facts.email ?? ""} onChange={(e) => set("email", e.target.value || null)} /></Field>
          <Field label="Phone"><Input value={facts.phone ?? ""} onChange={(e) => set("phone", e.target.value || null)} /></Field>
          <Field label="Location"><Input value={facts.location ?? ""} onChange={(e) => set("location", e.target.value || null)} /></Field>
          <div className="md:col-span-2">
            <Field label="Headline"><Input value={facts.headline ?? ""} onChange={(e) => set("headline", e.target.value || null)} /></Field>
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-sm font-semibold">Experience</h3>
          {(facts.experience ?? []).length === 0 && <p className="text-sm text-slate-500">None found.</p>}
          <div className="space-y-3">
            {(facts.experience ?? []).map((x, i) => (
              <div key={i} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <div className="grid gap-3 md:grid-cols-4">
                  <Field label="Title"><Input value={x.title} onChange={(e) => setItem("experience", i, { title: e.target.value })} /></Field>
                  <Field label="Company"><Input value={x.company} onChange={(e) => setItem("experience", i, { company: e.target.value })} /></Field>
                  <Field label="Start" hint={DATE_HINT}><Input value={x.start ?? ""} onChange={(e) => setItem("experience", i, { start: e.target.value || null })} /></Field>
                  <Field label="End"><Input value={x.end ?? ""} onChange={(e) => setItem("experience", i, { end: e.target.value || null })} /></Field>
                  <Field label="Type">
                    <Select value={x.employment_type} onChange={(e) => setItem("experience", i, { employment_type: e.target.value as typeof x.employment_type })}>
                      {["internship", "full_time", "part_time", "contract", "freelance"].map((t) => <option key={t} value={t}>{t}</option>)}
                    </Select>
                  </Field>
                  <div className="md:col-span-3">
                    <Field label="Highlights (one per line, copied from your resume)">
                      <Textarea value={(x.highlights ?? []).join("\n")} onChange={(e) => setItem("experience", i, { highlights: e.target.value.split("\n").filter(Boolean) })} />
                    </Field>
                  </div>
                </div>
                <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                  <span>Duration (computed in code): {parse.durations[i]?.months ?? "?"} months</span>
                  <Button size="sm" variant="ghost" onClick={() => removeItem("experience", i)}>Remove</Button>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-sm font-semibold">Education</h3>
          <div className="space-y-3">
            {(facts.education ?? []).map((e, i) => (
              <div key={i} className="grid gap-3 rounded-lg border border-slate-200 p-3 md:grid-cols-5 dark:border-slate-700">
                <div className="md:col-span-2"><Field label="Institution"><Input value={e.institution} onChange={(ev) => setItem("education", i, { institution: ev.target.value })} /></Field></div>
                <Field label="Degree"><Input value={e.degree} onChange={(ev) => setItem("education", i, { degree: ev.target.value })} /></Field>
                <Field label="Years"><Input value={`${e.start_year ?? ""}–${e.end_year ?? ""}`} readOnly /></Field>
                <Field label="Grade"><Input value={e.grade ?? ""} onChange={(ev) => setItem("education", i, { grade: ev.target.value || null })} /></Field>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h3 className="mb-2 text-sm font-semibold">Projects</h3>
          <div className="space-y-2">
            {(facts.projects ?? []).map((p, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <Input className="max-w-56" value={p.name} onChange={(e) => setItem("projects", i, { name: e.target.value })} />
                <div className="flex-1"><TagInput value={p.tech ?? []} onChange={(tech) => setItem("projects", i, { tech })} /></div>
                <Button size="sm" variant="ghost" onClick={() => removeItem("projects", i)}>Remove</Button>
              </div>
            ))}
          </div>
        </section>

        <section>
          <Field label="Skills" hint="Synonyms are merged on import (e.g. JS → javascript, Postgres → postgresql).">
            <TagInput value={facts.skills ?? []} onChange={(skills) => set("skills", skills)} />
          </Field>
        </section>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4 dark:border-slate-800">
          <Checkbox label="Replace facts imported from an earlier resume" checked={replace} onChange={setReplace} />
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onDone}>Discard</Button>
            <Button variant="primary" loading={importFacts.isPending} onClick={submit}>Import into profile</Button>
          </div>
        </div>
        <ErrorBanner error={importFacts.error} />
      </div>
    </Card>
  );
}

export function ResumeImport() {
  const resumes = useResumes();
  const { upload, parse, remove } = useResumeMutations();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [review, setReview] = useState<Parse | null>(null);
  const [parsingId, setParsingId] = useState<number | null>(null);

  const send = (file: File | undefined) => {
    if (!file) return;
    upload.mutate(file, {
      onSuccess: (r) => toast.success(r.created ? "Resume uploaded — click Read with LLM" : "This exact file was already uploaded"),
      onError: toast.error,
    });
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    send(e.dataTransfer.files[0]);
  };
  const runParse = (id: number) => {
    setParsingId(id);
    parse.mutate(id, { onSuccess: setReview, onError: toast.error, onSettled: () => setParsingId(null) });
  };

  if (review) return <ReviewForm parse={review} onDone={() => setReview(null)} />;

  return (
    <Card title="Resume" description="PDF or DOCX, max 5 MB. Parsed on this machine by the local LLM; you review everything before it's saved.">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`mb-4 flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors ${dragging ? "border-brand-500 bg-brand-50 dark:bg-brand-500/10" : "border-slate-300 dark:border-slate-700"}`}
      >
        <Upload className="mb-2 size-6 text-slate-400" />
        <p className="text-sm">Drag your resume here, or</p>
        <Button className="mt-2" size="sm" loading={upload.isPending} onClick={() => input.current?.click()}>Choose file</Button>
        <input ref={input} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="hidden" onChange={(e) => send(e.target.files?.[0])} />
      </div>

      <ul className="divide-y divide-slate-100 dark:divide-slate-800">
        {(resumes.data ?? []).map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
            <div className="flex items-center gap-2">
              <FileText className="size-4 text-slate-400" />
              <span className="text-sm font-medium">{r.original_filename}</span>
              {r.is_master && <Badge tone="violet">current</Badge>}
              <span className="text-xs text-slate-500">{bytes(r.size_bytes)} · {r.text_chars} chars · {timeAgo(r.uploaded_at)}</span>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="primary" icon={<Sparkles className="size-3.5" />} loading={parsingId === r.id} disabled={parsingId !== null} onClick={() => runParse(r.id)}>
                {parsingId === r.id ? "Reading… (~15 s)" : "Read with LLM"}
              </Button>
              <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} aria-label="Delete resume" onClick={() => remove.mutate(r.id, { onError: toast.error })} />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

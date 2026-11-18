import { Play } from "lucide-react";
import { useState } from "react";

import type { Schemas } from "@/api/client";
import { useGenerate, useModels, useSimilarity } from "@/api/queries";
import { Checkbox, Field, Input, Select, Slider, Textarea } from "@/components/ui/form";
import { Badge, Button, Card, ErrorBanner, Meter, PageHeader, Spinner } from "@/components/ui/primitives";

type Options = NonNullable<Schemas["GenerateRequest"]["options"]>;

const PRESETS: Record<string, { label: string; options: Options; hint: string }> = {
  extraction: { label: "Extraction (deterministic)", options: { temperature: 0, seed: 7 }, hint: "Same input → same output. Use for facts." },
  balanced: { label: "Balanced", options: { temperature: 0.7, top_p: 0.9 }, hint: "Natural writing with some variety." },
  creative: { label: "Creative", options: { temperature: 1.2, top_p: 0.95 }, hint: "More surprising — and more likely to be wrong." },
};

function Metrics({ m }: { m: Schemas["GenerationMetrics"] }) {
  const items: Array<[string, string, string]> = [
    ["Output speed", `${m.output_tokens_per_s ?? "–"} tok/s`, "Decode: one token at a time. The number to watch when tuning."],
    ["Prompt speed", `${m.prompt_tokens_per_s ?? "–"} tok/s`, "Prefill: the whole prompt is read in parallel — much faster."],
    ["Tokens", `${m.prompt_tokens} in · ${m.output_tokens} out`, "~4 characters of English per token."],
    ["Load", `${(m.load_ms / 1000).toFixed(1)} s`, "Time to load weights into memory. ~0 when the model is warm."],
    ["Total", `${(m.total_ms / 1000).toFixed(1)} s`, "Wall-clock time for the request."],
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {items.map(([k, v, hint]) => (
        <div key={k} className="rounded-lg bg-slate-50 p-2.5 dark:bg-slate-800/60" title={hint}>
          <dt className="text-[11px] text-slate-500 uppercase">{k}</dt>
          <dd className="text-sm font-semibold tabular-nums">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Playground({ chatModel }: { chatModel: string }) {
  const generate = useGenerate();
  const [prompt, setPrompt] = useState("In two sentences, what is a context window in an LLM?");
  const [system, setSystem] = useState("");
  const [options, setOptions] = useState<Options>({ temperature: 0, seed: 7, num_ctx: 8192, num_predict: 512 });
  const [think, setThink] = useState<"default" | "on" | "off">("off");
  const [jsonMode, setJsonMode] = useState(false);
  const set = (k: keyof Options, v: number | null) => setOptions((o) => ({ ...o, [k]: v }));

  const run = () =>
    generate.mutate({
      prompt,
      system: system || null,
      options,
      format: jsonMode ? "json" : null,
      think: think === "default" ? null : think === "on",
    });
  const r = generate.data;

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <Card className="lg:col-span-3" title="Prompt" description={`Model: ${chatModel}`} actions={<Button variant="primary" icon={<Play className="size-4" />} loading={generate.isPending} onClick={run}>Run</Button>}>
        <div className="space-y-3">
          <Field label="System prompt" hint="Standing instructions / persona. Try: “Answer like a pirate.”">
            <Textarea className="min-h-16" value={system} onChange={(e) => setSystem(e.target.value)} />
          </Field>
          <Field label="User prompt"><Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} /></Field>
          <ErrorBanner error={generate.error} />
          {generate.isPending && <Spinner label="Generating (the first call after a while also loads 15 GB into memory)" />}
          {r && (
            <div className="space-y-3">
              {r.thinking && (
                <details className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
                  <summary className="cursor-pointer font-medium">Model's thinking ({r.thinking.length} chars)</summary>
                  <p className="mt-2 whitespace-pre-wrap text-slate-600 dark:text-slate-300">{r.thinking}</p>
                </details>
              )}
              <div className="rounded-lg bg-slate-50 p-3 text-sm whitespace-pre-wrap dark:bg-slate-800/60">{r.response}</div>
              <p className="text-xs text-slate-500">done_reason: <b>{r.done_reason}</b> {r.done_reason === "length" && "— hit num_predict, the answer was cut off"}</p>
              <Metrics m={r.metrics} />
            </div>
          )}
        </div>
      </Card>

      <Card className="lg:col-span-2" title="Tuning knobs" description="Each knob changes how the next token is picked.">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(PRESETS).map(([key, p]) => (
              <Button key={key} size="sm" title={p.hint} onClick={() => setOptions((o) => ({ num_ctx: o.num_ctx, num_predict: o.num_predict, ...p.options }))}>{p.label}</Button>
            ))}
          </div>
          <Slider label="temperature" min={0} max={2} step={0.05} value={options.temperature ?? 1} onChange={(v) => set("temperature", v)}
            hint="0 = always the most likely token (deterministic). Higher = flatter probabilities = more random." />
          <Slider label="top_p" min={0.05} max={1} step={0.05} value={options.top_p ?? 0.95} onChange={(v) => set("top_p", v)}
            hint="Sample only from the smallest set of tokens whose probabilities add up to p." />
          <Slider label="top_k" min={1} max={100} step={1} value={options.top_k ?? 64} onChange={(v) => set("top_k", v)}
            hint="Sample only from the k most likely tokens." />
          <Slider label="repeat_penalty" min={0.8} max={1.5} step={0.05} value={options.repeat_penalty ?? 1} onChange={(v) => set("repeat_penalty", v)}
            hint=">1 discourages repeating tokens (fights loops)." />
          <div className="grid grid-cols-2 gap-3">
            <Field label="seed" hint="Same seed + same input = same output">
              <Input type="number" value={options.seed ?? ""} onChange={(e) => set("seed", e.target.value === "" ? null : Number(e.target.value))} />
            </Field>
            <Field label="num_predict" hint="Max output tokens">
              <Input type="number" min={1} value={options.num_predict ?? ""} onChange={(e) => set("num_predict", e.target.value === "" ? null : Number(e.target.value))} />
            </Field>
          </div>
          <Field label="num_ctx (context window)" hint="Bigger = more GPU memory (KV cache) and slower. Watch output speed change.">
            <Select value={options.num_ctx ?? 8192} onChange={(e) => set("num_ctx", Number(e.target.value))}>
              {[2048, 4096, 8192, 16384, 32768].map((n) => <option key={n} value={n}>{n.toLocaleString()} tokens</option>)}
            </Select>
          </Field>
          <Field label="think" hint="Gemma 4 can reason before answering: often better, always slower.">
            <Select value={think} onChange={(e) => setThink(e.target.value as typeof think)}>
              <option value="off">off (fast)</option>
              <option value="on">on (shows reasoning)</option>
              <option value="default">model default</option>
            </Select>
          </Field>
          <Checkbox label="JSON mode" hint="Constrained decoding: output is guaranteed to be valid JSON" checked={jsonMode} onChange={setJsonMode} />
        </div>
      </Card>
    </div>
  );
}

function SimilarityTool() {
  const sim = useSimilarity();
  const [query, setQuery] = useState("junior python backend developer");
  const [candidates, setCandidates] = useState("Entry-level Backend Developer (FastAPI)\nGraduate Software Engineer - Python/Django\nSenior Staff Machine Learning Engineer\nRestaurant Manager");
  return (
    <Card title="Embeddings: similarity search" description="Texts become 768-number vectors; cosine similarity measures closeness in meaning (1 = same, ~0 = unrelated).">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <Field label="Query"><Input value={query} onChange={(e) => setQuery(e.target.value)} /></Field>
          <Field label="Candidates (one per line)"><Textarea className="min-h-32" value={candidates} onChange={(e) => setCandidates(e.target.value)} /></Field>
          <Button variant="primary" loading={sim.isPending} onClick={() => sim.mutate({ query, candidates: candidates.split("\n").map((c) => c.trim()).filter(Boolean) })}>Rank by meaning</Button>
          <ErrorBanner error={sim.error} />
        </div>
        <div className="space-y-3">
          {sim.data?.results.map((h) => <Meter key={h.text} label={h.text} value={h.score} hint={h.score.toFixed(3)} />)}
          {sim.data && <p className="text-xs text-slate-500">ARGUS counts a skill as "similar" at ≥ 0.70 — calibrated on real pairs (see docs/learning).</p>}
        </div>
      </div>
    </Card>
  );
}

export function LlmLabPage() {
  const models = useModels();
  return (
    <>
      <PageHeader title="LLM Lab" description="Experiment with the local model and see how each setting changes the output and speed. Nothing here touches your data." />
      <div className="space-y-6">
        <Card title="Models on this machine">
          {models.isLoading ? <Spinner /> : models.error ? <ErrorBanner error={models.error} /> : (
            <ul className="grid gap-2 sm:grid-cols-3">
              {models.data!.models.map((m) => (
                <li key={m.name} className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
                  <p className="font-mono text-xs font-medium">{m.name}</p>
                  <p className="mt-1 text-xs text-slate-500">{m.parameter_size} · {m.quantization} · {m.size_gb} GB on disk</p>
                  <p className="mt-1.5">{m.loaded ? <Badge tone="green">loaded · {m.vram_gb} GB in VRAM</Badge> : <Badge>not loaded</Badge>}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Playground chatModel={models.data?.chat_model ?? "…"} />
        <SimilarityTool />
      </div>
    </>
  );
}

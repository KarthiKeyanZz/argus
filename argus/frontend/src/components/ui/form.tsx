import { clsx } from "clsx";
import { X } from "lucide-react";
import { createContext, useContext, useId, useState, type InputHTMLAttributes, type KeyboardEvent, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

const CONTROL =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-slate-700 dark:bg-slate-950";

/** A Field hands its generated id to the control inside it, so <label> and input are linked
 * (screen readers announce the label; clicking the label focuses the input). */
const FieldIdContext = createContext<{ id: string; hintId: string } | null>(null);

function useFieldIds(explicitId: string | undefined) {
  const field = useContext(FieldIdContext);
  return { id: explicitId ?? field?.id, describedBy: field?.hintId };
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <FieldIdContext.Provider value={{ id, hintId }}>{children}</FieldIdContext.Provider>
      {hint && <p id={hintId} className="text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  );
}

export function Input({ className, id, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  const ids = useFieldIds(id);
  return <input id={ids.id} aria-describedby={ids.describedBy} className={clsx(CONTROL, className)} {...rest} />;
}

export function Textarea({ className, id, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ids = useFieldIds(id);
  return <textarea id={ids.id} aria-describedby={ids.describedBy} className={clsx(CONTROL, "min-h-24", className)} {...rest} />;
}

export function Select({ className, children, id, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  const ids = useFieldIds(id);
  return (
    <select id={ids.id} aria-describedby={ids.describedBy} className={clsx(CONTROL, className)} {...rest}>
      {children}
    </select>
  );
}

export function Checkbox({ label, checked, onChange, hint }: { label: ReactNode; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  const id = useId();
  return (
    <div className="flex items-start gap-2">
      <input id={id} type="checkbox" className="mt-0.5 size-4 accent-brand-600" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <label htmlFor={id} className="text-sm">
        {label}
        {hint && <span className="block text-xs text-slate-500">{hint}</span>}
      </label>
    </div>
  );
}

/** Free-text list editor: type and press Enter (or comma) to add a chip. */
export function TagInput({ value, onChange, placeholder, id }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string; id?: string }) {
  const [draft, setDraft] = useState("");
  const ids = useFieldIds(id);

  const commit = () => {
    const items = draft.split(",").map((s) => s.trim()).filter(Boolean);
    if (items.length) {
      const seen = new Set(value.map((v) => v.toLowerCase())); // O(1) duplicate checks
      onChange([...value, ...items.filter((i) => !seen.has(i.toLowerCase()))]);
    }
    setDraft("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div className={clsx(CONTROL, "flex flex-wrap items-center gap-1.5 py-1.5")}>
      {value.map((item, index) => (
        <span key={`${item}-${index}`} className="inline-flex items-center gap-1 rounded-md bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700 dark:bg-brand-500/20 dark:text-brand-100">
          {item}
          <button type="button" aria-label={`Remove ${item}`} onClick={() => onChange(value.filter((_, i) => i !== index))}>
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        id={ids.id}
        aria-describedby={ids.describedBy}
        className="min-w-32 flex-1 bg-transparent py-0.5 text-sm outline-none"
        value={draft}
        placeholder={value.length ? "" : placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
      />
    </div>
  );
}

/** Range slider with live value and an explanation - used by the LLM Lab and weights. */
export function Slider({ label, value, onChange, min, max, step, hint, format }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step: number; hint?: string; format?: (v: number) => string;
}) {
  const id = useId();
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <label htmlFor={id} className="font-medium">{label}</label>
        <span className="tabular-nums text-slate-500">{format ? format(value) : value}</span>
      </div>
      <input id={id} type="range" className="w-full accent-brand-600" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      {hint && <p className="text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  );
}
